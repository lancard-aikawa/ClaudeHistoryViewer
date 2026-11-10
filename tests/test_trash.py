import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claudehistory.archive import load_sessionvault  # noqa: E402
from claudehistory.reader import ClaudeDataReader  # noqa: E402
from claudehistory.trash import Trash  # noqa: E402

SID = "11111111-2222-3333-4444-555555555555"
OTHER = "99999999-8888-7777-6666-555555555555"
PROJ = "C--work-demo"


def write_session(path: Path, title: str = "demo", age_sec: int = 3600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        {"type": "user", "uuid": "u1", "sessionId": path.stem, "cwd": "C:\\work\\demo",
         "timestamp": "2026-01-01T00:00:00Z", "message": {"role": "user", "content": "hello world"}},
        {"type": "ai-title", "aiTitle": title},
    ]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for o in lines:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    old = time.time() - age_sec
    os.utime(path, (old, old))


class TrashTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.claude = root / ".claude"
        self.vault = root / "vault"
        self.archive = root / "archive" / "projects"
        # 元・mirror・内蔵のバックアップ・世代のすべてに同じセッションがある
        self.src = self.claude / "projects" / PROJ / f"{SID}.jsonl"
        write_session(self.src)
        (self.src.parent / SID / "subagents").mkdir(parents=True)
        (self.src.parent / SID / "subagents" / "agent-a.jsonl").write_text("{}\n", encoding="utf-8")
        write_session(self.vault / "mirror" / PROJ / f"{SID}.jsonl")
        write_session(self.archive / PROJ.lower() / f"{SID}.jsonl")  # 大文字・小文字が違う綴り
        gen = self.vault / "generations" / PROJ / f"{SID}.jsonl@20260101T000000Z"
        gen.parent.mkdir(parents=True)
        gen.write_text("old\n", encoding="utf-8")
        write_session(self.claude / "projects" / PROJ / f"{OTHER}.jsonl", "other")
        self.reader = ClaudeDataReader(self.claude, [self.vault / "mirror", self.archive])
        self.trash = Trash(self.claude / "chat-viewer-trash", self.reader, self.vault, None)

    def tearDown(self):
        self.tmp.cleanup()

    def ids(self):
        return {s["id"] for s in self.reader.list_sessions(PROJ)}

    def test_put_moves_every_copy_and_restore_puts_back(self):
        self.assertEqual(self.ids(), {SID, OTHER})
        r = self.trash.put([{"project_id": PROJ, "session_id": SID}])
        self.assertEqual(r["errors"], [])
        # バックアップから復活しない
        self.assertEqual(self.ids(), {OTHER})
        self.assertFalse(self.src.exists())
        self.assertFalse((self.src.parent / SID).exists())
        self.assertEqual(list((self.vault / "generations" / PROJ).iterdir()), [])
        items = self.trash.list()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "demo")
        self.assertEqual(items[0]["file_count"], 5)

        r = self.trash.restore([items[0]["id"]])
        self.assertEqual(r["errors"], [])
        self.assertEqual(self.ids(), {SID, OTHER})
        self.assertTrue((self.src.parent / SID / "subagents" / "agent-a.jsonl").is_file())
        self.assertTrue((self.vault / "generations" / PROJ / f"{SID}.jsonl@20260101T000000Z").is_file())
        self.assertEqual(self.trash.list(), [])

    def test_purge_deletes(self):
        self.trash.put([{"project_id": PROJ, "session_id": SID}])
        eid = self.trash.list()[0]["id"]
        r = self.trash.purge([eid])
        self.assertEqual([p["session_id"] for p in r["purged"]], [SID])
        self.assertEqual(self.trash.list(), [])
        self.assertEqual(self.ids(), {OTHER})

    def test_refuses_session_in_use(self):
        write_session(self.src, age_sec=0)
        r = self.trash.put([{"project_id": PROJ, "session_id": SID}])
        self.assertEqual(r["moved"], [])
        self.assertIn("5 分以内", r["errors"][0]["error"])
        self.assertTrue(self.src.exists())

    def test_rejects_bad_names(self):
        r = self.trash.put([{"project_id": "..", "session_id": SID},
                            {"project_id": PROJ, "session_id": "../../x"}])
        self.assertEqual(r["moved"], [])
        self.assertEqual(len(r["errors"]), 2)
        for bad in ("..", "../x", "a\\b", "C:x"):
            self.assertEqual(len(self.trash.purge([bad])["errors"]), 1)
        self.assertEqual(len(self.trash.restore(["../x"])["errors"]), 1)

    def test_restore_refuses_when_original_came_back(self):
        self.trash.put([{"project_id": PROJ, "session_id": SID}])
        write_session(self.src)
        r = self.trash.restore([self.trash.list()[0]["id"]])
        self.assertIn("同じもの", r["errors"][0]["error"])
        self.assertEqual(len(self.trash.list()), 1)

    @unittest.skipUnless(sys.platform == "win32", "開いているファイルを動かせないのは Windows だけ")
    def test_rolls_back_when_a_file_is_open(self):
        mirror = self.vault / "mirror" / PROJ / f"{SID}.jsonl"
        with open(mirror, "rb"):
            r = self.trash.put([{"project_id": PROJ, "session_id": SID}])
        self.assertEqual(r["moved"], [])
        self.assertEqual(len(r["errors"]), 1)
        # 先に移した元のファイルも戻っている
        self.assertTrue(self.src.is_file())
        self.assertTrue((self.src.parent / SID / "subagents" / "agent-a.jsonl").is_file())
        self.assertEqual(self.trash.list(), [])

    def test_works_while_holding_sessionvault_lock(self):
        sv = load_sessionvault("")
        if sv is None:
            self.skipTest("SessionVault のサブモジュールが無い")
        trash = Trash(self.claude / "chat-viewer-trash", self.reader, self.vault, sv)
        # 同じプロセスの中では入れ子で取れるので、これで動くことだけを見る（別のプロセスとの重なりは SessionVault 側で試験済み）
        with sv.vault.Vault(self.vault).lock():
            r = trash.put([{"project_id": PROJ, "session_id": SID}])
        self.assertEqual(r["errors"], [])


if __name__ == "__main__":
    unittest.main()
