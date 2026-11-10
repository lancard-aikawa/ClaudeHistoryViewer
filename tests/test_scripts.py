"""start.cmd / stop.cmd / scripts/*.ps1 must be ASCII only with CRLF line endings.

Windows PowerShell 5.1 reads BOM-less UTF-8 as the ANSI code page and cmd.exe misreads UTF-8 and
LF-only batch files, so a single non-ASCII character breaks them on other machines.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = sorted([*ROOT.glob("*.cmd"), *(ROOT / "scripts").glob("*.ps1"), *(ROOT / "scripts").glob("*.cmd")])


class ScriptsTest(unittest.TestCase):
    def test_found(self):
        self.assertTrue(FILES)

    def test_ascii_crlf(self):
        for f in FILES:
            with self.subTest(f.name):
                data = f.read_bytes()
                self.assertTrue(data.isascii(), f"{f.name} has non-ASCII bytes")
                self.assertNotIn(b"\n", data.replace(b"\r\n", b""), f"{f.name} has LF without CR")


if __name__ == "__main__":
    unittest.main()
