#!/usr/bin/env python3
"""
Claude History Viewer - LINEライクな Claude Code セッションビューア
Usage: python claude_chat_viewer.py [--port 8080] [--claude-dir ~/.claude]
"""

import argparse
import json
import os
import re
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote

DEFAULT_PORT = 8080
DEFAULT_CLAUDE_DIR = Path.home() / ".claude"
META_FILENAME = "chat-viewer-meta.json"
SETTINGS_FILE = Path(__file__).parent / "settings.json"

SETTINGS_DEFAULTS: dict = {
    # ── 起動設定（再起動後に反映） ──────────────────
    "port": 8080,                 # ポート番号
    "auto_open_browser": True,    # 起動時にブラウザを自動で開く

    # ── 表示設定（再起動後に反映） ──────────────────
    "collapse_lines": 15,         # これ以上の行数で折りたたむ
    "collapse_chars": 600,        # これ以上の文字数で折りたたむ（行数より先に達した場合も折りたたむ）
    "preview_chars":  300,        # 折りたたみ時に表示するプレビュー文字数
    "show_timestamp":  True,       # メッセージの時刻を表示する
    "show_thinking":   True,      # 思考プロセスブロックを表示する
    "show_tool_chips": True,      # ツール呼び出しチップを表示する
    "max_search_results": 300,    # 検索結果の最大件数
}

def load_settings() -> dict:
    """settings.json を読み込んでデフォルト値とマージして返す"""
    cfg = dict(SETTINGS_DEFAULTS)
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                user = json.load(f)
            # 既知キーのみ上書き（型チェックも行う）
            for k, default in SETTINGS_DEFAULTS.items():
                if k in user and type(user[k]) is type(default):
                    cfg[k] = user[k]
        except Exception as e:
            print(f"Warning: settings.json の読み込みに失敗しました: {e}", file=sys.stderr)
    return cfg


# ── Data Layer ──────────────────────────────────────────────────────────────

class ClaudeDataReader:
    def __init__(self, claude_dir: Path):
        self.claude_dir = claude_dir
        self.projects_dir = claude_dir / "projects"

    # ---- Projects ----

    def list_projects(self) -> list:
        if not self.projects_dir.exists():
            return []
        projects = []
        for proj_dir in self.projects_dir.iterdir():
            if not proj_dir.is_dir():
                continue
            cwd, last_ts, session_count = self._project_summary(proj_dir)
            if session_count == 0:
                continue
            projects.append({
                "id": proj_dir.name,
                "cwd": cwd or proj_dir.name,
                "session_count": session_count,
                "last_activity": last_ts,
            })
        projects.sort(key=lambda x: x["last_activity"] or "", reverse=True)
        return projects

    def _project_summary(self, proj_dir: Path):
        cwd = None
        last_ts = None
        session_count = 0
        for f in proj_dir.glob("*.jsonl"):
            if not _is_session_file(f.stem):
                continue
            session_count += 1
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat()
            if last_ts is None or mtime > last_ts:
                last_ts = mtime
            if cwd is None:
                cwd = _read_cwd(f)
        return cwd, last_ts, session_count

    # ---- Sessions ----

    def list_sessions(self, project_id: str) -> list:
        proj_dir = self.projects_dir / project_id
        if not proj_dir.is_dir():
            return []
        sessions = []
        for f in proj_dir.glob("*.jsonl"):
            if not _is_session_file(f.stem):
                continue
            title, timestamp, msg_count = _read_session_meta(f)
            sessions.append({
                "id": f.stem,
                "title": title,
                "timestamp": timestamp,
                "message_count": msg_count,
            })
        sessions.sort(key=lambda x: x["timestamp"] or "", reverse=True)
        return sessions

    # ---- Messages ----

    def get_messages(self, project_id: str, session_id: str) -> list:
        f = self.projects_dir / project_id / f"{session_id}.jsonl"
        if not f.exists():
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
                    msg = _process_message(obj)
                    if msg:
                        messages.append(msg)
                except Exception:
                    pass
        return messages

    # ---- Search ----

    def search(self, query: str, project_id: str = None, search_type: str = "text") -> list:
        q = query.lower()
        results = []

        if project_id:
            dirs = [(project_id, self.projects_dir / project_id)]
        else:
            dirs = [(d.name, d) for d in self.projects_dir.iterdir() if d.is_dir()]

        for proj_id, proj_dir in dirs:
            for f in proj_dir.glob("*.jsonl"):
                if not _is_session_file(f.stem):
                    continue
                session_id = f.stem
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
                                hit = _search_message(obj, q, search_type)
                                if hit:
                                    hit.update({"project_id": proj_id, "session_id": session_id})
                                    hits.append(hit)
                        except Exception:
                            pass
                for h in hits:
                    h["session_title"] = title
                    results.append(h)
                if len(results) >= 300:
                    return results
        return results


# ── MetaStore ───────────────────────────────────────────────────────────────

class MetaStore:
    def __init__(self, path: Path):
        self.path = path
        self._data: dict | None = None

    def _load(self) -> dict:
        if self._data is None:
            if self.path.exists():
                try:
                    with open(self.path, encoding="utf-8") as f:
                        self._data = json.load(f)
                except Exception:
                    self._data = {}
            else:
                self._data = {}
        return self._data

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get_all(self) -> dict:
        return self._load()

    def set_session(self, project_id: str, session_id: str, meta: dict):
        d = self._load()
        d.setdefault("sessions", {})[f"{project_id}/{session_id}"] = meta
        self._save()

    def set_message(self, uuid: str, meta: dict):
        d = self._load()
        d.setdefault("messages", {})[uuid] = meta
        self._save()

    def get_starred(self) -> dict:
        d = self._load()
        sessions = [
            {"project_id": k.split("/")[0], "session_id": k.split("/", 1)[1], **v}
            for k, v in d.get("sessions", {}).items() if v.get("starred")
        ]
        messages = [
            {"uuid": k, **v}
            for k, v in d.get("messages", {}).items() if v.get("starred")
        ]
        return {"sessions": sessions, "messages": messages}


# ── Helper functions ─────────────────────────────────────────────────────────

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

def _process_message(obj: dict) -> dict | None:
    role = obj.get("type")
    raw_content = obj.get("message", {}).get("content", [])

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
            # Filter out ide_opened_file system injections
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
            if isinstance(inner, list):
                for item in inner:
                    if isinstance(item, dict) and item.get("type") == "image":
                        src = item.get("source", {})
                        images.append({
                            "media_type": src.get("media_type", "image/png"),
                            "data": src.get("data", ""),
                        })

    # Skip user messages that are only tool results (no real text)
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
        cmd = inp.get("command", "")
        description = cmd[:100]
    elif name in ("WebFetch", "WebSearch"):
        description = (inp.get("url") or inp.get("query") or "")[:80]
    elif name == "Agent":
        description = inp.get("description") or inp.get("prompt", "")[:60]
    else:
        for v in inp.values():
            if isinstance(v, str) and v:
                description = v[:80]
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


# ── HTTP Server ──────────────────────────────────────────────────────────────

def make_handler(reader: ClaudeDataReader, meta: MetaStore, cfg: dict):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # suppress default logs

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            if path == "/" or path == "/index.html":
                self._send(200, "text/html; charset=utf-8", HTML_TEMPLATE.encode())
            elif path == "/api/projects":
                self._json(reader.list_projects())
            elif path == "/api/sessions":
                pid = qs.get("project", [""])[0]
                sessions = reader.list_sessions(pid)
                # Merge meta
                all_meta = meta.get_all()
                for s in sessions:
                    key = f"{pid}/{s['id']}"
                    s["meta"] = all_meta.get("sessions", {}).get(key, {})
                self._json(sessions)
            elif path == "/api/messages":
                pid = qs.get("project", [""])[0]
                sid = qs.get("session", [""])[0]
                msgs = reader.get_messages(pid, sid)
                all_meta = meta.get_all()
                for m in msgs:
                    m["meta"] = all_meta.get("messages", {}).get(m["uuid"], {})
                self._json(msgs)
            elif path == "/api/search":
                q = qs.get("q", [""])[0]
                pid = qs.get("project", [""])[0] or None
                stype = qs.get("type", ["text"])[0]
                results = reader.search(q, pid, stype) if q else []
                self._json(results)
            elif path == "/api/starred":
                self._json(meta.get_starred())
            elif path == "/api/meta":
                self._json(meta.get_all())
            elif path == "/api/settings":
                # 起動設定（port等）はブラウザ側に渡さない
                pub = {k: v for k, v in cfg.items() if k not in ("port", "auto_open_browser")}
                self._json(pub)
            else:
                self._send(404, "text/plain", b"Not Found")

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)

            try:
                data = json.loads(body)
            except Exception:
                self._send(400, "text/plain", b"Bad JSON")
                return

            if path == "/api/meta/session":
                meta.set_session(data["project_id"], data["session_id"], data["meta"])
                self._json({"ok": True})
            elif path == "/api/meta/message":
                meta.set_message(data["uuid"], data["meta"])
                self._json({"ok": True})
            else:
                self._send(404, "text/plain", b"Not Found")

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def _json(self, data):
            body = json.dumps(data, ensure_ascii=False).encode()
            self._send(200, "application/json; charset=utf-8", body)

        def _send(self, code, ct, body):
            self.send_response(code)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", len(body))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

    return Handler


