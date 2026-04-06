# Claude Code JSONL 仕様メモ

Claude Code が `~/.claude/projects/<project>/<session-uuid>.jsonl` に記録するデータ形式。
1 行 = 1 JSON オブジェクト（JSON Lines 形式）。

---

## 共通フィールド（ほぼ全レコード）

| フィールド | 型 | 説明 |
|---|---|---|
| `type` | string | レコード種別（後述） |
| `uuid` | string | このレコードの UUID |
| `sessionId` | string | セッション UUID |
| `parentUuid` | string | 親レコードの UUID |
| `timestamp` | string | ISO 8601 タイムスタンプ |
| `isSidechain` | bool | サブセッション（subagent 等）かどうか |
| `cwd` | string | ワーキングディレクトリ |
| `version` | string | Claude Code バージョン |
| `gitBranch` | string | git ブランチ名 |
| `entrypoint` | string | `cli` / `ide` 等 |
| `userType` | string | `external`（人間）/ `internal` |

---

## レコード種別一覧

### 会話本体

#### `user`
ユーザー側メッセージ。tool_result も含む。

追加フィールド：
- `message.content[]` — コンテンツブロック配列（後述）
- `promptId` — プロンプト ID
- `permissionMode` — 送信時のパーミッションモード

#### `assistant`
Claude の応答。

追加フィールド：
- `message.content[]` — コンテンツブロック配列（後述）
- `requestId` — API リクエスト ID

---

### セッションメタ

#### `ai-title`
Claude が生成したセッションタイトル。

| フィールド | 説明 |
|---|---|
| `aiTitle` | タイトル文字列 |

#### `permission-mode`
パーミッションモードの記録。

| フィールド | 説明 |
|---|---|
| `permissionMode` | `default` / `bypass` / `auto_edit` 等 |

#### `last-prompt`
セッション再開用の最終プロンプト保存。

| フィールド | 説明 |
|---|---|
| `lastPrompt` | テキスト |

#### `pr-link`
セッション中に作成された PR の記録。

| フィールド | 説明 |
|---|---|
| `prNumber` | PR 番号 |
| `prUrl` | URL |
| `prRepository` | `owner/repo` |

---

### システム・フック

#### `system`
ターン単位の計測値等。

| フィールド | 説明 |
|---|---|
| `subtype` | `turn_duration` 等 |
| `durationMs` | ターン処理時間（ms） |
| `isMeta` | bool |

#### `progress`
フック（PreToolUse / PostToolUse 等）の実行イベント。

| フィールド | 説明 |
|---|---|
| `data.type` | `hook_progress` |
| `data.hookEvent` | `PreToolUse` / `PostToolUse` 等 |
| `data.hookName` | フック識別子（例: `PostToolUse:Glob`） |
| `parentToolUseID` | 紐づく tool_use の ID |

#### `attachment`
ツール定義の差分等。

| フィールド | 説明 |
|---|---|
| `attachment.type` | `deferred_tools_delta` 等 |
| `attachment.addedNames` | 追加されたツール名リスト |

---

### キュー操作

#### `queue-operation`
Claude 処理中にユーザーが入力したメッセージのキュー操作。

| `operation` | 説明 |
|---|---|
| `enqueue` | ユーザーがメッセージを入力した（`content` フィールドにテキスト） |
| `dequeue` | キューから取り出して処理 |
| `remove` | キューから削除（キャンセル） |
| `popAll` | 全キューを取り出し（`content` フィールドにテキスト） |

> **⚠ 注意**: `enqueue` されたメッセージが後続の `user` メッセージの `text` ブロックに
> 現れないことがある（Claude がツール連鎖中に受け取った発言）。
> この場合、ビューアには表示できない。

---

### ファイル履歴

#### `file-history-snapshot`
ファイル内容のスナップショット（アンドゥ用）。

| フィールド | 説明 |
|---|---|
| `snapshot` | ファイル内容 |
| `messageId` | 紐づくメッセージ ID |
| `isSnapshotUpdate` | bool |

---

## コンテンツブロック（`message.content[]`）

### `text` ブロック
```json
{ "type": "text", "text": "..." }
```
- **user** — ユーザーの入力テキスト
- **assistant** — Claude の応答テキスト

ユーザーの `text` ブロックには IDE が自動挿入するタグが混入することがある：
- `<ide_opened_file>...</ide_opened_file>` — 開いているファイル
- `<ide_selection>...</ide_selection>` — 選択中のテキスト

---

### `thinking` ブロック（assistant のみ）
```json
{ "type": "thinking", "thinking": "...", "signature": "..." }
```
Claude の拡張思考（Extended Thinking）内容。`signature` は Anthropic の署名。

---

### `tool_use` ブロック（assistant のみ）
```json
{
  "type": "tool_use",
  "id": "toolu_xxxxxxxxxx",
  "name": "Bash",
  "input": { "command": "..." }
}
```
Claude がツールを呼び出す宣言。

主なツール名：`Edit` / `Bash` / `Read` / `Grep` / `Write` / `Glob` /
`Agent` / `Skill` / `WebFetch` / `WebSearch` / `AskUserQuestion` /
`EnterPlanMode` / `ExitPlanMode` / `TaskCreate` / `TaskUpdate` / `TaskOutput`

---

### `tool_result` ブロック（user のみ）
```json
{
  "type": "tool_result",
  "tool_use_id": "toolu_xxxxxxxxxx",
  "content": "...",
  "is_error": false
}
```
ツール実行結果。

#### `content` の形式

| 形式 | 状況 |
|---|---|
| `string` | 通常のツール結果（大多数） |
| `list` | Agent ツールの結果（後述） |

#### `is_error: true` のパターン

| 内容 | 状況 |
|---|---|
| `"Exit code N\n..."` | コマンド失敗 |
| `"<tool_use_error>...</tool_use_error>"` | ツール実行エラー |
| `"The user doesn't want to proceed..."` | ユーザーが No で拒否 |
| `"...The user provided the following reason for the rejection: [理由]"` | ユーザーが Reason 付きで拒否 |

Reason 付き拒否の場合、`"The user provided the following reason for the rejection:"` 以降のテキストがユーザーの発言内容。

---

### Agent ツール結果の `content` リスト
```json
[
  { "type": "text", "text": "サブエージェントの回答テキスト" },
  { "type": "tool_reference", "tool_name": "Write" },
  { "type": "image", "source": { "media_type": "image/png", "data": "base64..." } }
]
```

| アイテム型 | 説明 |
|---|---|
| `text` | サブエージェントの応答テキスト |
| `tool_reference` | サブエージェントが使ったツール名の参照 |
| `image` | サブエージェントが返した画像 |

---

## スキル展開メッセージの挙動

`/skill-name` を呼び出したとき、JSONL に以下の順で記録される：

1. **assistant** — `tool_use: Skill`（チップとして表示）
2. **user** — `tool_result: "Launching skill: X"`（`is_error` なし、テキストなし）
3. **user** — `text: [スキルの展開内容]`（ハーネスが挿入するプロンプト本文）

3 番はユーザーが実際に入力したテキストではない。ビューアでは非表示にすべき。

---

## 既知の表示制限

| 状況 | 原因 | 対処 |
|---|---|---|
| ツール実行中のユーザー発言が消える | `queue-operation: enqueue` にはあるが後続 `user` メッセージの `text` ブロックに入らない | 不可（データなし） |
| スキル展開が右バブルで表示される | `user.text` ブロックとして挿入されるため | ビューア側で検出・除外 |
| Reason 付き拒否が表示されない | `tool_result.content` 文字列に埋め込まれているため | 文字列からパターンで抽出して表示 |
