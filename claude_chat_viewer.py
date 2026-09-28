#!/usr/bin/env python3
"""
Claude History Viewer - LINEライクな Claude Code セッションビューア
Usage: python claude_chat_viewer.py [--port 57080] [--claude-dir ~/.claude]
"""

import argparse
import sys
import threading
import webbrowser
from http.server import HTTPServer
from pathlib import Path

from claudehistory.archive import start_archive_thread
from claudehistory.claude_settings import ClaudeSettings
from claudehistory.config import (
    ARCHIVE_DIRNAME, DEFAULT_CLAUDE_DIR, META_FILENAME, SETTINGS_FILE, load_settings,
)
from claudehistory.reader import ClaudeDataReader
from claudehistory.meta import MetaStore
from claudehistory.server import make_handler


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

    archive_dir = None
    if cfg["archive_enabled"]:
        archive_dir = (Path(cfg["archive_dir"]).expanduser() if cfg["archive_dir"]
                       else claude_dir / ARCHIVE_DIRNAME)
        start_archive_thread(claude_dir / "projects", archive_dir / "projects",
                             max(1, cfg["archive_interval_min"]) * 60)

    reader = ClaudeDataReader(claude_dir, archive_dir)
    meta = MetaStore(claude_dir / META_FILENAME)
    handler = make_handler(reader, meta, cfg, ClaudeSettings(claude_dir))

    server = HTTPServer(("127.0.0.1", args.port), handler)
    url = f"http://localhost:{args.port}"
    print(f"Claude History Viewer: {url}")
    print(f"設定ファイル: {SETTINGS_FILE}")
    if archive_dir:
        print(f"バックアップ先: {archive_dir}")
    print("停止: Ctrl+C")

    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました。")


if __name__ == "__main__":
    main()
