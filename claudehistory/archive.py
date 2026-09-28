"""セッション JSONL のバックアップ

Claude Code は cleanupPeriodDays（既定 30 日）より古いセッションファイルを削除する。
消える前に ~/.claude/projects/ の JSONL を別フォルダへコピーしておき、
ビューアは元のファイルとバックアップの両方を読む。
"""
import os
import shutil
import sys
import threading
import time
from pathlib import Path

from .reader import _is_session_file


def sync_archive(src_projects: Path, dst_projects: Path) -> int:
    """src のセッション JSONL を dst へコピーする。コピーした件数を返す。

    dst に無いか、src の方がサイズ・更新時刻が変わっているファイルだけをコピーする。
    src 側で削除されたファイルは dst からは消さない（それがバックアップの目的）。
    """
    if not src_projects.is_dir():
        return 0
    copied = 0
    for proj_dir in src_projects.iterdir():
        if not proj_dir.is_dir():
            continue
        for f in proj_dir.glob("*.jsonl"):
            if not _is_session_file(f.stem):
                continue
            dst = dst_projects / proj_dir.name / f.name
            try:
                st = f.stat()
                if dst.exists():
                    dt = dst.stat()
                    if dt.st_size == st.st_size and int(dt.st_mtime) == int(st.st_mtime):
                        continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                # 書きかけのファイルを残さないよう一時ファイル経由で置き換える
                tmp = dst.with_name(dst.name + ".tmp")
                shutil.copy2(f, tmp)
                os.replace(tmp, dst)
                copied += 1
            except OSError as e:
                print(f"Warning: バックアップに失敗しました: {f}: {e}", file=sys.stderr)
    return copied


def start_archive_thread(src_projects: Path, dst_projects: Path, interval_sec: int) -> None:
    """起動直後と interval_sec ごとにバックアップを取るデーモンスレッドを開始する"""
    def _loop():
        while True:
            n = sync_archive(src_projects, dst_projects)
            if n:
                print(f"バックアップ: {n} 件のセッションを保存しました")
            time.sleep(interval_sec)

    threading.Thread(target=_loop, daemon=True, name="archive-sync").start()
