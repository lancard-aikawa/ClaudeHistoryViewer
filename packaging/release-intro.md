<!-- Release の本文の後半。release.yml が CHANGELOG の節のあとに付ける。この注記は消される -->
## 初めての方へ

Claude Code のセッション履歴（`~/.claude/projects/` の JSONL）を、ブラウザでチャットの形で読み返すビューアです。

### 要るもの

- Python 3.10 以上（外部ライブラリは不要）

### 使い方

1. `ClaudeHistoryViewer-<版>.zip` を好きな場所に展開する
2. Windows は `start.cmd` をダブルクリック（窓を出さずに裏で動く。止めるときは `stop.cmd`）。
   ほかの OS は `python claude_chat_viewer.py`
3. ブラウザで `http://localhost:57080` が開く

設定はフォルダの `settings.json`（無ければ既定値。見本は `settings.json.sample`）か、画面の「⚙ 設定」で変えられます。

### バックアップと SessionVault

Claude Code は古いセッション（既定 30 日）を消すので、ビューアは裏でバックアップを取ります。
zip には [SessionVault](https://github.com/lancard-aikawa/SessionVault) を同梱しているので、バックアップはそちらで取り、
サブエージェント・memory も残ります。保管庫は既定で `vendor/SessionVault/vault` にできます。

同じ zip の SessionVault は [RepoTether](https://github.com/lancard-aikawa/RepoTether) の「ログの検査」からも使えます
（RepoTether の設定「SessionVault の場所」にこのフォルダを指定）。
