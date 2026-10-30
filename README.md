# PBL-Team6

空き時間（分）を入力し、既存のSQLite DBから時間内に収まるタスクの組み合わせを提案します。
Python 3.10以上で動作し、外部パッケージのインストールは不要です。

## 起動

PowerShellで、このリポジトリのルートフォルダから実行します。

```powershell
python backend/app.py
```

ブラウザで http://127.0.0.1:8000 を開き、空き時間を入力して「タスクを提案する」を押してください。
終了は起動したターミナルで `Ctrl+C`。ポートが使用中なら `--port 8001` を指定できます。

起動時に `database/PBL.db` の既存スキーマを利用し、デモユーザー `demo@pbl.local` と
学習・生活・健康・計画／趣味の4カテゴリ、36タスクを投入します。
ジムに行く（30分）、夕食を作る（45分）、レポートを書く（60分）、
開発プロジェクトを進める（90分）など、まとまった時間を使うタスクも含みます。
再起動しても同じサンプルは重複登録されず、既存の登録内容や履歴を上書きしません。
ログイン機能はなく、操作対象はこのデモユーザーに固定しています。サーバーはローカルの127.0.0.1で待ち受けます。

実行時のDBファイルとログはGit管理の対象外です。初回起動時に `database/PBL_schema.sql` から
DBを作成し、同じサンプルデータを投入するため、クローン直後から試せます。

## 提案の仮ルール

- 入力は1〜1,440の整数（分）。
- デモユーザーの `is_active = 1` の登録タスクだけを対象にします。
- 所要時間は `estimated_minutes` があれば使い、未設定なら `default_minutes` を使います。
- 各タスクの点数は `user_priority × feedback_weight`。点数0のタスクは候補から除きます。
- 合計所要時間が入力時間以下になる組み合わせのうち、合計点数を最大にします（0/1ナップサック）。
- 同点なら合計所要時間が長い組み合わせ、その次にタスク数が少ない組み合わせを優先します。
- タスクは1回の提案で1度ずつ使います。短いタスクが複数選ばれやすい方式です。
- 別の提案では同じタスクも再び候補になります。実行済み管理・係数の自動更新は未実装です。

候補がある場合、`suggestions` に1行、`suggestion_items` に選択数分を同一トランザクションで保存します。
候補がない場合はメッセージを返し、空の履歴は作りません。提案の状態は `pending` です。
空き時間はレスポンスに返すだけで、既存の設計どおりDBには保存しません。
履歴は現在のタスクを参照するため、タスク名や所要時間を変更すると過去履歴の表示にも反映されます。

## CLI / API

ブラウザを使わずに試す場合（こちらもDBに提案履歴を保存します）：

```powershell
python backend/app.py --minutes 20
```

| メソッド | パス | 内容 |
|---|---|---|
| GET | `/api/health` | DB接続確認 |
| GET | `/api/tasks` | 有効な登録タスク |
| GET | `/api/history` | 直近10件の提案履歴（画面には6件表示） |
| POST | `/api/suggestions` | `{"available_minutes": 20}` で提案・保存 |

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/suggestions -Method Post -ContentType 'application/json' -Body '{"available_minutes":20}'
```

## 検証

```powershell
python -m unittest discover -s backend/tests -v
```

テストは一時DBを利用します。サンプル投入、時間制約、個人所要時間、ユーザー分離、
無効タスク、提案履歴、トランザクションのロールバック、入力エラー、HTTP APIを確認します。

## ファイル

- `backend/app.py`: HTTPサーバーとCLI
- `backend/database.py`: 外部キーを有効化したDB接続とサンプル投入
- `backend/suggestions.py`: タスク選択と提案履歴
- `backend/static/index.html`: 日本語の操作画面
- `database/PBL_schema.sql`: 既存スキーマ（変更なし）

認証・完了記録・フィードバック入力はこの動作確認デモの対象外です。
