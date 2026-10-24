# jev-mcp

[English](README.md) | 日本語

T3 Code 用の Jev モデルルーティングを、独立した MCP サーバーとして提供します。T3 Code のリポジトリ・サーバー・データベースの外にあるため、公式 T3 Code の更新と衝突しません。分離時点までの履歴は nyattoh/t3code の `extensions/jev-mcp`（`jev-detached/base`）から引き継いでいます。

## 機能

ツールは `jev_route` の 1 つです。タスクの要約、ポリシー、呼び出し側が使えるモデルと reasoning effort の組み合わせを渡すと、Jev（`https://api.typesafe.ai/v1/systemone`）に 1 つを選ばせます。結果は助言です。エージェントはサブエージェントや新しいスレッドのモデル選択に使います。実行中のスレッド自身のモデルは切り替えられません。

各 `requestId` は Jev を呼ぶ前に記録されます。同じ id と同じ入力で再度呼ぶと、Jev を呼ばずに保存済みの決定を返します。同じ id を異なる入力で使うと `duplicate-request` で失敗します。

### 確信度とセキュリティの下限

Jev の選択は、確信度が `max(0.5, 1.5 / 候補数)`（第 2 項の上限は 0.9）未満のとき、または次点との差が 0.15 未満のとき `low-confidence` で拒否されます。呼び出し側は `minConfidence`（0.5〜1）と `minMargin`（0.15〜1）で下限を上げられますが、下げることはできません。下限未満の保存済み決定は再生されません。

セキュリティ・認証・シークレット・デプロイ・リリース・マージ・プッシュ・マイグレーション・本番に関わるタスクは `securitySensitive: true` を指定する必要があります。このとき Jev には `reasoningEffort` が `high`・`xhigh`・`max` の候補だけが渡され、該当がなければ `no-secure-candidate` で失敗します。これらのエラーが出たら、エージェントは手動で強い方を選びます。

## 保存先

`%T3CODE_HOME%\jev\jev.sqlite`（`T3CODE_HOME` 未設定時は `~/.t3/jev/jev.sqlite`）、または `--db <path>`。T3 の `statev2.sqlite` は開きません。

T3 の旧 `jev_execution_requests` テーブルからエクスポートした行は次で取り込めます。

```sh
node src/main.ts --import-legacy jev_execution_requests-<timestamp>.json
```

## 要件

Node 24 以上（TypeScript を直接実行し、`node:sqlite` を使用）。npm 依存なし。サーバーの環境に `TYPESAFE_API_KEY` が必要です。

## 環境変数

| 変数 | 使用者 | 用途 |
| --- | --- | --- |
| `TYPESAFE_API_KEY` | jev-mcp | Jev の API キー。未設定だと `jev_route` は `missing-key` を返します。 |
| `T3CODE_HOME` | jev-mcp, T3 Code | ストアは `%T3CODE_HOME%\jev\jev.sqlite`。未設定なら `~/.t3`。 |

すべての起動経路（ショートカット、自動更新後の再起動を含む）に引き継がれるよう、Windows のユーザー環境変数として設定します。

```powershell
[Environment]::SetEnvironmentVariable('TYPESAFE_API_KEY', '<key>', 'User')
[Environment]::SetEnvironmentVariable('T3CODE_HOME', 'D:\path\to\t3-home', 'User')
```

起動済みのプロセスは古い環境のままなので、設定後に T3 Code を再起動してください。

## テスト

```sh
node --test test/*.test.ts
python -m unittest discover -s skills/bench-ledger-router/tests
```

## フォークのデータベースを公式 T3 Code へ移行する

Jev フォークは独自のマイグレーションを `57 JevExecutionRequests` として記録していました。公式 T3 Code は 57 を `ScheduledTaskWebhooks` に使っており、その履歴では起動を拒否します。`cutover/cutover.ts` はそのようなデータベースを公式ビルドで開けるよう書き換えます。

1. T3 Code を終了します。
2. ドライラン。計画を表示し、データベースを変更せずに新しい `jev_execution_requests-<timestamp>.json` を書き出します。エクスポートは上書きされません。

   ```sh
   node cutover/cutover.ts --db "$T3CODE_HOME/userdata/statev2.sqlite" --export-dir ./jev-export
   ```

3. 適用。データベースを `--backup-dir` にコピーしてから、1 つのトランザクションで `ScheduledTaskWebhooks` スキーマを追加し、`jev_execution_requests` を削除し、57 行目の名前を変更します。コミット前に `quick_check`・スレッド数・マイグレーション履歴を確認し、いずれかが失敗するとロールバックします。

   ```sh
   node cutover/cutover.ts --db "$T3CODE_HOME/userdata/statev2.sqlite" --export-dir ./jev-export --backup-dir ./jev-backup --apply
   ```

4. エクスポートした行を `--import-legacy` で Jev ストアに取り込みます（「保存先」参照）。

