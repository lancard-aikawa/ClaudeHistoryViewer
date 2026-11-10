"""ゴミ箱: サイドバーで選んだセッションを、元の場所とバックアップの全部から移す

元（~/.claude/projects）だけを消しても、ビューアはバックアップ（SessionVault の mirror・内蔵のバックアップ）から
読むので、一覧から消えない。そこで次のものをまとめてゴミ箱（~/.claude/chat-viewer-trash/<項目>/）へ移す。

- projects・SessionVault の mirror・内蔵のバックアップの <project>/<session>.jsonl と <project>/<session>/
  （サブエージェントと、長いツール結果）
- SessionVault の generations/<project>/<session>.jsonl@<時刻> と generations/<project>/<session>/

ゴミ箱からは「戻す」（元の場所へ移し戻す）と「消去」（本当に消す）ができる。消去するまでディスクは空かない。
"""
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .archive import BACKUP_LOCK
from .reader import _is_session_file

MANIFEST = "manifest.json"
# これより新しく書かれたセッションは、Claude Code が使っている途中とみなして移さない
ACTIVE_SEC = 5 * 60


class TrashError(Exception):
    pass


def _long(p: Path) -> str:
    """Windows の 260 文字を超えるパス（SessionVault の世代は名前に @時刻 が付いて長い）も扱える形"""
    s = str(p)
    if sys.platform != "win32" or s.startswith("\\\\?\\"):
        return s
    s = os.path.abspath(s)
    return "\\\\?\\UNC\\" + s[2:] if s.startswith("\\\\") else "\\\\?\\" + s


def _size(p: Path) -> int:
    lp = _long(p)
    if os.path.isfile(lp):
        return os.path.getsize(lp)
    total = 0
    for dirpath, _, names in os.walk(lp):
        for n in names:
            try:
                total += os.path.getsize(os.path.join(dirpath, n))
            except OSError:
                pass
    return total


def _project_dirs(root: Path, project_id: str) -> list:
    """root の下の、大文字・小文字を無視して project_id と同じ名前のフォルダ。
    project_id はパスにつながず、在るフォルダの名前と比べるだけにする（../ などを渡されても外へ出ない）"""
    if not root.is_dir():
        return []
    key = project_id.casefold()
    return [d for d in root.iterdir() if d.is_dir() and d.name.casefold() == key]


