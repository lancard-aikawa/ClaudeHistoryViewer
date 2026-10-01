#!/usr/bin/env python3
"""
Claude History Viewer - LINEライクな Claude Code セッションビューア
Usage: python claude_chat_viewer.py [--port 57080] [--claude-dir ~/.claude]
"""

import argparse
import socket
import sys
import threading
import webbrowser
from http.server import HTTPServer
from pathlib import Path

from claudehistory.archive import load_sessionvault, sessionvault_settings, start_archive_thread
from claudehistory.claude_settings import ClaudeSettings
from claudehistory.config import (
    ARCHIVE_DIRNAME, DEFAULT_CLAUDE_DIR, META_FILENAME, SETTINGS_FILE, load_settings,
)
from claudehistory.reader import ClaudeDataReader
from claudehistory.memory import MemoryIndex
from claudehistory.meta import MetaStore
from claudehistory.server import make_handler


class ViewerServer(HTTPServer):
    """二重に起動できない HTTPServer。
    Windows の SO_REUSEADDR（HTTPServer の既定）は使用中のポートにも bind できてしまい、
    再起動で古いプロセスが残ると、古い方が応答し続けて直したコードが効いていないように見えた（2026-10-01）"""
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self):
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


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

    # バックアップの読み込み元。元のファイルが消えてもここから読む（先に書いた方が優先）
    backup_roots = []
    archive_dir = (Path(cfg["archive_dir"]).expanduser() if cfg["archive_dir"]
                   else claude_dir / ARCHIVE_DIRNAME)
    vault = None
    if cfg["archive_enabled"]:
        sv = load_sessionvault(cfg["sessionvault_src"])
        if sv:
            try:
                _, vault = sessionvault_settings(sv, cfg["sessionvault_config"])
                backup_roots.append(vault / "mirror")
            except (OSError, ValueError) as e:
                print(f"Warning: SessionVault の設定を読めないので内蔵のバックアップを使います: {e}", file=sys.stderr)
                sv = None
        start_archive_thread(claude_dir / "projects", archive_dir / "projects",
                             max(1, cfg["archive_interval_min"]) * 60, sv, vault, cfg["sessionvault_config"])
    # 内蔵のバックアップが前に写したものも、SessionVault に移ったあと読めるよう残す
    backup_roots.append(archive_dir / "projects")

    reader = ClaudeDataReader(claude_dir, backup_roots)
    meta = MetaStore(claude_dir / META_FILENAME)
    handler = make_handler(reader, meta, cfg, ClaudeSettings(claude_dir),
                           MemoryIndex(claude_dir / "projects", vault))

    try:
        server = ViewerServer(("127.0.0.1", args.port), handler)
    except OSError as e:
        print(f"Error: ポート {args.port} を使えません（ビューアがもう動いていませんか）: {e}", file=sys.stderr)
        sys.exit(1)
    url = f"http://localhost:{args.port}"
    print(f"Claude History Viewer: {url}")
    print(f"設定ファイル: {SETTINGS_FILE}")
    if vault:
        print(f"バックアップ先: {vault}（SessionVault）")
    elif cfg["archive_enabled"]:
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