認識できない履歴、空でない WAL、別プロセスが書き込みロックを持つデータベースは拒否します。変換済みのデータベースに再実行しても何もしません。

## インストール

```sh
git clone https://github.com/nyattoh/jev-mcp.git D:\develop\works\jev-mcp
```

その後、各プロバイダーに登録します。詳細は [docs/configure.md](docs/configure.md)（英語）を参照してください。

## 設定

T3 Code 側の変更は不要です。各プロバイダーが自分の設定から MCP サーバーを読み込み、T3 はその横に自身の `t3-code` サーバーを追加します。

### Codex

T3 はプロバイダーインスタンスにホームパスが設定されていればそれを `CODEX_HOME` として、なければ Codex の既定（`%USERPROFILE%\.codex`）で Codex を起動します。そのホームの `config.toml` に追加します。

```toml
[mcp_servers.jev]
command = "node"
args = ['D:\develop\works\jev-mcp\src\main.ts']
env_vars = ["TYPESAFE_API_KEY", "T3CODE_HOME"]
```

`env_vars` は T3 の環境から変数を転送するため、キーをファイルに書く必要はありません。T3 がスレッドごとに渡す `mcp_servers` の上書きは `config.toml` とマージされます。`codex mcp get jev` で確認できます。

`approval_policy = "never"`（例: `codex exec`）では MCP ツール呼び出しが `MCP tool call requires approval` で拒否されます。プロンプトなしで `jev_route` を許可するには `[mcp_servers.jev]` に `default_tools_approval_mode = "approve"` を追加します。

### Claude

ユーザースコープに登録すると、T3 の Claude スレッドでも読み込まれます。

```sh
claude mcp add --scope user jev -- node D:\develop\works\jev-mcp\src\main.ts
```

Claude プロバイダーインスタンスが `CLAUDE_CONFIG_DIR` を設定している場合は、同じ `CLAUDE_CONFIG_DIR` でコマンドを実行してください。`claude mcp list` で確認できます。実行中の T3 Claude スレッドでの動作はまだ確認していません。

### WSL バックエンドの T3 Code Desktop

T3 Desktop がサーバーを WSL 内で動かす場合、プロバイダーはディストリ内で動くため上記の Windows 設定は適用されません。

- Desktop は `wsl.exe` に渡す環境から `T3CODE_HOME` を除き、許可リスト（`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、テレメトリ変数）だけを転送します。`TYPESAFE_API_KEY` は含まれません。
- Codex と Claude はディストリのホーム（`~/.codex/config.toml`、`~/.claude.json`）から設定を読みます。
- ディストリ内の `node` は Node 24 以上が必要で、パスは Linux パスにします。

対処:

1. Windows のユーザー変数 `WSLENV` でキーを転送します（既存の値があれば `:TYPESAFE_API_KEY` を追記）。その後 T3 Code を再起動します。

   ```powershell
   [Environment]::SetEnvironmentVariable('WSLENV', 'TYPESAFE_API_KEY', 'User')
   ```

2. `T3CODE_HOME` は届かないので、ディストリ内でストアのパスを明示して登録します。

   ```toml
   [mcp_servers.jev]
   command = "node"
   args = ["/mnt/d/develop/works/jev-mcp/src/main.ts", "--db", "/home/<you>/.t3/jev/jev.sqlite"]
   env_vars = ["TYPESAFE_API_KEY"]
   ```

   ```sh
   claude mcp add --scope user jev -- node /mnt/d/develop/works/jev-mcp/src/main.ts --db ~/.t3/jev/jev.sqlite
   ```

   `/mnt/d` 上のストアも動きますが、9P マウント越しの SQLite ロックは遅く信頼性も低いため、ストアはディストリのホーム配下に置いてください。

## bench-ledger-router スキル

`skills/bench-ledger-router` は T3 Code でモデルと effort のルーティングを計画するエージェントスキルです。公式 T3 MCP ツール（`orchestrator_capabilities`、`delegate_task`、`task_status`、`task_cancel`、`t3_worktree_status`、`t3_thread_launch`、`t3_thread_send`）、`bench-ledger` MCP サーバー、任意でこのサーバーの `jev_route` を使います（`references/decision-gates.md` 参照）。

エージェントがスキルを探す場所にインストールします。raytrek では両方の場所に同じコピーを置いています。

```powershell
Copy-Item -Recurse skills\bench-ledger-router $env:USERPROFILE\.agents\skills\
Copy-Item -Recurse skills\bench-ledger-router $env:USERPROFILE\.claude\skills\
```

`scripts/bench_candidates.py` は `--ledger` 指定がなければ `D:/develop/works/bench-ledger-engine/bench_ledger.db` の台帳を読みます。`bench-ledger` MCP サーバーの登録は [docs/configure.md](docs/configure.md#benchmark-ledger) を参照してください。