class Trash:
    def __init__(self, trash_dir: Path, reader, vault: Path | None = None, sv=None):
        self.dir = trash_dir
        self.reader = reader
        self.vault = vault
        self.sv = sv

    # ---- 移すものを集める ----

    def _targets(self, project_id: str, session_id: str) -> list:
        """[(移すもの, 元の木の中での位置の説明)]。元のファイルを先にする（Claude Code が開いていて失敗しやすいので、最初に試す）"""
        out = []
        for root in self.reader._roots():
            for d in _project_dirs(root, project_id):
                for p in (d / f"{session_id}.jsonl", d / session_id):
                    if os.path.exists(_long(p)):
                        out.append(p)
        if self.vault:
            for d in _project_dirs(self.vault / "generations", project_id):
                prefix = f"{session_id}.jsonl@"
                out += sorted(p for p in d.iterdir() if p.name.startswith(prefix))
                if (d / session_id).is_dir():
                    out.append(d / session_id)
        return out

    def _lock(self):
        """ビューアのバックアップと、別のプロセスの SessionVault（タスクスケジューラ）が写している最中には動かさない"""
        if not BACKUP_LOCK.acquire(timeout=60):
            raise TrashError("バックアップが終わらないので、あとでもう一度試してください")
        vault_lock = None
        if self.sv and self.vault:
            vault_lock = self.sv.vault.Vault(self.vault).lock()
            try:
                vault_lock.__enter__()
            except self.sv.vault.VaultLocked:
                BACKUP_LOCK.release()
                raise TrashError("SessionVault がバックアップ中です。終わってからもう一度試してください")
        return _Release(vault_lock)

    # ---- 操作 ----

    def put(self, items: list) -> dict:
        """items: [{"project_id", "session_id"}]。{"moved": [...], "errors": [...]}"""
        moved, errors = [], []
        with self._lock():
            for it in items:
                pid, sid = str(it.get("project_id", "")), str(it.get("session_id", ""))
                try:
                    moved.append(self._put_one(pid, sid))
                except TrashError as e:
                    errors.append({"project_id": pid, "session_id": sid, "error": str(e)})
        return {"moved": moved, "errors": errors}

    def _put_one(self, pid: str, sid: str) -> dict:
        if not _is_session_file(sid):
            raise TrashError("セッションの ID ではありません")
        files = self.reader._session_files(pid)
        if sid not in files:
            raise TrashError("見つかりません")
        main, _ = files[sid]
        title, timestamp, count = self.reader._session_meta(main)
        cwd = self.reader._head_meta(main)[0]
        for d in _project_dirs(self.reader.projects_dir, pid):
            src = d / f"{sid}.jsonl"
            if src.is_file() and time.time() - src.stat().st_mtime < ACTIVE_SEC:
                raise TrashError("5 分以内に書き込まれています。Claude Code で使っている途中かもしれないので移しません")
        targets = self._targets(pid, sid)

        now = datetime.now(timezone.utc)
        entry = self.dir / f"{now:%Y%m%dT%H%M%S}-{sid}"
        n = 1
        while entry.exists():
            entry = self.dir / f"{now:%Y%m%dT%H%M%S}-{sid}-{n}"
            n += 1
        done = []
        try:
            for i, p in enumerate(targets):
                rel = f"files/{i}/{p.name}"
                dst = entry / rel
                size = _size(p)
                os.makedirs(_long(dst.parent), exist_ok=True)
                shutil.move(_long(p), _long(dst))
                done.append({"from": str(p), "to": rel, "size": size})
        except OSError as e:
            # 途中で失敗したら（Claude Code が開いている、など）移した分を戻す
            for m in reversed(done):
                try:
                    shutil.move(_long(entry / m["to"]), _long(Path(m["from"])))
                except OSError:
                    pass
            shutil.rmtree(_long(entry), ignore_errors=True)
            raise TrashError(f"移せませんでした（開いているアプリを閉じてください）: {e}")
        manifest = {
            "project_id": pid, "session_id": sid, "title": title, "timestamp": timestamp,
            "message_count": count, "cwd": cwd, "trashed_at": now.isoformat(timespec="seconds"),
            "size": sum(m["size"] for m in done), "files": done,
        }
        with open(entry / MANIFEST, "w", encoding="utf-8", newline="\n") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        self.reader.forget(m["from"] for m in done)
        return {"id": entry.name, **{k: manifest[k] for k in ("project_id", "session_id", "title", "size")}}

    def list(self) -> list:
        out = []
        if not self.dir.is_dir():
            return out
        for entry in self.dir.iterdir():
            m = self._manifest(entry)
            if m:
                out.append({"id": entry.name, **{k: v for k, v in m.items() if k != "files"},
                            "file_count": len(m.get("files", []))})
        out.sort(key=lambda x: x.get("trashed_at") or "", reverse=True)
        return out

    def restore(self, ids: list) -> dict:
        restored, errors = [], []
        with self._lock():
            for eid in ids:
                try:
                    restored.append(self._restore_one(str(eid)))
                except TrashError as e:
                    errors.append({"id": eid, "error": str(e)})
        return {"restored": restored, "errors": errors}

    def _restore_one(self, eid: str) -> dict:
        entry = self._entry(eid)
        m = self._manifest(entry)
        if not m:
            raise TrashError("ゴミ箱に見つかりません")
        clash = [f["from"] for f in m["files"] if os.path.exists(_long(Path(f["from"])))]
        if clash:
            raise TrashError(f"元の場所に同じものがあるので戻せません: {clash[0]}")
        for f in m["files"]:
            src = entry / f["to"]
            if not os.path.exists(_long(src)):
                continue
            os.makedirs(_long(Path(f["from"]).parent), exist_ok=True)
            try:
                shutil.move(_long(src), _long(Path(f["from"])))
            except OSError as e:
                raise TrashError(f"戻せませんでした: {f['from']}: {e}")
        shutil.rmtree(_long(entry), ignore_errors=True)
        return {"id": eid, "project_id": m["project_id"], "session_id": m["session_id"]}

    def purge(self, ids: list) -> dict:
        """本当に消す。消したもの [{"id", "project_id", "session_id", "size"}]"""
        purged, errors = [], []
        for eid in ids:
            try:
                entry = self._entry(str(eid))
            except TrashError as e:
                errors.append({"id": eid, "error": str(e)})
                continue
            m = self._manifest(entry)
            if not m:
                errors.append({"id": eid, "error": "ゴミ箱に見つかりません"})
                continue
            shutil.rmtree(_long(entry), ignore_errors=True)
            if os.path.exists(_long(entry)):
                errors.append({"id": eid, "error": "消せないファイルがありました（開いているアプリを閉じてください）"})
                continue
            purged.append({"id": eid, "project_id": m["project_id"], "session_id": m["session_id"],
                           "size": m.get("size", 0)})
        return {"purged": purged, "errors": errors}

    def _entry(self, eid: str) -> Path:
        # 名前だけを受け付ける（区切り文字や .. を含むものは、ゴミ箱の外を指しうる）
        if not eid or eid in (".", "..") or any(c in eid for c in "/\\:"):
            raise TrashError("項目の名前が不正です")
        return self.dir / eid

    @staticmethod
    def _manifest(entry: Path) -> dict | None:
        try:
            with open(entry / MANIFEST, encoding="utf-8") as f:
                m = json.load(f)
            return m if isinstance(m, dict) and isinstance(m.get("files"), list) else None
        except (OSError, ValueError):
            return None


class _Release:
    def __init__(self, vault_lock):
        self.vault_lock = vault_lock

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            if self.vault_lock is not None:
                self.vault_lock.__exit__(*exc)
        finally:
            BACKUP_LOCK.release()
