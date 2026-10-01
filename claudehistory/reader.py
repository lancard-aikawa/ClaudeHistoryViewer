import json
import re
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

def _read_session_meta(path: Path) -> tuple:
    title = path.stem
    timestamp = None
    msg_count = 0
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                t = obj.get("type")
                if t == "ai-title":
                    title = obj.get("aiTitle", title)
                elif t in ("user", "assistant"):
                    msg_count += 1
                    if timestamp is None:
                        timestamp = obj.get("timestamp")
    except Exception:
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

def _search_message(obj: dict, query: str, search_type: str) -> dict | None:
    role = obj.get("type", "")
    uuid = obj.get("uuid", "")
    timestamp = obj.get("timestamp", "")
    content = obj.get("message", {}).get("content", [])
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]

    if search_type == "file":
        for block in (content if isinstance(content, list) else []):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                inp = block.get("input", {})
                fp = inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or ""
                if query in fp.lower():
                    return {"role": role, "uuid": uuid, "timestamp": timestamp,
                            "snippet": f"📄 {fp}", "match_type": "file"}
    else:
        full_text = ""
        for block in (content if isinstance(content, list) else []):
            if isinstance(block, dict) and block.get("type") == "text":
                full_text += block.get("text", "") + " "
        if isinstance(content, str):
            full_text = content
        if query in full_text.lower():
            idx = full_text.lower().find(query)
            s = max(0, idx - 60)
            e = min(len(full_text), idx + len(query) + 120)
            snippet = ("…" if s > 0 else "") + full_text[s:e] + ("…" if e < len(full_text) else "")
            return {"role": role, "uuid": uuid, "timestamp": timestamp,
                    "snippet": snippet, "match_type": "text"}
    return None


class ClaudeDataReader:
    def __init__(self, claude_dir: Path, backup_roots: list | None = None):
        self.claude_dir = claude_dir
        self.projects_dir = claude_dir / "projects"
        # バックアップ（SessionVault の mirror や、内蔵のバックアップ）。projects と同じ木の形。
        # 元のファイルが消えてもここから読む
        self.backup_roots = list(backup_roots or [])
        # {path: ((size, mtime_ns), (cwd, timestamp))}。変わっていないファイルは読み直さない
        self._head_cache = {}

    def _head_meta(self, path: Path) -> tuple:
        try:
            st = path.stat()
        except OSError:
            return None, None
        key = (st.st_size, st.st_mtime_ns)
        hit = self._head_cache.get(path)
        if hit and hit[0] == key:
            return hit[1]
        meta = _read_head_meta(path)
        self._head_cache[path] = (key, meta)
        return meta

    def _roots(self) -> list:
        """読み込み元。先に書いた方が優先（元のファイル > バックアップ）"""
        return [self.projects_dir, *self.backup_roots]

    def _project_ids(self) -> list:
        """プロジェクトのフォルダ名。C--x と c--x は同じプロジェクト（Claude Code が大文字・小文字を揺らす）。
        先に見つけた綴りを使う"""
        ids = {}
        for root in self._roots():
            if root.is_dir():
                for d in root.iterdir():
                    if d.is_dir():
                        ids.setdefault(d.name.casefold(), d.name)
        return list(ids.values())

    def _project_dirs(self, project_id: str) -> list:
        """[(root の番号, そのプロジェクトのフォルダ)]。大文字・小文字を無視して探す"""
        key = project_id.casefold()
        out = []
        for i, root in enumerate(self._roots()):
            if root.is_dir():
                out += [(i, d) for d in root.iterdir() if d.is_dir() and d.name.casefold() == key]
        return out

    def _session_files(self, project_id: str) -> dict:
        """{session_id: (path, archived_only)} を返す。同じ ID は元のファイルを優先"""
        files = {}
        for i, proj_dir in self._project_dirs(project_id):
            for f in proj_dir.glob("*.jsonl"):
                if _is_session_file(f.stem) and f.stem not in files:
                    files[f.stem] = (f, i > 0)
        return files

    # ---- Projects ----

    def list_projects(self) -> list:
        projects = []
        for proj_id in self._project_ids():
            cwd, first_ts, last_ts, session_count = self._project_summary(proj_id)
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

    def _project_summary(self, project_id: str):
        cwd = None
        first_ts = None
        last_ts = None
        session_count = 0
        for f, _ in self._session_files(project_id).values():
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
            title, timestamp, msg_count = _read_session_meta(f)
            sessions.append({
                "id": sid,
                "title": title,
                "timestamp": timestamp,
                "message_count": msg_count,
                "archived": archived,
            })
        sessions.sort(key=lambda x: x["timestamp"] or "", reverse=True)
        return sessions

    # ---- Messages ----

    def get_messages(self, project_id: str, session_id: str) -> list:
        f = next((p for p in (d / f"{session_id}.jsonl" for _, d in self._project_dirs(project_id))
                  if p.exists()), None)
        if f is None:
            return []
        messages = []
        with open(f, encoding="utf-8", errors="replace") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
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

        proj_ids = [project_id] if project_id else self._project_ids()

        for proj_id in proj_ids:
            for session_id, (f, _) in self._session_files(proj_id).items():
                title = session_id
                hits = []
                with open(f, encoding="utf-8", errors="replace") as fp:
                    for line in fp:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                            if obj.get("type") == "ai-title":
                                title = obj.get("aiTitle", title)
                            elif obj.get("type") in ("user", "assistant"):
                                # 画面に出さない行 (isMeta・通知・タグだけの行) は探さない
                                shown = _process_message(obj)
                                if not shown or shown["role"] != obj.get("type"):
                                    continue
                                hit = _search_message(obj, q, search_type)
                                if hit:
                                    hit.update({"project_id": proj_id, "session_id": session_id})
                                    hits.append(hit)
                        except Exception:
                            pass
                for h in hits:
                    h["session_title"] = title
                    results.append(h)
                if len(results) >= max_results:
                    return results
        return results
