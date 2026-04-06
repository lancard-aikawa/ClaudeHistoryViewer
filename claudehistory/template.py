import sys
from pathlib import Path

if sys.version_info >= (3, 9):
    from importlib.resources import files as _res_files

    def _read(filename: str) -> str:
        return (_res_files("claudehistory.static") / filename).read_text(encoding="utf-8")
else:
    _STATIC = Path(__file__).parent / "static"

    def _read(filename: str) -> str:
        return (_STATIC / filename).read_text(encoding="utf-8")


def build_template() -> str:
    html   = _read("index.html")
    style  = _read("style.css")
    script = _read("app.js")
    return html.replace("/* {{STYLE}} */", style).replace("// {{SCRIPT}}", script)


HTML_TEMPLATE: str = build_template()
