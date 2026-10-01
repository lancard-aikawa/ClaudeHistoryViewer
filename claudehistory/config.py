import json
import os
import sys
from pathlib import Path

DEFAULT_PORT = 57080
DEFAULT_CLAUDE_DIR = Path.home() / ".claude"
META_FILENAME = "chat-viewer-meta.json"
ARCHIVE_DIRNAME = "chat-viewer-archive"
SETTINGS_FILE = Path(__file__).parent.parent / "settings.json"

SETTINGS_DEFAULTS: dict = {
    # ── 起動設定（再起動後に反映） ──────────────────
    "port": 57080,                # ポート番号
    "auto_open_browser": True,    # 起動時にブラウザを自動で開く

    # ── 表示設定（設定画面から変えるとすぐ反映） ────
    "collapse_lines": 15,         # これ以上の行数で折りたたむ
    "collapse_chars": 600,        # これ以上の文字数で折りたたむ（行数より先に達した場合も折りたたむ）
    "preview_chars":  300,        # 折りたたみ時に表示するプレビュー文字数
    "show_thinking":   True,      # 思考プロセスブロックを表示する
    "show_tool_chips": True,      # ツール呼び出しチップを表示する
    "max_search_results": 300,    # 検索結果の最大件数

    # ── バックアップ（再起動後に反映） ──────────────
    # Claude Code は古いセッションを削除するため、消える前に別フォルダへコピーしておく
    "archive_enabled": True,      # セッションのバックアップを取る
    "archive_dir": "",            # 保存先（空なら ~/.claude/chat-viewer-archive）
    "archive_interval_min": 10,   # バックアップを取り直す間隔（分）
    # SessionVault の src フォルダ（例: C:/Repos/mywork/SessionVault/src）。空なら同梱のサブモジュール
    # （vendor/SessionVault/src）を使う。読み込めればバックアップをそちらに任せ、保存先は SessionVault の設定に従う
    # （archive_dir は使わない）。読み込めなければビューア内蔵のバックアップ
    "sessionvault_src": "",
    # SessionVault の設定ファイル（sessionvault.json）。空なら読み込んだ SessionVault のリポジトリ直下。
    # 単体で動かしている SessionVault（タスクスケジューラ）と同じ保管庫を使うときは、その sessionvault.json を書く。
    # 設定に vault が無ければ、この設定ファイルの隣の vault/ を使う
    "sessionvault_config": "",
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

# 整数設定の下限・上限（無いものは 1 以上）
_INT_RANGES = {"port": (1024, 65535)}

def validate_settings(changes: dict) -> dict:
    """設定画面からの変更を検証する。不正な値は ValueError"""
    out = {}
    for k, v in changes.items():
        if k not in SETTINGS_DEFAULTS:
            raise ValueError(f"不明な設定です: {k}")
        default = SETTINGS_DEFAULTS[k]
        if type(v) is not type(default):
            raise ValueError(f"{k} の型が違います")
        if isinstance(v, int) and not isinstance(v, bool):
            lo, hi = _INT_RANGES.get(k, (1, None))
            if v < lo or (hi is not None and v > hi):
                raise ValueError(f"{k} は {lo} 以上{f'、{hi} 以下' if hi else ''}にしてください")
        out[k] = v
    return out

def save_settings(changes: dict) -> None:
    """settings.json に変更を書き込む。ファイルにある他のキーはそのまま残す"""
    data = {}
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    data.update(changes)
    write_json_atomic(SETTINGS_FILE, data)

def write_json_atomic(path: Path, data: dict) -> None:
    """書きかけのファイルを残さないよう一時ファイル経由で置き換える"""
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
