"""Claude Code の設定（~/.claude/settings.json）の読み書き

設定画面から書き換えられるのは EDITABLE に挙げた項目だけ。
permissions / hooks / env などはコマンド実行や権限に関わるため、画面からは編集させない
（ビューアは認証のないローカル HTTP サーバなので、書ける範囲を広げると悪用の入口になる）。
"""
import json
import re
from pathlib import Path

from .config import write_json_atomic

# 値の種類と既定値は https://json.schemastore.org/claude-code-settings.json に合わせる
EDITABLE: dict = {
    "cleanupPeriodDays": {
        "group": "保存", "label": "セッションの保存期間（日）", "type": "int", "min": 1, "default": 30,
        "help": "これより古いセッションは Claude Code の起動時に削除されます。0 は指定できません",
    },
    "theme": {
        "group": "表示", "label": "テーマ", "type": "enum", "default": "dark",
        "values": ["auto", "dark", "light", "dark-daltonized", "light-daltonized", "dark-ansi", "light-ansi"],
    },
    "tui": {
        "group": "表示", "label": "画面の描画方式", "type": "enum", "default": "default",
        "values": ["fullscreen", "default"],
        "help": "fullscreen はちらつきの少ない全画面表示（/tui と同じ）",
    },
    "verbose": {
        "group": "表示", "label": "ツールの出力を省略せず表示", "type": "bool", "default": False,
    },
    "spinnerTipsEnabled": {
        "group": "表示", "label": "作業中にヒントを表示", "type": "bool", "default": True,
    },
    "terminalProgressBarEnabled": {
        "group": "表示", "label": "ターミナルの進捗バー", "type": "bool", "default": True,
        "help": "Windows Terminal などのタブに進捗を表示します",
    },
    "prefersReducedMotion": {
        "group": "表示", "label": "アニメーションを減らす", "type": "bool", "default": False,
    },
    "preferredNotifChannel": {
        "group": "通知", "label": "通知の方法", "type": "enum", "default": "auto",
        "values": ["auto", "terminal_bell", "iterm2", "iterm2_with_bell", "kitty", "ghostty",
                   "notifications_disabled"],
        "help": "作業完了や許可待ちの通知。auto は iTerm2 / Ghostty / Kitty 以外では何もしません",
    },
    "agentPushNotifEnabled": {
        "group": "通知", "label": "スマホへのプッシュ通知（作業完了など）", "type": "bool", "default": False,
        "help": "Remote Control 接続中のみ",
    },
    "inputNeededNotifEnabled": {
        "group": "通知", "label": "スマホへのプッシュ通知（入力待ち）", "type": "bool", "default": False,
        "help": "Remote Control 接続中のみ",
    },
}

# 閲覧用の表示で値を伏せるキー
_SECRET_KEY = re.compile(r"token|secret|password|passwd|api[_-]?key|credential|auth", re.I)


def _mask(obj, parent_key: str = ""):
    if isinstance(obj, dict):
        return {k: _mask(v, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_mask(v, parent_key) for v in obj]
    # 秘密情報らしい名前のキーの値は伏せる
    if isinstance(obj, str) and _SECRET_KEY.search(parent_key):
        return "***"
    return obj


class ClaudeSettings:
    def __init__(self, claude_dir: Path):
        self.path = claude_dir / "settings.json"

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def get(self) -> dict:
        try:
            data = self._load()
            error = None
        except (OSError, json.JSONDecodeError) as e:
            data, error = {}, f"{self.path} を読めません: {e}"
        masked = {k: _mask(v, k) for k, v in data.items()}
        # env は値がすべて秘密情報になりうるので、名前だけ見せる
        if isinstance(data.get("env"), dict):
            masked["env"] = {k: "***" for k in data["env"]}
        return {
            "path": str(self.path),
            "error": error,
            "fields": EDITABLE,
            "values": {k: data[k] for k in EDITABLE if k in data},
            "raw": json.dumps(masked, ensure_ascii=False, indent=2),
        }

    def update(self, changes: dict) -> None:
        """changes の値で上書きする。None は項目を消して既定値に戻す"""
        for k, v in changes.items():
            spec = EDITABLE.get(k)
            if spec is None:
                raise ValueError(f"この項目は設定画面からは変更できません: {k}")
            if v is None:
                continue
            t = spec["type"]
            if t == "bool" and not isinstance(v, bool):
                raise ValueError(f"{spec['label']} の値が不正です")
            if t == "int" and (isinstance(v, bool) or not isinstance(v, int) or v < spec.get("min", 0)):
                raise ValueError(f"{spec['label']} は {spec.get('min', 0)} 以上の整数にしてください")
            if t == "enum" and v not in spec["values"] and not (k == "theme" and isinstance(v, str)
                                                                and v.startswith("custom:")):
                raise ValueError(f"{spec['label']} の値が不正です: {v}")
        # 読み込みから書き込みまでの間に Claude Code が書き換える可能性を小さくするため、直前に読む
        data = self._load()
        for k, v in changes.items():
            if v is None:
                data.pop(k, None)
            else:
                data[k] = v
        write_json_atomic(self.path, data)
