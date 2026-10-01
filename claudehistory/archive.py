"""セッション JSONL のバックアップ

Claude Code は cleanupPeriodDays（既定 30 日）より古いセッションファイルを削除する。
消える前に ~/.claude/projects/ を別の場所へコピーしておき、ビューアは元のファイルとバックアップの両方を読む。

SessionVault（https://github.com/lancard-aikawa/SessionVault、vendor/SessionVault にサブモジュールとして同梱）が
読み込めれば、バックアップはそちらに任せる。
サブエージェント・tool-results・memory も残り、元が縮んだり壊れたりしても前の版が世代として残る。
読み込めなければ、このファイルの sync_archive（セッション本体の JSONL を写すだけ）で取る。
"""
import os
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from .reader import _is_session_file

# 設定画面に出す、最後のバックアップの結果。pythonw で動かすと print が見えないため
STATUS: dict = {"engine": None, "store": None, "last_run": None, "summary": "", "errors": []}

# サブモジュールとして同梱した SessionVault（git clone --recursive か git submodule update --init で取れる）
VENDORED_SRC = Path(__file__).resolve().parent.parent / "vendor" / "SessionVault" / "src"


def load_sessionvault(src_dir: str):
    """SessionVault を読み込む。src_dir はリポジトリの src フォルダ。
    空なら同梱のサブモジュール、それも無ければインストール済みのものを探す。読み込めなければ None"""
    explicit = bool(src_dir)
    if not src_dir and (VENDORED_SRC / "sessionvault").is_dir():
        src_dir = str(VENDORED_SRC)
    if src_dir:
        p = str(Path(src_dir).expanduser())
        if p not in sys.path:
            sys.path.insert(0, p)
    try:
        import sessionvault.backup
        import sessionvault.config
        import sessionvault.memindex
        import sessionvault.paths
        import sessionvault.vault
    except ImportError as e:
        if explicit:
            print(f"Warning: SessionVault を読み込めません（{src_dir}）: {e}", file=sys.stderr)
        return None
    return sessionvault


def sessionvault_settings(sv, config_file: str) -> tuple:
    """(SessionVault の設定, 保管庫の場所) を返す。
    config_file が空なら、読み込んだ SessionVault のリポジトリ直下の sessionvault.json（SessionVault の既定）。
    指定した設定ファイルに vault が無ければ、その設定ファイルの隣の vault/ を使う。
    サブモジュールを読み込んで既定のままだと、保管庫は vendor/SessionVault/vault になる。
    単体の SessionVault と同じ保管庫を使うなら、その sessionvault.json を config_file に渡す"""
    if config_file:
        path = Path(config_file).expanduser()
        # 設定ファイルはまだ無くてよい（SessionVault は無ければ既定値で動く）が、置き場所が無いのは打ち間違いとみなす。
        # そのまま進むと、存在しない場所に保管庫を黙って作ってしまう
        if not path.parent.is_dir():
            raise ValueError(f"SessionVault の設定ファイルのフォルダがありません: {path.parent}")
        cfg = sv.config.load(path)
        return cfg, sv.paths.vault_dir(None, cfg["vault"] or str(path.parent / "vault"))
    cfg = sv.config.load(sv.paths.default_config_path())
    return cfg, sv.paths.vault_dir(None, cfg["vault"])


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


def _run_sessionvault(sv, config_file: str, src_projects: Path, vault_root: Path, first: bool) -> None:
    cfg, _ = sessionvault_settings(sv, config_file)  # 世代の間引きなどの変更は次の回から効く
    try:
        result = sv.backup.run(src_projects, vault_root, cfg)
    except sv.vault.VaultLocked:
        # 定期実行（タスクスケジューラ）などと重なった。次の回に取り直す
        STATUS["summary"] = "別の SessionVault の実行と重なったので、この回は見送りました"
        return
    counts = result.counts
    STATUS["summary"] = ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "変更なし"
    STATUS["errors"] = [f"{p}/{r}: {m}" for p, r, m in result.errors]
    if counts:
        print(f"バックアップ: {STATUS['summary']}")
    # memory の索引は、何か変わったときと起動直後だけ作り直す（全部の記録を読むので数秒かかる）
    if counts or first:
        try:
            sv.memindex.run(src_projects, vault_root)
        except sv.vault.VaultLocked:
            pass


def start_archive_thread(src_projects: Path, dst_projects: Path, interval_sec: int,
                         sv=None, sv_vault: Path | None = None, sv_config: str = "") -> None:
    """起動直後と interval_sec ごとにバックアップを取るデーモンスレッドを開始する。
    sv（SessionVault）があれば保管庫 sv_vault へそちらで取り、dst_projects は使わない"""
    STATUS["engine"] = "SessionVault" if sv else "ビューア内蔵"
    STATUS["store"] = str(sv_vault) if sv else str(dst_projects.parent)

    def _loop():
        first = True
        while True:
            try:
                if sv:
                    _run_sessionvault(sv, sv_config, src_projects, Path(STATUS["store"]), first)
                else:
                    n = sync_archive(src_projects, dst_projects)
                    STATUS["summary"] = f"{n} 件を保存" if n else "変更なし"
                    if n:
                        print(f"バックアップ: {n} 件のセッションを保存しました")
            except Exception as e:  # スレッドが止まるとバックアップが黙って途切れるので、記録して続ける
                STATUS["summary"] = f"失敗しました: {e}"
                print(f"Warning: バックアップに失敗しました: {e}", file=sys.stderr)
            STATUS["last_run"] = datetime.now().astimezone().isoformat(timespec="seconds")
            first = False
            time.sleep(interval_sec)

    threading.Thread(target=_loop, daemon=True, name="archive-sync").start()
