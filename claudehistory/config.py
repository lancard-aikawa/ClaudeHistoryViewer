import json
import sys
from pathlib import Path

DEFAULT_PORT = 57080
DEFAULT_CLAUDE_DIR = Path.home() / ".claude"
META_FILENAME = "chat-viewer-meta.json"
SETTINGS_FILE = Path(__file__).parent.parent / "settings.json"

SETTINGS_DEFAULTS: dict = {
    # ── 起動設定（再起動後に反映） ──────────────────
    "port": 57080,                # ポート番号
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
