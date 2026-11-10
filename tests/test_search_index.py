import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claudehistory.reader import _read_session_meta  # noqa: E402
from claudehistory.search_index import SearchIndex, find  # noqa: E402


def line(role: str, uuid: str, text: str, **extra) -> str:
    content = text if role == "user" else [{"type": "text", "text": text}]
    return json.dumps({"type": role, "uuid": uuid, "timestamp": "2026-01-01T00:00:00Z",
                       "message": {"role": role, "content": content}, **extra}, ensure_ascii=False) + "\n"


class SearchIndexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = Path(self.tmp.name) / "s.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, text: str, mode: str = "w") -> None:
        with open(self.f, mode, encoding="utf-8", newline="\n") as fp:
            fp.write(text)

    def uuids(self, idx, q, kind="text"):
        return [h["uuid"] for h in find(idx.entries(self.f), q, kind)]

    def test_reads_appended_lines_only_after_complete(self):
        idx = SearchIndex()
        self.write(line("user", "u1", "ゴミ箱を作る") + line("assistant", "a1", "Trash を作ります"))
        self.assertEqual(self.uuids(idx, "trash"), ["a1"])
        # 書きかけ（改行で終わらない）の行は、まだ読まない
        partial = line("assistant", "a2", "trash again")
        self.write(partial[:-10], "a")
        self.assertEqual(self.uuids(idx, "trash"), ["a1"])
        self.write(partial[-10:], "a")
        self.assertEqual(self.uuids(idx, "trash"), ["a1", "a2"])

    def test_rebuilds_when_file_is_replaced(self):
        idx = SearchIndex()
        self.write(line("user", "u1", "alpha") + line("user", "u2", "beta"))
        self.assertEqual(self.uuids(idx, "alpha"), ["u1"])
        self.write(line("user", "x1", "gamma gamma gamma") + line("user", "x2", "alpha!"))
        self.assertEqual(self.uuids(idx, "alpha"), ["x2"])

    def test_skips_lines_not_shown(self):
        idx = SearchIndex()
        self.write(line("user", "m1", "hidden", isMeta=True)
                   + line("user", "n1", "<task-notification><summary>done</summary></task-notification>")
                   + json.dumps({"type": "attachment", "text": "hidden"}) + "\n"
                   + line("user", "u1", "shown hidden"))
        self.assertEqual(self.uuids(idx, "hidden"), ["u1"])

    def test_file_search_and_escaped_text(self):
        idx = SearchIndex()
        tool = json.dumps({"type": "assistant", "uuid": "a1", "timestamp": "",
                           "message": {"content": [{"type": "tool_use", "name": "Read",
                                                    "input": {"file_path": "C:\\Repos\\App\\Main.py"}}]}}) + "\n"
        self.write(tool + line("user", "u1", 'say "quoted"\nnext'))
        self.assertEqual(self.uuids(idx, "repos\\app", "file"), ["a1"])
        self.assertEqual(self.uuids(idx, '"quoted"\nnext'), ["u1"])

    def test_saved_index_is_reused(self):
        path = Path(self.tmp.name) / "index.json"
        self.write(line("user", "u1", "persist me"))
        idx = SearchIndex(path)
        idx.entries(self.f)
        idx.save(force=True)
        again = SearchIndex(path)
        self.assertEqual(self.uuids(again, "persist"), ["u1"])

    def test_session_meta(self):
        self.write(line("user", "u1", "hi") + json.dumps({"type": "ai-title", "aiTitle": "題"}) + "\n"
                   + line("assistant", "a1", "yo") + json.dumps({"type": "attachment"}) + "\n")
        self.assertEqual(_read_session_meta(self.f), ("題", "2026-01-01T00:00:00Z", 2))


if __name__ == "__main__":
    unittest.main()
