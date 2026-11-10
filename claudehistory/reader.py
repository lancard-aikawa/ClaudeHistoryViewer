import json
import os
import re
import threading
from collections import OrderedDict
from pathlib import Path


def _is_session_file(stem: str) -> bool:
    return bool(re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', stem))

def _read_cwd(path: Path) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                cwd = obj.get("cwd")
                if cwd:
                    return cwd
    except Exception:
        pass
    return None

def _read_head_meta(path: Path) -> tuple:
    """(cwd, 最初の発言の時刻) を返す。両方そろった時点で読むのをやめる。
    プロジェクト一覧はこれだけで足りる（全文を読むと、履歴が数百 MB あるので一覧に 10 秒以上かかった）"""
    cwd = None
    timestamp = None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if cwd is None:
                    cwd = obj.get("cwd") or None
                if timestamp is None and obj.get("type") in ("user", "assistant"):
                    timestamp = obj.get("timestamp")
                if cwd and timestamp:
                    break
    except Exception:
        pass
    return cwd, timestamp

# Claude Code は JSONL を空白なしで書くので、発言の行には `"type":"user"` などの文字列が必ずある（キーの順番は行ごとに違う）。
# 行の大半は api-request-blob やツール結果の画像で、JSON を解くと遅い（521 MB のセッションで 1.8 秒）。
# この文字列が無い行は解かずに飛ばす。あっても発言とは限らないので、解いてから type を確かめる
_MSG_MARKERS = ('"type":"user"', '"type":"assistant"', '"type": "user"', '"type": "assistant"')
_TITLE_MARKERS = ('"type":"ai-title"', '"type": "ai-title"')


def _maybe_message(line: str) -> bool:
    return any(m in line for m in _MSG_MARKERS)


def _read_session_meta(path: Path) -> tuple:
    """(題, 最初の発言の時刻, 発言の行の数)。数は目安なので、行を解かずに印の文字列で数える"""
    title = path.stem
    timestamp = None
    msg_count = 0
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if any(m in line for m in _TITLE_MARKERS):
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    if obj.get("type") == "ai-title":
                        title = obj.get("aiTitle", title)
                elif _maybe_message(line):
                    if timestamp is None:
                        try:
                            obj = json.loads(line)
                        except ValueError:
                            continue
                        if obj.get("type") not in ("user", "assistant"):
                            continue
                        timestamp = obj.get("timestamp")
                    msg_count += 1
    except OSError:
        pass
    return title, timestamp, msg_count

# user の行に Claude Code が差し込むタグ。人が打ったものではないので消す（RepoTether の sessions.rs と同じ一覧）
_NOISE_TAGS = ("system-reminder", "ide_selection", "ide_opened_file", "ide_diagnostics",
               "local-command-stdout", "local-command-stderr", "local-command-caveat",
               "command-message", "command-args")
_NOISE_RE = [re.compile(rf"<{t}(?:\s[^>]*)?>.*?</{t}>", re.DOTALL) for t in _NOISE_TAGS]
# /mcp などのコマンドは名前だけ残す
_COMMAND_RE = re.compile(r"<command-name>(.*?)</command-name>", re.DOTALL)
_TASK_SUMMARY_RE = re.compile(r"<summary>(.*?)</summary>", re.DOTALL)


def _strip_user_noise(t: str) -> str:
    for r in _NOISE_RE:
        t = r.sub("", t)
    return _COMMAND_RE.sub(r"\1", t).strip()


def _system_note(obj: dict, text: str) -> dict:
    """人の発言ではないが、会話の流れとして見せたいもの（中断・裏の作業の完了）"""
    return {"uuid": obj.get("uuid", ""), "role": "system", "timestamp": obj.get("timestamp", ""),
            "text": text, "thinking": [], "tool_uses": [], "images": [], "plan_content": None}


def _process_message(obj: dict) -> dict | None:
    role = obj.get("type")
    raw_content = obj.get("message", {}).get("content", [])

    if role == "user":
        # ハーネスが差し込んだもの（Skill の展開文・画像の大きさの注記・別セッションからの連絡など）。
        # 2026-10-01 の実データでは 142 件すべて文字だけで、画像は別の行にある
        if obj.get("isMeta"):
            return None
        # 文脈が長くなって要約したときの要約文。Claude Code が書いたもので、人の発言ではない
        if obj.get("isCompactSummary"):
            text = raw_content if isinstance(raw_content, str) else "\n".join(
                b.get("text", "") for b in raw_content if isinstance(b, dict) and b.get("type") == "text")
            return {"uuid": obj.get("uuid", ""), "role": "summary", "timestamp": obj.get("timestamp", ""),
                    "text": text.strip(), "thinking": [], "tool_uses": [], "images": [], "plan_content": None}

    # Normalize to list
    if isinstance(raw_content, str):
        raw_content = [{"type": "text", "text": raw_content}]
    elif not isinstance(raw_content, list):
        return None

    text_parts = []
    thinking_blocks = []
    tool_uses = []
    images = []
    has_user_text = False

    for block in raw_content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            t = block.get("text", "")
            if role == "user":
                stripped = t.lstrip()
                # 裏の作業（バックグラウンドのコマンドやサブエージェント）の完了通知
                if stripped.startswith("<task-notification>"):
                    m = _TASK_SUMMARY_RE.search(t)
                    return _system_note(obj, "裏の作業: " + (m.group(1).strip() if m else "完了の通知"))
                # 中断の印 ([Request interrupted by user] など)
                if stripped.startswith("[Request interrupted"):
                    return _system_note(obj, "中断しました" + (
                        "（ツールの実行中）" if "tool use" in stripped else ""))
                t = _strip_user_noise(t)
            else:
                t = re.sub(r'<ide_opened_file>.*?</ide_opened_file>', '', t, flags=re.DOTALL).strip()
                t = re.sub(r'<ide_selection>.*?</ide_selection>', '', t, flags=re.DOTALL).strip()
            if t:
                text_parts.append(t)
                has_user_text = True
        elif btype == "thinking":
            t = block.get("thinking", "")
            if t:
                thinking_blocks.append(t)
        elif btype == "tool_use":
            tool_uses.append(_process_tool_use(block))
        elif btype == "tool_result":
            inner = block.get("content", "")
            if isinstance(inner, str) and block.get("is_error"):
                # Extract user-supplied reason from tool rejection messages
                marker = "The user provided the following reason for the rejection:"
                idx = inner.find(marker)
                if idx != -1:
                    reason = inner[idx + len(marker):].strip()
                    if reason:
                        text_parts.append(reason)
                        has_user_text = True
            elif isinstance(inner, list):
                for item in inner:
                    if isinstance(item, dict) and item.get("type") == "image":
                        src = item.get("source", {})
                        images.append({
                            "media_type": src.get("media_type", "image/png"),
                            "data": src.get("data", ""),
                        })

    # Skip user messages that are only tool results (no real text)。
    # images はツール結果の中の画像 (スクリーンショットなど) なので、それだけでは人の発言にしない
    if role == "user" and not has_user_text:
        return None

    # Skip assistant messages with no displayable content
    if role == "assistant" and not text_parts and not tool_uses and not thinking_blocks:
        return None

    # Detect plan-mode injection ("Implement the following plan:")
    plan_content = obj.get("planContent")

    return {
        "uuid": obj.get("uuid", ""),
        "role": role,
        "timestamp": obj.get("timestamp", ""),
        "text": "\n\n".join(text_parts),
        "thinking": thinking_blocks,
        "tool_uses": tool_uses,
        "images": images,
        "plan_content": plan_content,
    }

def _process_tool_use(block: dict) -> dict:
    name = block.get("name", "unknown")
    inp = block.get("input", {})
    file_path = None
    description = ""

    if name in ("Read", "Write", "Edit", "NotebookEdit", "NotebookRead"):
        file_path = inp.get("file_path") or inp.get("notebook_path", "")
        description = file_path or ""
    elif name == "Glob":
        description = inp.get("pattern", "")
        if inp.get("path"):
            description += f" in {inp['path']}"
    elif name == "Grep":
        description = inp.get("pattern", "")
        if inp.get("path"):
            description += f" in {inp['path']}"
    elif name == "Bash":
        description = inp.get("command", "")
    elif name in ("WebFetch", "WebSearch"):
        description = inp.get("url") or inp.get("query") or ""
    elif name == "Agent":
        description = inp.get("description") or inp.get("prompt", "")
    else:
        for v in inp.values():
            if isinstance(v, str) and v:
                description = v
                break

    return {"name": name, "file": file_path, "description": description}

def _stat_key(path: Path):
    try:
        st = path.stat()
    except OSError:
        return None
    return [st.st_size, st.st_mtime_ns]


class _FileCache:
    """ファイルを読んで得たものを (サイズ, 更新時刻) と一緒に覚える。変わっていないファイルは読み直さない。
    path を渡すと、次に起動したときも使えるようファイルに書く（履歴が数 GB あると、全部の一覧を作り直すのに十数秒かかる）"""

    # 読み方を変えたら上げる（古い結果を捨てる）
    VERSION = 1

    def __init__(self, path: Path | None = None):
        self.path = path
        self._data: dict = {}  # {種類: {パス: [[サイズ, 更新時刻], 値]}}
        self._dirty = False
        self._lock = threading.Lock()
        if path and path.is_file():
            try:
                with open(path, encoding="utf-8") as f:
                    saved = json.load(f)
                if saved.get("version") == self.VERSION:
                    self._data = saved.get("files", {})
            except (OSError, ValueError):
                pass

    def get(self, kind: str, path: Path, read):
        key = _stat_key(path)
        if key is None:
            return None
        name = str(path)
        hit = self._data.get(kind, {}).get(name)
        if hit and hit[0] == key:
            return hit[1]
        value = read(path)
        with self._lock:
            self._data.setdefault(kind, {})[name] = [key, value]
            self._dirty = True
        return value

    def save(self) -> None:
        if not self.path or not self._dirty:
            return
        with self._lock:
            # 消えたファイルの分は捨てる（ゴミ箱に移したものなど）
            self._data = {kind: {k: v for k, v in files.items() if os.path.exists(k)}
                          for kind, files in self._data.items()}
            data = {"version": self.VERSION, "files": self._data}
            self._dirty = False
            try:
                tmp = self.path.with_name(self.path.name + ".tmp")
                with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                    json.dump(data, f, ensure_ascii=False)
                os.replace(tmp, self.path)
            except OSError:
                pass


class ClaudeDataReader:
    # 開いたセッションの表示用の中身を、新しく開いた順にいくつ覚えておくか（前後の移動や、検索から飛んだときに読み直さない）
    MESSAGE_CACHE_SIZE = 8

    def __init__(self, claude_dir: Path, backup_roots: list | None = None,
                 cache_file: Path | None = None, index_file: Path | None = None):
        from .search_index import SearchIndex  # search_index がこのモジュールの関数を使うので、ここで読む
        self.claude_dir = claude_dir
        self.projects_dir = claude_dir / "projects"
        # バックアップ（SessionVault の mirror や、内蔵のバックアップ）。projects と同じ木の形。
        # 元のファイルが消えてもここから読む
        self.backup_roots = list(backup_roots or [])
        # プロジェクト一覧用の (cwd, timestamp) と、セッション一覧用の (題, 時刻, 件数)
        self._cache = _FileCache(cache_file)
        self._messages = OrderedDict()  # {path: (stat_key, messages)}
        self._messages_lock = threading.Lock()
        self._index = SearchIndex(index_file)

    def _head_meta(self, path: Path) -> tuple:
        meta = self._cache.get("head", path, _read_head_meta)
        return tuple(meta) if meta else (None, None)

    def _session_meta(self, path: Path) -> tuple:
        meta = self._cache.get("session", path, _read_session_meta)
        return tuple(meta) if meta else (path.stem, None, 0)

    def save_cache(self) -> None:
        self._cache.save()

    def _roots(self) -> list:
        """読み込み元。先に書いた方が優先（元のファイル > バックアップ）"""
        return [self.projects_dir, *self.backup_roots]

    def _dir_map(self) -> dict:
        """{小文字にしたプロジェクト名: [(root の番号, フォルダ)]}。各 root を 1 回だけ読む
        （プロジェクトごとに全部の root を並べ直すと、検索 1 回で 1 万回 is_dir を呼んで 0.3 秒かかった）"""
        out = {}
        for i, root in enumerate(self._roots()):
            try:
                with os.scandir(root) as it:
                    for d in it:
                        if d.is_dir():
                            out.setdefault(d.name.casefold(), []).append((i, Path(d.path)))
            except OSError:
                pass
        return out

    def _project_ids(self) -> list:
        """プロジェクトのフォルダ名。C--x と c--x は同じプロジェクト（Claude Code が大文字・小文字を揺らす）。
        先に見つけた綴りを使う"""
        return [dirs[0][1].name for dirs in self._dir_map().values()]

    def _project_dirs(self, project_id: str, dir_map: dict | None = None) -> list:
        """[(root の番号, そのプロジェクトのフォルダ)]。大文字・小文字を無視して探す"""
        return (dir_map if dir_map is not None else self._dir_map()).get(project_id.casefold(), [])

    def _session_files(self, project_id: str, dir_map: dict | None = None) -> dict:
        """{session_id: (path, archived_only)} を返す。同じ ID は元のファイルを優先"""
        files = {}
        for i, proj_dir in self._project_dirs(project_id, dir_map):
            try:
                with os.scandir(proj_dir) as it:
                    names = sorted(e.name for e in it if e.name.endswith(".jsonl") and e.is_file())
            except OSError:
                continue
            for name in names:
                stem = name[:-6]
                if _is_session_file(stem) and stem not in files:
                    files[stem] = (proj_dir / name, i > 0)
        return files

    # ---- Projects ----

    def list_projects(self) -> list:
        projects = []
        dir_map = self._dir_map()
        for dirs in dir_map.values():
            proj_id = dirs[0][1].name
            cwd, first_ts, last_ts, session_count = self._project_summary(proj_id, dir_map)
            if session_count == 0:
                continue
            projects.append({
                "id": proj_id,
                "cwd": cwd or proj_id,
                "session_count": session_count,
                "first_activity": first_ts,
                "last_activity": last_ts,
            })
        projects.sort(key=lambda x: x["last_activity"] or "", reverse=True)
        return projects

    def _project_summary(self, project_id: str, dir_map: dict | None = None):
        cwd = None
        first_ts = None
        last_ts = None
        session_count = 0
        for f, _ in self._session_files(project_id, dir_map).values():
            session_count += 1
            file_cwd, ts = self._head_meta(f)
            if ts:
                if first_ts is None or ts < first_ts:
                    first_ts = ts
                if last_ts is None or ts > last_ts:
                    last_ts = ts
            if cwd is None:
                cwd = file_cwd
        return cwd, first_ts, last_ts, session_count

    # ---- Sessions ----

    def list_sessions(self, project_id: str) -> list:
        sessions = []
        for sid, (f, archived) in self._session_files(project_id).items():
            title, timestamp, msg_count = self._session_meta(f)
            key = _stat_key(f)
            sessions.append({
                "id": sid,
                "title": title,
                "timestamp": timestamp,
                "message_count": msg_count,
                "archived": archived,
                # 本体の JSONL の大きさ。サブエージェントや保管庫の世代は含まない
                "size": key[0] if key else 0,
            })
        sessions.sort(key=lambda x: x["timestamp"] or "", reverse=True)
        self._cache.save()
        return sessions

    # ---- Messages ----

    def get_messages(self, project_id: str, session_id: str) -> list:
        f = next((p for p in (d / f"{session_id}.jsonl" for _, d in self._project_dirs(project_id))
                  if p.exists()), None)
        if f is None:
            return []
        key = _stat_key(f)
        with self._messages_lock:
            hit = self._messages.get(f)
            if hit and hit[0] == key:
                self._messages.move_to_end(f)
                return hit[1]
        messages = self._read_messages(f, session_id)
        with self._messages_lock:
            self._messages[f] = (key, messages)
            self._messages.move_to_end(f)
            while len(self._messages) > self.MESSAGE_CACHE_SIZE:
                self._messages.popitem(last=False)
        return messages

    def forget(self, paths) -> None:
        """ゴミ箱に移したファイルを覚えていたら忘れる"""
        with self._messages_lock:
            for p in paths:
                self._messages.pop(Path(p), None)

    @staticmethod
    def _read_messages(f: Path, session_id: str) -> list:
        messages = []
        with open(f, encoding="utf-8", errors="replace") as fp:
            for line in fp:
                if not _maybe_message(line):
                    continue
                line = line.strip()
                try:
                    obj = json.loads(line)
                    if obj.get("type") not in ("user", "assistant"):
                        continue
                    # Skip lines that belong to a different session (cross-session contamination)
                    if obj.get("sessionId") and obj.get("sessionId") != session_id:
                        continue
                    # Skill の展開文は isMeta なので _process_message が落とす。以前は「Skill の直後の user 行」という
                    # 位置で落としていたが、展開文が isMeta で先に消えると、次の本物の発言を落としてしまう
                    msg = _process_message(obj)
                    if msg:
                        messages.append(msg)
                except Exception:
                    pass
        return messages

    # ---- Search ----

    def search(self, query: str, project_id: str = None, search_type: str = "text", max_results: int = 300) -> list:
        q = query.lower()
        results = []
        dir_map = self._dir_map()
        proj_ids = [project_id] if project_id else [dirs[0][1].name for dirs in dir_map.values()]
        # 件数の上限で打ち切るので、新しいセッションから探す
        targets = [(proj_id, sid, f) for proj_id in proj_ids
                   for sid, (f, _) in self._session_files(proj_id, dir_map).items()]
        targets.sort(key=lambda t: self._session_meta(t[2])[1] or "", reverse=True)
        from .search_index import find
        for proj_id, session_id, f in targets:
            hits = find(self._index.entries(f), q, search_type)
            if hits:
                title = self._session_meta(f)[0]
                for h in hits:
                    h.update({"project_id": proj_id, "session_id": session_id, "session_title": title})
                results += hits
            if len(results) >= max_results:
                break
        self._cache.save()
        self._index.save()
        return results

    def warm_up(self) -> None:
        """全部のセッションの一覧用の情報と検索の索引を作っておく（起動直後に裏のスレッドで呼ぶ）。
        前に作ったものがファイルに残っていれば、変わったセッションだけを読む"""
        dir_map = self._dir_map()
        for dirs in dir_map.values():
            for f, _ in self._session_files(dirs[0][1].name, dir_map).values():
                self._head_meta(f)
                self._session_meta(f)
                self._index.entries(f)
        self._cache.save()
        self._index.save(force=True)