# ── HTML / CSS / JS ──────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Claude History Viewer</title>
<style>
/* ── Variables ── */
:root {
  --bg: #f0f2f5;
  --sidebar-bg: #ffffff;
  --header-bg: #6366f1;
  --bubble-user: #6366f1;
  --bubble-user-text: #ffffff;
  --bubble-ai: #ffffff;
  --bubble-ai-text: #1a1a2e;
  --bubble-tool: #f0f4ff;
  --bubble-tool-text: #4b5563;
  --thinking-bg: #fef9c3;
  --thinking-text: #78350f;
  --border: #e5e7eb;
  --text: #1f2937;
  --text-muted: #6b7280;
  --accent: #6366f1;
  --accent-hover: #4f46e5;
  --tag-bg: #e0e7ff;
  --tag-text: #4338ca;
  --star-color: #f59e0b;
  --search-bg: #f9fafb;
  --chip-bg: #e5e7eb;
  --chip-text: #374151;
  --session-active: #ede9fe;
  --session-hover: #f5f3ff;
  --shadow: 0 1px 3px rgba(0,0,0,.1);
  --font-size: 14px;
  --radius: 18px;
  --font-family: 'Cascadia Code','Cascadia Mono',Consolas,'BIZ UDGothic','Noto Sans Mono',monospace;
}
[data-theme="dark"] {
  --bg: #0f1117;
  --sidebar-bg: #1a1d27;
  --header-bg: #312e81;
  --bubble-user: #4f46e5;
  --bubble-user-text: #ffffff;
  --bubble-ai: #1e2131;
  --bubble-ai-text: #e2e8f0;
  --bubble-tool: #1a2040;
  --bubble-tool-text: #94a3b8;
  --thinking-bg: #2d2208;
  --thinking-text: #fde68a;
  --border: #2d3148;
  --text: #e2e8f0;
  --text-muted: #9ca3af;
  --accent: #818cf8;
  --accent-hover: #6366f1;
  --tag-bg: #1e1b4b;
  --tag-text: #a5b4fc;
  --star-color: #fbbf24;
  --search-bg: #1a1d27;
  --chip-bg: #2d3148;
  --chip-text: #cbd5e1;
  --session-active: #1e1b4b;
  --session-hover: #1a1d35;
  --shadow: 0 1px 3px rgba(0,0,0,.4);
}
/* ── Reset ── */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;font-family:var(--font-family);font-size:var(--font-size);background:var(--bg);color:var(--text)}
button{cursor:pointer;border:none;background:none;font:inherit;color:inherit}
input{font:inherit;color:inherit}
/* ── Layout ── */
#app{display:flex;flex-direction:column;height:100vh;overflow:hidden}
#header{background:var(--header-bg);color:#fff;display:flex;align-items:center;gap:8px;padding:0 16px;height:52px;flex-shrink:0}
#header h1{font-size:16px;font-weight:700;flex:1;white-space:nowrap}
.hbtn{padding:6px 10px;border-radius:8px;color:#fff;opacity:.85;transition:opacity .15s,background .15s;font-size:13px}
.hbtn:hover{opacity:1;background:rgba(255,255,255,.15)}
.hbtn.active{opacity:1;background:rgba(255,255,255,.25)}
#font-select{padding:5px 8px;border-radius:8px;border:none;background:rgba(255,255,255,.15);color:#fff;font-size:12px;cursor:pointer;opacity:.85}
#font-select:hover{opacity:1;background:rgba(255,255,255,.25)}
#font-select option{background:#312e81;color:#fff}
#main{display:flex;flex:1;overflow:hidden}
/* ── Sidebar ── */
#sidebar{width:280px;min-width:200px;max-width:380px;background:var(--sidebar-bg);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;flex-shrink:0}
#sidebar-header{padding:12px 14px 8px;border-bottom:1px solid var(--border);flex-shrink:0}
#sidebar-search{width:100%;padding:6px 10px;border-radius:8px;border:1px solid var(--border);background:var(--search-bg);color:var(--text);font-size:13px;outline:none}
#sidebar-search:focus{border-color:var(--accent)}
#project-list{flex:1;overflow-y:auto;padding:6px 0}
.proj-header{display:flex;align-items:center;gap:6px;padding:9px 12px 9px 14px;cursor:pointer;user-select:none;border-bottom:1px solid var(--border);margin-top:2px}
.proj-header:first-child{margin-top:0}
.proj-header:hover{background:var(--session-hover)}
.proj-header.open{border-bottom-color:transparent}
.proj-caret{font-size:10px;transition:transform .15s;display:inline-block;color:var(--text-muted);flex-shrink:0}
.proj-header.open .proj-caret{transform:rotate(90deg)}
.proj-icon{font-size:13px;flex-shrink:0}
.proj-name{font-weight:700;font-size:12px;color:var(--text);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;letter-spacing:.01em}
.proj-count{font-size:10px;color:var(--text-muted);background:var(--chip-bg);padding:1px 6px;border-radius:8px;flex-shrink:0}
.session-list{display:none;padding:4px 8px 8px 20px;border-left:2px solid var(--border);margin:0 0 4px 18px}
.session-list.open{display:block}
.sess-item{padding:6px 8px;border-radius:6px;cursor:pointer;transition:background .1s;margin-bottom:1px}
.sess-item:hover{background:var(--session-hover)}
.sess-item.active{background:var(--session-active)}
.sess-title{font-size:12px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sess-meta{display:flex;align-items:center;gap:6px;margin-top:2px}
.sess-date{font-size:11px;color:var(--text-muted)}
.sess-count{font-size:11px;color:var(--text-muted)}
.sess-star{color:var(--star-color);font-size:11px}
.sess-tags{display:flex;gap:3px;flex-wrap:wrap}
.tag-chip{font-size:10px;background:var(--tag-bg);color:var(--tag-text);padding:1px 6px;border-radius:10px}
/* ── Chat pane ── */
#chat-pane{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}
#chat-header{padding:10px 16px;border-bottom:1px solid var(--border);background:var(--sidebar-bg);flex-shrink:0;display:flex;align-items:center;gap:8px}
#session-title{font-weight:600;font-size:14px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#chat-messages{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px}
#chat-empty{display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);font-size:14px;text-align:center;flex-direction:column;gap:8px}
#chat-empty .icon{font-size:48px}
/* ── Compaction notice ── */
.compaction-notice{display:flex;align-items:center;justify-content:center;padding:6px 0 2px}
.compaction-notice span{font-size:12px;color:var(--text-muted);background:var(--bg);border:1px solid var(--border);border-radius:12px;padding:3px 12px}
/* ── Plan block ── */
.plan-block{margin:4px 0;border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;background:var(--sidebar-bg)}
.plan-block summary{display:flex;align-items:center;gap:6px;padding:8px 12px;cursor:pointer;font-size:12px;color:var(--text-muted);user-select:none;list-style:none}
.plan-block summary::marker{display:none}
.plan-block summary:hover{background:var(--session-hover)}
.plan-block-body{padding:10px 14px;border-top:1px solid var(--border);max-height:400px;overflow-y:auto}
.plan-block-body .bubble-text{font-size:13px}
/* ── Bubbles ── */
.msg-row{display:flex;flex-direction:column;gap:4px}
.msg-row.user{align-items:flex-end}
.msg-row.assistant{align-items:flex-start}
.msg-ts{font-size:11px;color:var(--text-muted);padding:0 4px}
.msg-ts.hidden{display:none}
.bubble{max-width:72%;padding:10px 14px;border-radius:var(--radius);word-break:break-word;position:relative}
.msg-row.user .bubble{background:var(--bubble-user);color:var(--bubble-user-text);border-bottom-right-radius:4px}
.msg-row.assistant .bubble{background:var(--bubble-ai);color:var(--bubble-ai-text);border-bottom-left-radius:4px;box-shadow:var(--shadow)}
.bubble-text{line-height:1.6;white-space:normal}
.bubble-text p{margin:0 0 .6em}
.bubble-text p:last-child{margin-bottom:0}
.bubble-text code{background:rgba(0,0,0,.1);padding:1px 4px;border-radius:4px;font-size:.9em;font-family:'Cascadia Code','Fira Code',monospace}
.msg-row.user .bubble-text code{background:rgba(255,255,255,.2)}
.bubble-text pre{background:rgba(0,0,0,.12);padding:8px 10px;border-radius:8px;overflow-x:auto;margin:.4em 0}
.msg-row.user .bubble-text pre{background:rgba(255,255,255,.15)}
.bubble-text pre code{background:none;padding:0}
.bubble-text h1{font-size:1.1em;font-weight:700;margin:.5em 0 .15em}.bubble-text h2{font-size:1.05em;font-weight:700;margin:.4em 0 .15em}.bubble-text h3{font-size:1em;font-weight:700;margin:.35em 0 .1em}.bubble-text h1:first-child,.bubble-text h2:first-child,.bubble-text h3:first-child{margin-top:.1em}
.bubble-text ul,.bubble-text ol{padding-left:1.4em;margin:.3em 0}
.bubble-text li{margin:.15em 0}
.bubble-text strong{font-weight:700}
.bubble-text em{font-style:italic}
.bubble-text a{color:inherit;opacity:.8;text-decoration:underline}
/* Tables */
.md-table-wrap{overflow-x:auto;margin:.5em 0;border-radius:6px}
.md-table{border-collapse:collapse;width:100%;font-size:.93em}
.md-table th,.md-table td{border:1px solid rgba(0,0,0,.15);padding:5px 10px;white-space:nowrap;line-height:1.4}
.md-table th{background:rgba(0,0,0,.06);font-weight:600}
.md-table tr:nth-child(even) td{background:rgba(0,0,0,.025)}
.msg-row.user .md-table th,.msg-row.user .md-table td{border-color:rgba(255,255,255,.3)}
.msg-row.user .md-table th{background:rgba(255,255,255,.18)}
.msg-row.user .md-table tr:nth-child(even) td{background:rgba(255,255,255,.08)}
[data-theme="dark"] .md-table th{background:rgba(255,255,255,.07)}
[data-theme="dark"] .md-table th,[data-theme="dark"] .md-table td{border-color:rgba(255,255,255,.1)}
/* Collapsed long messages */
.msg-collapse{margin-top:6px}
.msg-collapse summary{font-size:12px;color:var(--accent);cursor:pointer;user-select:none;list-style:none;padding:2px 0}
.msg-row.user .msg-collapse summary{color:rgba(255,255,255,.7)}
.msg-collapse summary::marker{display:none}
.msg-collapse[open]>summary{display:none}
.collapse-bottom-btn{margin-top:8px;font-size:12px;color:var(--accent);cursor:pointer;user-select:none;padding:2px 0}
.msg-row.user .collapse-bottom-btn{color:rgba(255,255,255,.7)}
/* Thinking */
.thinking-block{margin-top:6px;background:var(--thinking-bg);border-radius:10px;overflow:hidden}
.thinking-summary{padding:6px 10px;cursor:pointer;font-size:12px;color:var(--thinking-text);user-select:none;display:flex;align-items:center;gap:6px}
.thinking-summary::marker{display:none}
.thinking-content{padding:8px 10px;font-size:12px;color:var(--thinking-text);white-space:pre-wrap;max-height:300px;overflow-y:auto;border-top:1px solid rgba(0,0,0,.08)}
/* Tool chips */
.tool-chips{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
.tool-chip{display:inline-flex;align-items:center;gap:4px;font-size:11px;padding:3px 8px;border-radius:10px;background:var(--chip-bg);color:var(--chip-text);max-width:220px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.tool-icon{flex-shrink:0}
/* Images */
.msg-images{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.msg-images img{max-width:200px;max-height:150px;border-radius:8px;cursor:pointer;border:1px solid var(--border)}
/* Message toolbar */
.msg-toolbar{display:flex;gap:4px;margin-top:4px;visibility:hidden}
.msg-row:hover .msg-toolbar{visibility:visible}
.tbtn{font-size:14px;padding:2px 5px;border-radius:6px;opacity:.6;transition:opacity .1s}
.tbtn:hover{opacity:1;background:var(--chip-bg)}
.tbtn.active{opacity:1;color:var(--star-color)}
/* ── Search panel ── */
#search-panel{position:fixed;inset:0;z-index:100;display:flex;align-items:flex-start;justify-content:center;padding-top:60px;background:rgba(0,0,0,.4);display:none}
#search-panel.open{display:flex}
#search-box{background:var(--sidebar-bg);border-radius:12px;width:640px;max-width:90vw;max-height:80vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.3)}
#search-input-row{display:flex;gap:8px;padding:12px 14px;border-bottom:1px solid var(--border);align-items:center}
#search-input{flex:1;padding:8px 12px;border-radius:8px;border:1px solid var(--border);background:var(--search-bg);font-size:14px;outline:none}
#search-input:focus{border-color:var(--accent)}
#search-type{padding:6px 8px;border-radius:8px;border:1px solid var(--border);background:var(--search-bg);font-size:13px;color:var(--text)}
#search-scope{padding:6px 8px;border-radius:8px;border:1px solid var(--border);background:var(--search-bg);font-size:13px;color:var(--text)}
#search-results{overflow-y:auto;flex:1;padding:8px}
.sr-item{padding:10px 12px;border-radius:8px;cursor:pointer;border-bottom:1px solid var(--border)}
.sr-item:last-child{border-bottom:none}
.sr-item:hover{background:var(--session-hover)}
.sr-session{font-size:11px;color:var(--accent);font-weight:600;margin-bottom:3px}
.sr-snippet{font-size:13px;color:var(--text);line-height:1.5}
.sr-role{font-size:10px;color:var(--text-muted);margin-top:2px}
.sr-empty{padding:20px;text-align:center;color:var(--text-muted);font-size:13px}
/* ── Starred panel ── */
#starred-panel{position:fixed;inset:0;z-index:100;display:flex;align-items:flex-start;justify-content:center;padding-top:60px;background:rgba(0,0,0,.4);display:none}
#starred-panel.open{display:flex}
#starred-box{background:var(--sidebar-bg);border-radius:12px;width:600px;max-width:90vw;max-height:80vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.3)}
.panel-header{display:flex;align-items:center;padding:12px 16px;border-bottom:1px solid var(--border);font-weight:600;font-size:15px}
.panel-header button{margin-left:auto;opacity:.6;font-size:18px}
.panel-header button:hover{opacity:1}
.panel-body{overflow-y:auto;flex:1;padding:10px}
.starred-section-title{font-size:12px;font-weight:600;color:var(--text-muted);text-transform:uppercase;padding:6px 8px 4px}
.starred-item{padding:8px 10px;border-radius:8px;cursor:pointer;margin-bottom:2px}
.starred-item:hover{background:var(--session-hover)}
.starred-item-title{font-size:13px;font-weight:500}
.starred-item-meta{font-size:11px;color:var(--text-muted);margin-top:2px}
.starred-tags{display:flex;gap:4px;flex-wrap:wrap;margin-top:4px}
/* ── Memo modal ── */
#memo-modal{position:fixed;inset:0;z-index:200;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.5);display:none}
#memo-modal.open{display:flex}
#memo-box{background:var(--sidebar-bg);border-radius:12px;width:400px;max-width:90vw;padding:16px;display:flex;flex-direction:column;gap:12px}
#memo-box h3{font-size:14px;font-weight:600}
#memo-textarea{padding:10px;border-radius:8px;border:1px solid var(--border);background:var(--search-bg);color:var(--text);font-size:13px;resize:vertical;min-height:80px;outline:none}
#memo-textarea:focus{border-color:var(--accent)}
#tag-input{padding:7px 10px;border-radius:8px;border:1px solid var(--border);background:var(--search-bg);color:var(--text);font-size:13px;width:100%;outline:none}
#tag-input:focus{border-color:var(--accent)}
.memo-btns{display:flex;gap:8px;justify-content:flex-end}
.btn{padding:7px 14px;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer;border:none}
.btn-primary{background:var(--accent);color:#fff}
.btn-primary:hover{background:var(--accent-hover)}
.btn-ghost{background:var(--chip-bg);color:var(--text)}
/* ── Image lightbox ── */
#lightbox{position:fixed;inset:0;z-index:300;background:rgba(0,0,0,.85);display:none;align-items:center;justify-content:center;cursor:zoom-out}
#lightbox.open{display:flex}
#lightbox img{max-width:90vw;max-height:90vh;border-radius:8px}
/* ── Scrollbar ── */
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
/* ── Resize handle ── */
#resize-handle{width:4px;cursor:col-resize;background:transparent;flex-shrink:0}
#resize-handle:hover,#resize-handle.dragging{background:var(--accent)}
</style>
</head>
<body>
<div id="app">
  <!-- Header -->
  <div id="header">
    <h1>💬 Claude History Viewer</h1>
    <button class="hbtn" id="btn-search" title="検索 (Ctrl+K)">🔍 検索</button>
    <button class="hbtn" id="btn-starred" title="スター一覧">⭐ スター</button>
    <button class="hbtn" id="btn-ts" title="時刻表示切替">🕐 時刻</button>
    <button class="hbtn" id="btn-theme" title="ダーク/ライト切替">🌙</button>
    <button class="hbtn" id="btn-font-down" title="文字小">A-</button>
    <button class="hbtn" id="btn-font-up" title="文字大">A+</button>
    <select id="font-select" title="フォント選択">
      <option value="auto">Fnt: 自動</option>
      <option value="cascadia-code">Cascadia Code</option>
      <option value="cascadia-mono">Cascadia Mono</option>
      <option value="consolas">Consolas</option>
      <option value="biz-ud">BIZ UDゴシック</option>
      <option value="courier-new">Courier New</option>
      <option value="system">System UI</option>
    </select>
  </div>

  <div id="main">
    <!-- Sidebar -->
    <div id="sidebar">
      <div id="sidebar-header">
        <input id="sidebar-search" type="text" placeholder="セッション名を絞り込み…" />
      </div>
      <div id="project-list"></div>
    </div>

    <div id="resize-handle"></div>

    <!-- Chat pane -->
    <div id="chat-pane">
      <div id="chat-header">
        <span id="session-title">プロジェクトを選択してください</span>
        <button class="tbtn" id="btn-session-star" title="セッションをスター" style="font-size:16px">☆</button>
        <button class="tbtn" id="btn-session-memo" title="メモ・タグ編集" style="font-size:16px">📝</button>
        <button class="tbtn" id="btn-export" title="HTMLとして保存" style="font-size:16px">💾</button>
      </div>
      <div id="chat-messages">
        <div id="chat-empty">
          <div class="icon">💬</div>
          <div>左のサイドバーからセッションを選択してください</div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Search panel -->
<div id="search-panel">
  <div id="search-box">
    <div id="search-input-row">
      <input id="search-input" type="text" placeholder="検索キーワードを入力…" />
      <select id="search-type">
        <option value="text">テキスト</option>
        <option value="file">ファイル名</option>
      </select>
      <select id="search-scope">
        <option value="">全プロジェクト</option>
      </select>
      <button class="tbtn" id="btn-search-close" style="font-size:18px">✕</button>
    </div>
    <div id="search-results"><div class="sr-empty">キーワードを入力して検索</div></div>
  </div>
</div>

<!-- Starred panel -->
<div id="starred-panel">
  <div id="starred-box">
    <div class="panel-header">
      ⭐ スター・タグ一覧
      <button id="btn-starred-close" style="font-size:18px">✕</button>
    </div>
    <div class="panel-body" id="starred-body"></div>
  </div>
</div>

<!-- Memo modal -->
<div id="memo-modal">
  <div id="memo-box">
    <h3>📝 メモ・タグ</h3>
    <textarea id="memo-textarea" placeholder="メモを入力…"></textarea>
    <input id="tag-input" type="text" placeholder="タグ (カンマ区切り、例: 重要, バグ修正)" />
    <div class="memo-btns">
      <button class="btn btn-ghost" id="btn-memo-cancel">キャンセル</button>
      <button class="btn btn-primary" id="btn-memo-save">保存</button>
    </div>
  </div>
</div>

<!-- Lightbox -->
<div id="lightbox"><img id="lightbox-img" src="" alt=""></div>

<script>
// ── State ──
const S = {
  projects: [],
  currentProject: null,
  currentSession: null,
  messages: [],
  meta: { sessions: {}, messages: {} },
  showTs: localStorage.getItem('showTs') !== 'false',
  theme: localStorage.getItem('theme') || 'light',
  fontSize: parseInt(localStorage.getItem('fontSize') || '14'),
  fontKey: localStorage.getItem('fontKey') || 'auto',
  openProjects: new Set(JSON.parse(localStorage.getItem('openProjects') || '[]')),
  memoTarget: null, // { type: 'session'|'message', key, current }
  sidebarFilter: '',
  cfg: { collapse_lines:15, collapse_chars:600, preview_chars:300, show_thinking:true, show_tool_chips:true },
};

// ── API ──
async function api(path) {
  const r = await fetch(path);
  return r.json();
}
async function post(path, data) {
  await fetch(path, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(data) });
}

// ── Init ──
async function init() {
  S.cfg = await api('/api/settings');
  // localStorage に未保存の場合は settings.json の値をデフォルトとして使う
  if (localStorage.getItem('showTs') === null) {
    S.showTs = S.cfg.show_timestamp !== false;
  }
  applyTheme();
  applyFontSize();
  applyFont();
  applyTsBtn();

  S.projects = await api('/api/projects');
  S.meta = await api('/api/meta');
  renderProjects();
  populateSearchScope();

  // open状態のプロジェクトのセッションを並列ロードして描画
  await Promise.all([...S.openProjects].map(async projId => {
    const sl = document.getElementById('sl-' + projId);
    if (!sl) return;
    const sessions = await api(`/api/sessions?project=${encodeURIComponent(projId)}`);
    for (const s of sessions) {
      s.meta = (S.meta.sessions || {})[`${projId}/${s.id}`] || s.meta || {};
    }
    sl.dataset.loaded = '1';
    sl.dataset.sessions = JSON.stringify(sessions);
    renderSessionList(sl, projId, S.sidebarFilter.toLowerCase());
  }));

  // Restore last session
  const last = JSON.parse(localStorage.getItem('lastSession') || 'null');
  if (last) {
    await loadSession(last.project, last.session);
  }
}

// ── Theme / Font / TS ──
function applyTheme() {
  document.documentElement.setAttribute('data-theme', S.theme);
  document.getElementById('btn-theme').textContent = S.theme === 'dark' ? '☀️' : '🌙';
}
function applyFontSize() {
  document.documentElement.style.setProperty('--font-size', S.fontSize + 'px');
}
const FONT_STACKS = {
  'auto':         "'Cascadia Code','Cascadia Mono',Consolas,'BIZ UDGothic','Noto Sans Mono',monospace",
  'cascadia-code':"'Cascadia Code',monospace",
  'cascadia-mono':"'Cascadia Mono',monospace",
  'consolas':     "Consolas,monospace",
  'biz-ud':       "'BIZ UDGothic',monospace",
  'courier-new':  "'Courier New',monospace",
  'system':       "-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
};
function applyFont() {
  const stack = FONT_STACKS[S.fontKey] || FONT_STACKS['auto'];
  document.documentElement.style.setProperty('--font-family', stack);
  const sel = document.getElementById('font-select');
  if (sel) sel.value = S.fontKey;
}
function applyTsBtn() {
  document.getElementById('btn-ts').classList.toggle('active', S.showTs);
  document.querySelectorAll('.msg-ts').forEach(el => el.classList.toggle('hidden', !S.showTs));
}

// ── Project/Session rendering ──
function renderProjects() {
  const filter = S.sidebarFilter.toLowerCase();
  const container = document.getElementById('project-list');
  if (!S.projects.length) {
    container.innerHTML = '<div style="padding:16px;color:var(--text-muted);font-size:13px">プロジェクトが見つかりません</div>';
    return;
  }
  container.innerHTML = '';
  for (const proj of S.projects) {
    const open = S.openProjects.has(proj.id);
    const ph = el('div', 'proj-header' + (open ? ' open' : ''));
    ph.innerHTML = `<span class="proj-caret">▶</span><span class="proj-icon">${open ? '📂' : '📁'}</span><span class="proj-name" title="${esc(proj.cwd)}">${esc(shortPath(proj.cwd))}</span><span class="proj-count">${proj.session_count}</span>`;
    ph.addEventListener('click', () => toggleProject(proj.id));
    container.appendChild(ph);

    const sl = el('div', 'session-list' + (open ? ' open' : ''));
    sl.id = 'sl-' + proj.id;
    // セッションデータは init() 内で非同期ロード後に描画するためここでは行わない
    container.appendChild(sl);
  }
}

async function toggleProject(projId) {
  const sl = document.getElementById('sl-' + projId);
  const ph = sl.previousElementSibling;
  const iconEl = ph.querySelector('.proj-icon');
  if (S.openProjects.has(projId)) {
    S.openProjects.delete(projId);
    sl.classList.remove('open');
    ph.classList.remove('open');
    if (iconEl) iconEl.textContent = '📁';
  } else {
    S.openProjects.add(projId);
    sl.classList.add('open');
    ph.classList.add('open');
    if (iconEl) iconEl.textContent = '📂';
    // Load sessions if not yet loaded
    if (!sl.dataset.loaded) {
      const sessions = await api(`/api/sessions?project=${encodeURIComponent(projId)}`);
      // Merge meta
      for (const s of sessions) {
        const key = `${projId}/${s.id}`;
        s.meta = (S.meta.sessions || {})[key] || s.meta || {};
      }
      sl.dataset.loaded = '1';
      sl.dataset.sessions = JSON.stringify(sessions);
    }
    renderSessionList(sl, projId, S.sidebarFilter.toLowerCase());
  }
  localStorage.setItem('openProjects', JSON.stringify([...S.openProjects]));
}

function renderSessionList(sl, projId, filter) {
  const sessions = JSON.parse(sl.dataset.sessions || '[]');
  sl.innerHTML = '';
  const filtered = filter ? sessions.filter(s => s.title.toLowerCase().includes(filter)) : sessions;
  for (const sess of filtered) {
    const meta = sess.meta || {};
    const item = el('div', 'sess-item' + (S.currentSession === sess.id ? ' active' : ''));
    item.dataset.sid = sess.id;
    const tags = meta.tags || [];
    const tagsHtml = tags.map(t => `<span class="tag-chip">${esc(t)}</span>`).join('');
    item.innerHTML = `
      <div class="sess-title">${meta.starred ? '⭐ ' : ''}${esc(sess.title)}</div>
      <div class="sess-meta">
        <span class="sess-date">${fmtDate(sess.timestamp)}</span>
        <span class="sess-count">${sess.message_count}件</span>
      </div>
      ${tagsHtml ? `<div class="sess-tags">${tagsHtml}</div>` : ''}
      ${meta.memo ? `<div style="font-size:11px;color:var(--text-muted);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">📝 ${esc(meta.memo)}</div>` : ''}
    `;
    item.addEventListener('click', () => loadSession(projId, sess.id));
    sl.appendChild(item);
  }
  if (!filtered.length) {
    sl.innerHTML = '<div style="padding:6px 14px;font-size:12px;color:var(--text-muted)">一致なし</div>';
  }
}

async function loadSession(projId, sessionId) {
  S.currentProject = projId;
  S.currentSession = sessionId;
  localStorage.setItem('lastSession', JSON.stringify({project: projId, session: sessionId}));

  // プロジェクトが閉じていたら開く
  if (!S.openProjects.has(projId)) {
    await toggleProject(projId);
  }

  // Update sidebar active state
  document.querySelectorAll('.sess-item').forEach(el => el.classList.remove('active'));
  const activeEl = document.querySelector(`.sess-item[data-sid="${sessionId}"]`);
  if (activeEl) activeEl.classList.add('active');

  // Load messages
  const msgs = await api(`/api/messages?project=${encodeURIComponent(projId)}&session=${encodeURIComponent(sessionId)}`);
  S.messages = msgs;

  // Find session title
  let title = sessionId;
  for (const proj of S.projects) {
    if (proj.id === projId) {
      const sl = document.getElementById('sl-' + projId);
      if (sl) {
        const sessions = JSON.parse(sl.dataset.sessions || '[]');
        const s = sessions.find(x => x.id === sessionId);
        if (s) title = s.title;
      }
    }
  }
  document.getElementById('session-title').textContent = title;

  // Update session star button
  const sessKey = `${projId}/${sessionId}`;
  const sessMeta = (S.meta.sessions || {})[sessKey] || {};
  document.getElementById('btn-session-star').textContent = sessMeta.starred ? '⭐' : '☆';

  renderMessages(msgs);
}

// ── Message rendering ──
function renderMessages(msgs) {
  const container = document.getElementById('chat-messages');
  container.innerHTML = '';
  if (!msgs.length) {
    container.innerHTML = '<div id="chat-empty"><div class="icon">🗒️</div><div>メッセージがありません</div></div>';
    return;
  }
  // If first non-plan message is from assistant, prior context was compacted
  const firstReal = msgs.find(m => !m.plan_content);
  if (firstReal && firstReal.role === 'assistant') {
    const notice = el('div', 'compaction-notice');
    notice.innerHTML = '<span>〔以前の会話は省略されています〕</span>';
    container.appendChild(notice);
  }
  for (const msg of msgs) {
    const row = renderMessage(msg);
    if (row) container.appendChild(row);
  }
  // 先頭から読めるようにトップへスクロール
  container.scrollTop = 0;
}

function renderMessage(msg) {
  // Plan-mode injection: display as collapsible plan document, not a chat bubble
  if (msg.plan_content) {
    const row = el('div', 'msg-row');
    row.dataset.uuid = msg.uuid;
    const ts = el('div', `msg-ts${S.showTs ? '' : ' hidden'}`);
    ts.textContent = fmtTime(msg.timestamp);
    const details = document.createElement('details');
    details.className = 'plan-block';
    details.innerHTML = `<summary>📋 実装計画 (クリックで展開)</summary>`;
    const body = el('div', 'plan-block-body');
    const bodyText = el('div', 'bubble-text');
    bodyText.innerHTML = renderMd(msg.plan_content);
    body.appendChild(bodyText);
    details.appendChild(body);
    row.appendChild(ts);
    row.appendChild(details);
    return row;
  }

  const row = el('div', `msg-row ${msg.role}`);
  row.dataset.uuid = msg.uuid;

  // Timestamp
  const ts = el('div', `msg-ts${S.showTs ? '' : ' hidden'}`);
  ts.textContent = fmtTime(msg.timestamp);

  // Bubble
  const bubble = el('div', 'bubble');

  // Main text
  if (msg.text) {
    const textEl = el('div', 'bubble-text');
    const collapseChars = S.cfg.collapse_chars ?? 600;
    const collapseLines = S.cfg.collapse_lines ?? 15;
    const previewChars  = S.cfg.preview_chars  ?? 300;
    const lineCount = (msg.text.match(/\n/g) || []).length;
    const shouldCollapse = msg.text.length > collapseChars || lineCount > collapseLines;
    if (shouldCollapse) {
      const preview = el('div', 'bubble-text');
      preview.innerHTML = renderMd(msg.text.slice(0, previewChars)) + '…';
      bubble.appendChild(preview);
      const details = document.createElement('details');
      details.className = 'msg-collapse';
      details.innerHTML = `<summary>▼ 続きを見る (${lineCount}行 / ${msg.text.length}文字)</summary>`;
      const full = el('div', 'bubble-text');
      full.innerHTML = renderMd(msg.text);
      details.appendChild(full);
      // 下部の「折りたたむ」ボタン
      const collapseBtn = el('div', 'collapse-bottom-btn');
      collapseBtn.textContent = '▲ 折りたたむ';
      collapseBtn.addEventListener('click', () => {
        details.open = false;
        bubble.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      });
      details.appendChild(collapseBtn);
      // 展開時はプレビューを隠す、閉じたら戻す
      details.addEventListener('toggle', () => {
        preview.style.display = details.open ? 'none' : '';
      });
      bubble.appendChild(details);
    } else {
      textEl.innerHTML = renderMd(msg.text);
      bubble.appendChild(textEl);
    }
  }

  // Thinking blocks
  if (S.cfg.show_thinking !== false) {
    for (const think of (msg.thinking || [])) {
      if (!think) continue;
      const d = document.createElement('details');
      d.className = 'thinking-block';
      d.innerHTML = `<summary class="thinking-summary">🤔 思考プロセス (${think.length}文字)</summary>`;
      const tc = el('div', 'thinking-content');
      tc.textContent = think;
      d.appendChild(tc);
      bubble.appendChild(d);
    }
  }

  // Tool chips
  if (S.cfg.show_tool_chips !== false && msg.tool_uses && msg.tool_uses.length) {
    const chips = el('div', 'tool-chips');
    for (const tu of msg.tool_uses) {
      const chip = el('div', 'tool-chip');
      chip.title = tu.description || tu.name;
      chip.innerHTML = `<span class="tool-icon">${toolIcon(tu.name)}</span>${esc(tu.description ? tu.description.slice(0,40) : tu.name)}`;
      chips.appendChild(chip);
    }
    bubble.appendChild(chips);
  }

  // Images
  if (msg.images && msg.images.length) {
    const imgRow = el('div', 'msg-images');
    for (const img of msg.images) {
      const im = document.createElement('img');
      im.src = `data:${img.media_type};base64,${img.data}`;
      im.alt = '画像';
      im.addEventListener('click', () => openLightbox(im.src));
      imgRow.appendChild(im);
    }
    bubble.appendChild(imgRow);
  }

  // バブルに表示する内容が何もなければ行ごとスキップ
  if (!bubble.hasChildNodes()) return null;

  // Toolbar (star / memo)
  const toolbar = el('div', 'msg-toolbar');
  const msgMeta = (S.meta.messages || {})[msg.uuid] || msg.meta || {};
  const starBtn = el('button', `tbtn${msgMeta.starred ? ' active' : ''}`);
  starBtn.textContent = msgMeta.starred ? '⭐' : '☆';
  starBtn.title = 'スター';
  starBtn.addEventListener('click', () => toggleMessageStar(msg.uuid, starBtn));
  const memoBtn = el('button', 'tbtn');
  memoBtn.textContent = '📝';
  memoBtn.title = 'メモ・タグ';
  memoBtn.addEventListener('click', () => openMemo('message', msg.uuid, msgMeta));
  toolbar.appendChild(starBtn);
  toolbar.appendChild(memoBtn);

  row.appendChild(ts);
  row.appendChild(bubble);
  row.appendChild(toolbar);
  return row;
}

function toolIcon(name) {
  const icons = { Read:'📖', Write:'💾', Edit:'✏️', Bash:'💻', Glob:'🗂️', Grep:'🔍',
    WebFetch:'🌐', WebSearch:'🌐', Agent:'🤖', TodoWrite:'📋', NotebookEdit:'📓',
    NotebookRead:'📓', TaskOutput:'📤' };
  return icons[name] || '🔧';
}

// ── Markdown renderer ──
function renderMd(text) {
  if (!text) return '';

  const saved = [];
  const save = html => { const i = saved.length; saved.push(html); return `\x00${i}\x00`; };
  const isSaved = s => /^\x00\d+\x00$/.test(s);

  // Normalize line endings (\r\n → \n)
  let s = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

  // ① テーブル・コードブロックを先に退避（内部の改行・HTMLを保護）
  const rawLines = s.split('\n');
  const out = [];
  let i = 0;
  while (i < rawLines.length) {
    // テーブル
    if (i + 1 < rawLines.length
        && /^\|.+\|/.test(rawLines[i])
        && /^\|[\s|:\-]+\|/.test(rawLines[i + 1])) {
      const tbl = [rawLines[i], rawLines[i + 1]]; i += 2;
      while (i < rawLines.length && /^\|.+\|/.test(rawLines[i])) tbl.push(rawLines[i++]);
      out.push(save(_renderTable(tbl)));
    } else {
      out.push(rawLines[i++]);
    }
  }
  s = out.join('\n');

  // ② コードブロックを退避（先にHTMLエスケープして \n を保護）
  s = s.replace(/```[\w]*\n?([\s\S]*?)```/g, (_, c) => save(
    `<pre><code>${c.trimEnd().replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}</code></pre>`
  ));

  // ③ 残りをHTMLエスケープ（プレースホルダの \x00 は影響を受けない）
  s = s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

  // ④ インライン要素
  s = s.replace(/`([^`\n]+)`/g, (_, c) => `<code>${c}</code>`);
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/__(.+?)__/g, '<strong>$1</strong>');
  s = s.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');

  // ⑤ 行単位でブロック要素を処理（見出し・リスト・段落を正しく分離）
  const parts = [];
  let paraLines = [];
  let listItems = [];
  let listOrdered = false;

  const flushPara = () => {
    const t = paraLines.join('<br>').trim();
    if (t) parts.push(`<p>${t}</p>`);
    paraLines = [];
  };
  const flushList = () => {
    if (!listItems.length) return;
    const tag = listOrdered ? 'ol' : 'ul';
    parts.push(`<${tag}>${listItems.join('')}</${tag}>`);
    listItems = [];
  };

  for (const line of s.split('\n')) {
    const t = line.trim();
    const h3 = t.match(/^### (.+)/), h2 = !h3 && t.match(/^## (.+)/), h1 = !h2 && !h3 && t.match(/^# (.+)/);
    const ul = t.match(/^[\*\-] (.+)/);
    const ol = t.match(/^\d+\. (.+)/);

    if (h3 || h2 || h1) {
      flushList(); flushPara();
      parts.push(h3 ? `<h3>${h3[1]}</h3>` : h2 ? `<h2>${h2[1]}</h2>` : `<h1>${h1[1]}</h1>`);
    } else if (isSaved(t)) {
      flushList(); flushPara();
      parts.push(t);
    } else if (ul) {
      flushPara();
      if (listOrdered) flushList();
      listOrdered = false;
      listItems.push(`<li>${ul[1]}</li>`);
    } else if (ol) {
      flushPara();
      if (!listOrdered) flushList();
      listOrdered = true;
      listItems.push(`<li>${ol[1]}</li>`);
    } else if (!t) {
      flushList(); flushPara();
    } else {
      flushList();
      paraLines.push(t);
    }
  }
  flushList();
  flushPara();

  // ⑥ プレースホルダ復元
  return parts.join('').replace(/\x00(\d+)\x00/g, (_, i) => saved[+i]);
}

function _renderTable(lines) {
  const parseRow = l => l.replace(/^\||\|$/g,'').split('|').map(c => c.trim());
  const header = parseRow(lines[0]);
  const sep    = parseRow(lines[1]);
  if (!sep.every(c => /^:?-+:?$/.test(c))) {
    // セパレータ行が不正なら plain text で返す
    return lines.map(l => l.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')).join('<br>');
  }
  const aligns = sep.map(c =>
    (c.startsWith(':') && c.endsWith(':')) ? 'center' :
    c.endsWith(':') ? 'right' : 'left');
  // セル内テキストをエスケープ＋インラインマークアップだけ処理
  const ec = c => c
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g,'<em>$1</em>')
    .replace(/`([^`]+)`/g,'<code>$1</code>');
  let h = '<div class="md-table-wrap"><table class="md-table"><thead><tr>';
  header.forEach((c,i) => h += `<th style="text-align:${aligns[i]||'left'}">${ec(c)}</th>`);
  h += '</tr></thead><tbody>';
  lines.slice(2).forEach(l => {
    const cells = parseRow(l);
    if (!cells.length) return;
    h += '<tr>';
    header.forEach((_,i) => h += `<td style="text-align:${aligns[i]||'left'}">${ec(cells[i]||'')}</td>`);
    h += '</tr>';
  });
  return h + '</tbody></table></div>';
}

// ── Star / Memo ──
async function toggleMessageStar(uuid, btn) {
  const existing = (S.meta.messages || {})[uuid] || {};
  const meta = {
    ...existing,
    starred: !existing.starred,
    project_id: existing.project_id || S.currentProject,
    session_id: existing.session_id || S.currentSession,
  };
  await post('/api/meta/message', { uuid, meta });
  S.meta.messages = S.meta.messages || {};
  S.meta.messages[uuid] = meta;
  btn.textContent = meta.starred ? '⭐' : '☆';
  btn.classList.toggle('active', !!meta.starred);
}

function openMemo(type, key, currentMeta) {
  S.memoTarget = { type, key, currentMeta };
  document.getElementById('memo-textarea').value = currentMeta.memo || '';
  document.getElementById('tag-input').value = (currentMeta.tags || []).join(', ');
  document.getElementById('memo-modal').classList.add('open');
}

async function saveMemo() {
  const { type, key } = S.memoTarget;
  const memo = document.getElementById('memo-textarea').value.trim();
  const tagsRaw = document.getElementById('tag-input').value;
  const tags = tagsRaw.split(',').map(t => t.trim()).filter(Boolean);
  const existingMeta = type === 'session'
    ? (S.meta.sessions || {})[key] || {}
    : (S.meta.messages || {})[key] || {};
  const newMeta = { ...existingMeta, memo, tags };

  if (type === 'session') {
    const [projId, sessId] = key.split('/', 2);
    // If key is already "projId/sessId" format:
    await post('/api/meta/session', { project_id: projId, session_id: sessId, meta: newMeta });
    S.meta.sessions = S.meta.sessions || {};
    S.meta.sessions[key] = newMeta;
    // Re-render session list
    refreshSessionMeta(key, newMeta);
  } else {
    const existingMsg = (S.meta.messages || {})[key] || {};
    const msgMeta = {
      ...newMeta,
      project_id: existingMsg.project_id || S.currentProject,
      session_id: existingMsg.session_id || S.currentSession,
    };
    await post('/api/meta/message', { uuid: key, meta: msgMeta });
    S.meta.messages = S.meta.messages || {};
    S.meta.messages[key] = msgMeta;
  }
  document.getElementById('memo-modal').classList.remove('open');
}

function refreshSessionMeta(key, newMeta) {
  const [projId, sessId] = key.split('/', 2);
  const sl = document.getElementById('sl-' + projId);
  if (!sl) return;
  const sessions = JSON.parse(sl.dataset.sessions || '[]');
  for (const s of sessions) {
    if (s.id === sessId) { s.meta = newMeta; break; }
  }
  sl.dataset.sessions = JSON.stringify(sessions);
  renderSessionList(sl, projId, S.sidebarFilter.toLowerCase());
}

// Session star
document.getElementById('btn-session-star').addEventListener('click', async () => {
  if (!S.currentSession) return;
  const key = `${S.currentProject}/${S.currentSession}`;
  const existing = (S.meta.sessions || {})[key] || {};
  const newMeta = { ...existing, starred: !existing.starred };
  await post('/api/meta/session', { project_id: S.currentProject, session_id: S.currentSession, meta: newMeta });
  S.meta.sessions = S.meta.sessions || {};
  S.meta.sessions[key] = newMeta;
  document.getElementById('btn-session-star').textContent = newMeta.starred ? '⭐' : '☆';
  refreshSessionMeta(key, newMeta);
});

document.getElementById('btn-session-memo').addEventListener('click', () => {
  if (!S.currentSession) return;
  const key = `${S.currentProject}/${S.currentSession}`;
  const existing = (S.meta.sessions || {})[key] || {};
  openMemo('session', key, existing);
});
document.getElementById('btn-export').addEventListener('click', exportHTML);

// ── Search ──
function populateSearchScope() {
  const sel = document.getElementById('search-scope');
  for (const proj of S.projects) {
    const opt = document.createElement('option');
    opt.value = proj.id;
    opt.textContent = shortPath(proj.cwd);
    sel.appendChild(opt);
  }
}

let searchTimer = null;
document.getElementById('search-input').addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(runSearch, 300);
});
document.getElementById('search-type').addEventListener('change', runSearch);
document.getElementById('search-scope').addEventListener('change', runSearch);

async function runSearch() {
  const q = document.getElementById('search-input').value.trim();
  const type = document.getElementById('search-type').value;
  const scope = document.getElementById('search-scope').value;
  const resultsEl = document.getElementById('search-results');
  if (!q) { resultsEl.innerHTML = '<div class="sr-empty">キーワードを入力して検索</div>'; return; }
  resultsEl.innerHTML = '<div class="sr-empty">検索中…</div>';
  const url = `/api/search?q=${encodeURIComponent(q)}&type=${type}${scope ? '&project=' + encodeURIComponent(scope) : ''}`;
  const results = await api(url);
  if (!results.length) {
    resultsEl.innerHTML = '<div class="sr-empty">一致するメッセージが見つかりませんでした</div>';
    return;
  }
  resultsEl.innerHTML = '';
  for (const r of results) {
    const item = el('div', 'sr-item');
    item.innerHTML = `
      <div class="sr-session">📁 ${esc(r.session_title || r.session_id)}</div>
      <div class="sr-snippet">${esc(r.snippet)}</div>
      <div class="sr-role">${r.role === 'user' ? '👤 あなた' : '🤖 Claude'} · ${fmtTime(r.timestamp)}</div>
    `;
    item.addEventListener('click', async () => {
      document.getElementById('search-panel').classList.remove('open');
      await loadSession(r.project_id, r.session_id);
      // Scroll to message
      setTimeout(() => {
        const msgEl = document.querySelector(`.msg-row[data-uuid="${r.uuid}"]`);
        if (msgEl) { msgEl.scrollIntoView({ behavior: 'smooth', block: 'center' }); msgEl.style.outline = '2px solid var(--accent)'; setTimeout(() => msgEl.style.outline = '', 2000); }
      }, 300);
    });
    resultsEl.appendChild(item);
  }
}

// ── Starred panel ──
async function openStarredPanel() {
  const starred = await api('/api/starred');
  const body = document.getElementById('starred-body');
  body.innerHTML = '';

  if (starred.sessions.length) {
    const h = el('div', 'starred-section-title'); h.textContent = 'スター付きセッション';
    body.appendChild(h);
    for (const s of starred.sessions) {
      const item = el('div', 'starred-item');
      const sessTitle = s.session_id; // Best we can do without loading
      const tags = (s.tags || []).map(t => `<span class="tag-chip">${esc(t)}</span>`).join('');
      item.innerHTML = `
        <div class="starred-item-title">⭐ ${esc(s.session_id)}</div>
        <div class="starred-item-meta">📁 ${esc(s.project_id)}</div>
        ${s.memo ? `<div class="starred-item-meta">📝 ${esc(s.memo)}</div>` : ''}
        ${tags ? `<div class="starred-tags">${tags}</div>` : ''}
      `;
      item.addEventListener('click', async () => {
        document.getElementById('starred-panel').classList.remove('open');
        await loadSession(s.project_id, s.session_id);
      });
      body.appendChild(item);
    }
  }
  if (starred.messages.length) {
    const h = el('div', 'starred-section-title'); h.textContent = 'スター付きメッセージ';
    body.appendChild(h);
    for (const m of starred.messages) {
      const item = el('div', 'starred-item');
      const canNav = m.project_id && m.session_id;
      item.innerHTML = `
        <div class="starred-item-title">⭐ ${esc(m.memo || m.uuid.slice(0,8) + '…')}</div>
        ${m.session_id ? `<div class="starred-item-meta">📁 ${esc(m.session_id.slice(0,8))}…</div>` : ''}
        ${!canNav ? '<div class="starred-item-meta" style="opacity:.6">※ 再スターで位置を記録できます</div>' : ''}
      `;
      if (canNav) {
        item.addEventListener('click', async () => {
          document.getElementById('starred-panel').classList.remove('open');
          await loadSession(m.project_id, m.session_id);
          setTimeout(() => {
            const target = document.querySelector(`[data-uuid="${m.uuid}"]`);
            if (target) target.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }, 100);
        });
      }
      body.appendChild(item);
    }
  }
  if (!starred.sessions.length && !starred.messages.length) {
    body.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted);font-size:13px">スター付きアイテムがありません</div>';
  }
  document.getElementById('starred-panel').classList.add('open');
}

// ── Sidebar filter ──
document.getElementById('sidebar-search').addEventListener('input', e => {
  S.sidebarFilter = e.target.value;
  document.querySelectorAll('.session-list.open').forEach(sl => {
    const projId = sl.id.replace('sl-', '');
    renderSessionList(sl, projId, S.sidebarFilter.toLowerCase());
  });
});

// ── Event listeners ──
document.getElementById('btn-theme').addEventListener('click', () => {
  S.theme = S.theme === 'dark' ? 'light' : 'dark';
  localStorage.setItem('theme', S.theme);
  applyTheme();
});
document.getElementById('btn-ts').addEventListener('click', () => {
  S.showTs = !S.showTs;
  localStorage.setItem('showTs', S.showTs);
  applyTsBtn();
});
document.getElementById('btn-font-up').addEventListener('click', () => {
  S.fontSize = Math.min(22, S.fontSize + 1);
  localStorage.setItem('fontSize', S.fontSize);
  applyFontSize();
});
document.getElementById('btn-font-down').addEventListener('click', () => {
  S.fontSize = Math.max(10, S.fontSize - 1);
  localStorage.setItem('fontSize', S.fontSize);
  applyFontSize();
});
document.getElementById('font-select').addEventListener('change', e => {
  S.fontKey = e.target.value;
  localStorage.setItem('fontKey', S.fontKey);
  applyFont();
});
document.getElementById('btn-search').addEventListener('click', () => {
  document.getElementById('search-panel').classList.add('open');
  setTimeout(() => document.getElementById('search-input').focus(), 50);
});
document.getElementById('btn-search-close').addEventListener('click', () => {
  document.getElementById('search-panel').classList.remove('open');
});
document.getElementById('search-panel').addEventListener('click', e => {
  if (e.target === document.getElementById('search-panel')) document.getElementById('search-panel').classList.remove('open');
});
document.getElementById('btn-starred').addEventListener('click', openStarredPanel);
document.getElementById('btn-starred-close').addEventListener('click', () => {
  document.getElementById('starred-panel').classList.remove('open');
});
document.getElementById('starred-panel').addEventListener('click', e => {
  if (e.target === document.getElementById('starred-panel')) document.getElementById('starred-panel').classList.remove('open');
});
document.getElementById('btn-memo-cancel').addEventListener('click', () => {
  document.getElementById('memo-modal').classList.remove('open');
});
document.getElementById('btn-memo-save').addEventListener('click', saveMemo);
document.getElementById('lightbox').addEventListener('click', () => {
  document.getElementById('lightbox').classList.remove('open');
});

// Keyboard shortcuts
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    document.getElementById('search-panel').classList.add('open');
    setTimeout(() => document.getElementById('search-input').focus(), 50);
  }
  if (e.key === 'Escape') {
    document.getElementById('search-panel').classList.remove('open');
    document.getElementById('starred-panel').classList.remove('open');
    document.getElementById('memo-modal').classList.remove('open');
    document.getElementById('lightbox').classList.remove('open');
  }
});

