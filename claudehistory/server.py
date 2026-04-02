import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .template import HTML_TEMPLATE


def make_handler(reader, meta, cfg):
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
            elif path == "/api/open-folder":
                folder = qs.get("path", [""])[0]
                if folder and Path(folder).is_dir():
                    if sys.platform == "win32":
                        def _open_win(f):
                            import ctypes, time
                            subprocess.Popen(["explorer", f])
                            time.sleep(0.7)
                            u = ctypes.windll.user32
                            hwnd = u.FindWindowW("CabinetWClass", None)
                            if hwnd:
                                # Alt キーイベントで Windows のフォーカス制限を回避
                                u.keybd_event(0x12, 0, 0, 0)
                                u.ShowWindow(hwnd, 9)  # SW_RESTORE
                                u.SetForegroundWindow(hwnd)
                                u.keybd_event(0x12, 0, 2, 0)
                        threading.Thread(target=_open_win, args=(folder,), daemon=True).start()
                    elif sys.platform == "darwin":
                        subprocess.Popen(["open", folder])
                    else:
                        subprocess.Popen(["xdg-open", folder])
                    self._json({"ok": True})
                else:
                    self._json({"ok": False})
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
            elif path == "/api/meta/project":
                meta.set_project(data["project_id"], data["meta"])
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
