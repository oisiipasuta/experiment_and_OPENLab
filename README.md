# experiment_and_OPENLab

実験用 Web アプリと、次に作成する高校生向け OPENLab アプリを分けて管理するためのリポジトリです。

## フォルダ構成

```text
experiment_and_OPENLab/
├─ experiment-app/  # 現在の音楽聴取実験用アプリ
└─ openlab-app/     # 次に作成する高校生向け OPENLab アプリ
```

## GitHub に上げないもの

`.gitignore` で以下を除外しています。

- `**/instance/`: SQLite DB、Flask の secret key、管理者パスワードなど
- `.env` / `.env.*`: 環境変数ファイル
- `__pycache__/` / `*.pyc`: Python のキャッシュ
- `.DS_Store`: macOS の自動生成ファイル
- `*.db` / `*.sqlite*`: DB ファイル
- `*.pem` / `*.key` / `credentials.*` / `secrets.*`: 秘密情報になりやすいファイル
- `experiment-app/static/audio/` の音源ファイル: 容量・権利管理の都合で Git 管理外
- `experiment-app/static/video/` とアプリ直下の動画ファイル: 容量の都合で Git 管理外

現在の実験用アプリの実行方法は [experiment-app/README.md](experiment-app/README.md) を参照してください。