// ── Resize handle ──
(function() {
  const handle = document.getElementById('resize-handle');
  const sidebar = document.getElementById('sidebar');
  let dragging = false, startX, startW;
  handle.addEventListener('mousedown', e => {
    dragging = true; startX = e.clientX; startW = sidebar.offsetWidth;
    handle.classList.add('dragging');
    document.body.style.userSelect = 'none';
  });
  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const w = Math.max(160, Math.min(500, startW + e.clientX - startX));
    sidebar.style.width = w + 'px';
  });
  document.addEventListener('mouseup', () => {
    if (dragging) { dragging = false; handle.classList.remove('dragging'); document.body.style.userSelect = ''; }
  });
})();

// ── Lightbox ──
function openLightbox(src) {
  document.getElementById('lightbox-img').src = src;
  document.getElementById('lightbox').classList.add('open');
}

// ── Helpers ──
function el(tag, cls) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  return e;
}
function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function fmtDate(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    return d.toLocaleDateString('ja-JP', { month:'2-digit', day:'2-digit' });
  } catch { return ''; }
}
function fmtTime(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    return d.toLocaleString('ja-JP', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' });
  } catch { return ''; }
}
// ── Export ──
function exportHTML() {
  if (!S.currentSession) return;

  const title = document.getElementById('session-title').textContent;
  const dateStr = new Date().toLocaleString('ja-JP');

  // クローンして操作UIを除去
  const clone = document.getElementById('chat-messages').cloneNode(true);
  clone.querySelectorAll('.msg-toolbar').forEach(el => el.remove());

  // 折りたたみを全展開し、プレビュー重複を解消
  clone.querySelectorAll('details.msg-collapse').forEach(details => {
    details.open = true;
    // プレビュー div（直前の兄弟）を削除
    const prev = details.previousElementSibling;
    if (prev && prev.classList.contains('bubble-text')) prev.remove();
    // 下部の折りたたむボタンを削除（JS不要のため）
    details.querySelectorAll('.collapse-bottom-btn').forEach(b => b.remove());
  });

  // 現在のテーマのCSS変数を取得
  const cs = getComputedStyle(document.documentElement);
  const vars = ['--bg','--sidebar-bg','--bubble-user','--bubble-user-text',
    '--bubble-ai','--bubble-ai-text','--thinking-bg','--thinking-text',
    '--border','--text','--text-muted','--accent','--chip-bg','--chip-text',
    '--font-family','--font-size','--radius','--shadow'];
  const varBlock = vars.map(v => `  ${v}:${cs.getPropertyValue(v)};`).join('\n');

  const html = `<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title>
<style>
:root {
${varBlock}
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font-family);font-size:var(--font-size);background:var(--bg);color:var(--text);padding:16px}
.export-header{max-width:860px;margin:0 auto 20px;padding-bottom:12px;border-bottom:1px solid var(--border)}
.export-header h1{font-size:17px;font-weight:700;margin-bottom:4px}
.export-meta{font-size:12px;color:var(--text-muted)}
#chat-messages{max-width:860px;margin:0 auto;display:flex;flex-direction:column;gap:12px}
.msg-row{display:flex;flex-direction:column;gap:4px}
.msg-row.user{align-items:flex-end}
.msg-row.assistant{align-items:flex-start}
.msg-ts{font-size:11px;color:var(--text-muted);padding:0 4px}
.msg-ts.hidden{display:none}
.bubble{max-width:72%;padding:10px 14px;border-radius:var(--radius);word-break:break-word}
.msg-row.user .bubble{background:var(--bubble-user);color:var(--bubble-user-text);border-bottom-right-radius:4px}
.msg-row.assistant .bubble{background:var(--bubble-ai);color:var(--bubble-ai-text);border-bottom-left-radius:4px;box-shadow:var(--shadow)}
.bubble-text{line-height:1.6;white-space:normal}
.bubble-text p{margin:0 0 .6em}.bubble-text p:last-child{margin-bottom:0}
.bubble-text code{background:rgba(0,0,0,.1);padding:1px 4px;border-radius:4px;font-size:.9em;font-family:monospace}
.msg-row.user .bubble-text code{background:rgba(255,255,255,.2)}
.bubble-text pre{background:rgba(0,0,0,.12);padding:8px 10px;border-radius:8px;overflow-x:auto;margin:.4em 0}
.msg-row.user .bubble-text pre{background:rgba(255,255,255,.15)}
.bubble-text pre code{background:none;padding:0}
.bubble-text h1{font-size:1.1em;font-weight:700;margin:.5em 0 .15em}.bubble-text h2{font-size:1.05em;font-weight:700;margin:.4em 0 .15em}.bubble-text h3{font-size:1em;font-weight:700;margin:.35em 0 .1em}.bubble-text h1:first-child,.bubble-text h2:first-child,.bubble-text h3:first-child{margin-top:.1em}
.bubble-text ul,.bubble-text ol{padding-left:1.4em;margin:.3em 0}
.bubble-text strong{font-weight:700}
.bubble-text em{font-style:italic}
.msg-collapse>summary{font-size:12px;color:var(--accent);cursor:pointer;list-style:none;padding:4px 0}
.msg-collapse>summary::marker{display:none}
.msg-collapse[open]>summary{display:none}
.thinking-block{margin-top:6px;background:var(--thinking-bg);border-radius:10px;overflow:hidden}
.thinking-summary{padding:6px 10px;font-size:12px;color:var(--thinking-text);cursor:pointer;display:flex;align-items:center;gap:6px}
.thinking-summary::marker{display:none}
.thinking-content{padding:8px 10px;font-size:12px;color:var(--thinking-text);white-space:pre-wrap;max-height:300px;overflow-y:auto;border-top:1px solid rgba(0,0,0,.08)}
.tool-chips{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
.tool-chip{display:inline-flex;align-items:center;gap:4px;font-size:11px;padding:3px 8px;border-radius:10px;background:var(--chip-bg);color:var(--chip-text);max-width:220px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.msg-images{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.msg-images img{max-width:200px;max-height:150px;border-radius:8px;border:1px solid var(--border)}
.md-table-wrap{overflow-x:auto;margin:.5em 0;border-radius:6px}
.md-table{border-collapse:collapse;width:100%;font-size:.93em}
.md-table th,.md-table td{border:1px solid rgba(0,0,0,.15);padding:5px 10px;white-space:nowrap;line-height:1.4}
.md-table th{background:rgba(0,0,0,.06);font-weight:600}
.md-table tr:nth-child(even) td{background:rgba(0,0,0,.025)}
.msg-row.user .md-table th,.msg-row.user .md-table td{border-color:rgba(255,255,255,.3)}
.msg-row.user .md-table th{background:rgba(255,255,255,.18)}
</style>
</head>
<body>
<div class="export-header">
  <h1>${esc(title)}</h1>
  <div class="export-meta">保存日時: ${dateStr}</div>
</div>
${clone.outerHTML}
</body>
</html>`;

  const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = title.replace(/[\\/:*?"<>|]/g, '_').slice(0, 80) + '.html';
  a.click();
  URL.revokeObjectURL(url);
}

function shortPath(p) {
  if (!p) return '';
  const parts = p.replace(/\\/g,'/').split('/');
  return parts.slice(-2).join('/') || p;
}

// Start
init();
</script>
</body>
</html>
"""


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    cfg = load_settings()

    parser = argparse.ArgumentParser(description="Claude History Viewer")
    parser.add_argument("--port",       type=int,  default=cfg["port"])
    parser.add_argument("--claude-dir", type=Path, default=DEFAULT_CLAUDE_DIR)
    parser.add_argument("--no-browser", action="store_true",
                        default=not cfg["auto_open_browser"])
    args = parser.parse_args()

    claude_dir = args.claude_dir.expanduser()
    if not claude_dir.exists():
        print(f"Error: Claude directory not found: {claude_dir}", file=sys.stderr)
        sys.exit(1)

    # コマンドライン引数で settings.json の値を上書き
    cfg["port"] = args.port

    reader = ClaudeDataReader(claude_dir)
    meta = MetaStore(claude_dir / META_FILENAME)
    handler = make_handler(reader, meta, cfg)

    server = HTTPServer(("127.0.0.1", args.port), handler)
    url = f"http://localhost:{args.port}"
    print(f"Claude History Viewer: {url}")
    print(f"設定ファイル: {SETTINGS_FILE}")
    print("停止: Ctrl+C")

    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました。")


if __name__ == "__main__":
    main()
