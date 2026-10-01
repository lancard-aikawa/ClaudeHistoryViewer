"""memory（~/.claude/projects/<project>/memory/*.md）の一覧と、それを書いた会話

どの会話で書いたかは、SessionVault が作る索引（<保管庫>/index/memory.json）から読む。
索引が無くても、今ある memory と保管庫に残っている memory は一覧に出す（書いた会話は空）。
"""
import json
import re
from pathlib import Path

_KEY = re.compile(r"^([^/\\]+)/memory/([^/\\]+\.md)$")


class MemoryIndex:
    def __init__(self, projects_dir: Path, vault: Path | None):
        self.projects_dir = projects_dir
        self.vault = vault
        self.mirror = vault / "mirror" if vault else None

    def _roots(self) -> list:
        return [r for r in (self.projects_dir, self.mirror) if r]

    def _index(self) -> dict:
        if not self.vault:
            return {}
        try:
            with open(self.vault / "index" / "memory.json", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def list(self, project_ids: list) -> dict:
        """{"generated": 索引を作った時刻, "items": [...]}。項目の project はビューアのプロジェクト ID に寄せる"""
        canon = {p.casefold(): p for p in project_ids}
        index = self._index()
        items: dict = {}

        def item(project: str, name: str) -> dict:
            pid = canon.get(project.casefold(), project)
            key = f"{pid}/memory/{name}"
            return items.setdefault(key.casefold(), {
                "key": key, "project": pid, "name": name, "exists": False, "backed_up": False, "writes": []})

        for i, root in enumerate(self._roots()):
            if not root.is_dir():
                continue
            for f in root.glob("*/memory/*.md"):
                it = item(f.parent.parent.name, f.name)
                if i == 0:
                    it["exists"] = True
                else:
                    it["backed_up"] = True
        for key, entry in index.get("memory", {}).items():
            m = _KEY.match(key)
            if not m:
                continue
            it = item(m.group(1), m.group(2))
            for w in entry.get("writes", []):
                it["writes"].append({**w, "project": canon.get(str(w.get("project", "")).casefold(), w.get("project"))})
        out = sorted(items.values(), key=lambda x: (x["project"].casefold(), x["name"] != "MEMORY.md", x["name"]))
        return {"generated": index.get("generated"), "vault": str(self.vault) if self.vault else None, "items": out}

    def read(self, key: str) -> dict | None:
        """本文。今あるものを優先し、消えていれば保管庫の版を返す。key の形が違えば None"""
        m = _KEY.match(key)
        if not m:
            return None
        project, name = m.group(1).casefold(), m.group(2)
        for i, root in enumerate(self._roots()):
            if not root.is_dir():
                continue
            for d in root.iterdir():
                f = d / "memory" / name
                if d.is_dir() and d.name.casefold() == project and f.is_file():
                    return {"text": f.read_text(encoding="utf-8", errors="replace"), "from_backup": i > 0}
        return None
