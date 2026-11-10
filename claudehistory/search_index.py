"""全文検索の索引

セッションの JSONL は数 GB になり、毎回全部を読むと検索に十数秒かかった（2026-11-10、2.6 GB・640 セッションで 11 秒）。
大半は api-request-blob やツール結果の画像で、検索に使う文字（画面に出す発言の本文と、ツールで触ったファイルのパス）は
0.6% ほどしかない。それだけを抜き出して覚えておき、次に起動したときも使えるようファイルに書く。

セッションは後ろに追記されて伸びるので、伸びた分だけ読み足す。縮んだり、読み終えた所の手前が変わっていたりしたら
（SessionVault の mirror が別の版に置き換わったときなど）、初めから読み直す。
"""
import json
import os
import threading
import time
from pathlib import Path

from .reader import _process_message

# 発言の行の印（reader._MSG_MARKERS のバイト列版）
_MARKERS = tuple(m.encode() for m in ('"type":"user"', '"type":"assistant"', '"type": "user"', '"type": "assistant"'))
# 読み終えた所の手前が変わっていないかを見るための長さ
_PROBE = 256


def _entry(obj: dict) -> list | None:
    """[role, uuid, timestamp, 本文, [ファイルのパス]]。画面に出さない行（isMeta・通知・タグだけの行）は None"""
    role = obj.get("type")
    if role not in ("user", "assistant"):
        return None
    shown = _process_message(obj)
    if not shown or shown["role"] != role:
        return None
    content = obj.get("message", {}).get("content", [])
    texts, files = [], []
    if isinstance(content, str):
        texts.append(content)
    elif isinstance(content, list):
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                texts.append(b.get("text", ""))
            elif b.get("type") == "tool_use":
                inp = b.get("input", {})
                fp = inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or ""
                if isinstance(fp, str) and fp:
                    files.append(fp)
    return [role, obj.get("uuid", ""), obj.get("timestamp", ""), " ".join(texts), files]


def _probe(fp, offset: int) -> str:
    start = max(0, offset - _PROBE)
    fp.seek(start)
    return fp.read(offset - start).hex()


def _read_from(path: Path, offset: int) -> tuple[list, int, str]:
    """offset から後ろの、改行で終わる行を読む。(項目, 読み終えた位置, 読み終えた所の手前のバイト列)。
    書きかけの最後の行は読まずに残し、次に読み足す"""
    entries = []
    with open(path, "rb") as fp:
        fp.seek(offset)
        pos = offset
        for line in fp:
            if not line.endswith(b"\n"):
                break
            pos += len(line)
            if not any(m in line for m in _MARKERS):
                continue
            try:
                obj = json.loads(line.decode("utf-8", errors="replace"))
            except ValueError:
                continue
            if isinstance(obj, dict):
                e = _entry(obj)
                if e:
                    entries.append(e)
        return entries, pos, _probe(fp, pos)


class SearchIndex:
    VERSION = 1
    SAVE_INTERVAL = 60  # 秒。使っているセッションは検索のたびに伸びるので、書き出しは間を空ける

    def __init__(self, path: Path | None = None):
        self.path = path
        # {パス: {"key": [サイズ, 更新時刻], "offset": 読み終えた位置, "probe": その手前, "entries": [...]}}
        self._files: dict = {}
        self._lock = threading.Lock()
        self._dirty = False
        self._saved_at = 0.0
        if path and path.is_file():
            try:
                with open(path, encoding="utf-8") as f:
                    saved = json.load(f)
                if saved.get("version") == self.VERSION:
                    self._files = saved.get("files", {})
            except (OSError, ValueError):
                pass

    def entries(self, path: Path) -> list:
        """path の項目。前に読んだときから変わっていれば読み足す"""
        name = str(path)
        try:
            st = path.stat()
        except OSError:
            return []
        key = [st.st_size, st.st_mtime_ns]
        with self._lock:
            state = self._files.get(name)
            if state and state["key"] == key:
                return state["entries"]
            try:
                if state and st.st_size >= state["offset"] and self._same_prefix(path, state):
                    new, pos, probe = _read_from(path, state["offset"])
                    state = {"key": key, "offset": pos, "probe": probe, "entries": state["entries"] + new}
                else:
                    new, pos, probe = _read_from(path, 0)
                    state = {"key": key, "offset": pos, "probe": probe, "entries": new}
            except OSError:
                return state["entries"] if state else []
            self._files[name] = state
            self._dirty = True
            return state["entries"]

    @staticmethod
    def _same_prefix(path: Path, state: dict) -> bool:
        try:
            with open(path, "rb") as fp:
                return _probe(fp, state["offset"]) == state["probe"]
        except OSError:
            return False

    def save(self, force: bool = False) -> None:
        if not self.path or not self._dirty:
            return
        if not force and time.monotonic() - self._saved_at < self.SAVE_INTERVAL:
            return
        with self._lock:
            self._files = {k: v for k, v in self._files.items() if os.path.exists(k)}
            data = json.dumps({"version": self.VERSION, "files": self._files}, ensure_ascii=False)
            self._dirty = False
            self._saved_at = time.monotonic()
        try:
            tmp = self.path.with_name(self.path.name + ".tmp")
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(data)
            os.replace(tmp, self.path)
        except OSError:
            pass


def find(entries: list, q: str, search_type: str) -> list:
    """q（小文字）を含む項目を、画面に出す形の dict にして返す"""
    hits = []
    for role, uuid, ts, text, files in entries:
        if search_type == "file":
            fp = next((p for p in files if q in p.lower()), None)
            if fp is not None:
                hits.append({"role": role, "uuid": uuid, "timestamp": ts,
                             "snippet": f"📄 {fp}", "match_type": "file"})
            continue
        idx = text.lower().find(q)
        if idx < 0:
            continue
        s = max(0, idx - 60)
        e = min(len(text), idx + len(q) + 120)
        snippet = ("…" if s > 0 else "") + text[s:e] + ("…" if e < len(text) else "")
        hits.append({"role": role, "uuid": uuid, "timestamp": ts, "snippet": snippet, "match_type": "text"})
    return hits
