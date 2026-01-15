# Python Process Manager

Dockerコンテナ・Pterodactyl環境向けのPythonスクリプト管理Webアプリケーション。

## 機能

- **プロセス管理**: Pythonスクリプトの起動・停止・再起動・削除
- **リアルタイム監視**: 各プロセスのCPU・メモリ使用率を表示
- **ファイルマネージャー**: scripts/logs/backupsディレクトリ内のファイル閲覧・編集・ダウンロード
- **コンソール**: Webインターフェースからシェルコマンドを直接実行
- **パッケージインストーラー**: pipでPythonパッケージをインストール
- **REST API**: 全機能へのプログラマティックアクセス
- **リソースリミッター**: スクリプト毎のCPU・メモリ制限（Linux専用）

## インストール

```bash
git clone https://github.com/yourusername/python-process-manager.git
cd python-process-manager
pip install -r requirements.txt
```

## 必要なパッケージ

`requirements.txt`:

```
flask
psutil
```

## 使い方

### サーバー起動

```bash
python app.py
```

サーバーは `http://0.0.0.0:8000` で起動します
ポートの変更をしたい場合は、app.pyの631行目を変更してください

### ディレクトリ構成

```
python-process-manager/
├── app.py              # メインアプリケーション
├── scripts/            # 管理対象のPythonスクリプト
├── logs/               # 各スクリプトのログファイル
├── backups/            # スクリプトの自動バックアップ
├── files/              # スクリプト実行時の作業ディレクトリ
├── process_state.json  # プロセス状態の追跡
├── resource_config.json # リソース制限設定
└── templates/
    └── index.html      # Webインターフェース
```

### Webインターフェース

1. **Scriptsタブ**: Pythonスクリプトの管理
   - 新規スクリプトのアップロード
   - スクリプトの起動/停止/再起動
   - ログの表示
   - スクリプトの削除

2. **File Managerタブ**: ファイルの閲覧・編集
   - ディレクトリのナビゲーション
   - ファイル内容の表示・編集
   - ファイルのダウンロード

3. **Consoleタブ**: シェルコマンドの実行
   - コマンドの直接実行
   - 出力の表示

## Dockerデプロイ

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p scripts logs backups

EXPOSE 2092

CMD ["python", "app.py"]
```

### ビルドと実行

```bash
docker build -t python-process-manager .
docker run -d -p 2092:2092 --name ppm python-process-manager
```

### Pterodactyl Egg設定

Pterodactylで使用する場合:
- **起動コマンド**: `python app.py`
- **デフォルトポート**: 2092
- **Dockerイメージ**: python:3.12-slim

## リソース制限（Linux専用）

APIを使用して各スクリプトにメモリ・CPU制限を設定:

```bash
curl -X POST http://localhost:2092/api/config/script.py \
  -H "Content-Type: application/json" \
  -d '{"memory_limit_mb": 256, "cpu_time_limit": 300}'
```

- `memory_limit_mb`: 最大仮想メモリ（MB単位、0 = 無制限）
- `cpu_time_limit`: 最大CPU時間（秒単位、0 = 無制限）

## APIドキュメント

完全なAPIリファレンスは [docs/API.md](docs/API.md) を参照してください。

## ライセンス

MIT License
