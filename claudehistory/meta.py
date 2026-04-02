import json
from pathlib import Path


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

    def set_project(self, project_id: str, meta: dict):
        d = self._load()
        d.setdefault("projects", {})[project_id] = meta
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
