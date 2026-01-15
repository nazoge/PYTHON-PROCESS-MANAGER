# Python Process Manager API リファレンス

ベースURL: `http://localhost:2092`

## スクリプト

### 全スクリプト一覧取得

```http
GET /api/scripts
```

**レスポンス:**
```json
{
  "scripts": [
    {
      "name": "example.py",
      "status": "Running",
      "pid": 12345,
      "cpu": 2.5,
      "memory_mb": 45.2
    }
  ]
}
```

### スクリプト起動

```http
POST /api/scripts/{script_name}/start
```

**レスポンス:**
```json
{
  "success": true,
  "pid": 12345
}
```

### スクリプト停止

```http
POST /api/scripts/{script_name}/stop
```

**レスポンス:**
```json
{
  "success": true
}
```

### スクリプト再起動

```http
POST /api/scripts/{script_name}/restart
```

**レスポンス:**
```json
{
  "success": true,
  "pid": 12346
}
```

### スクリプト削除

```http
DELETE /api/scripts/{script_name}/delete
```

**レスポンス:**
```json
{
  "success": true
}
```

### スクリプトログ取得

```http
GET /api/scripts/{script_name}/logs?lines=100
```

**パラメータ:**
| 名前 | 型 | 説明 |
|------|------|-------------|
| lines | integer | 取得する行数（デフォルト: 100） |

**レスポンス:**
```json
{
  "content": "...",
  "lines": 150
}
```

### コマンド送信

実行中のスクリプトに標準入力を送信します。

```http
POST /api/scripts/{script_name}/send
Content-Type: application/json
```

**ボディ:**
```json
{
  "input": "コマンドやテキスト"
}
```

**レスポンス:**
```json
{
  "success": true
}
```

**注意:** スクリプトはサーバー起動後にUI/APIから起動されている必要があります。

### スクリプトアップロード

```http
POST /api/scripts/upload
Content-Type: multipart/form-data
```

**フォームデータ:**
| 名前 | 型 | 説明 |
|------|------|-------------|
| file | file | アップロードするPythonファイル (.py) |

**レスポンス:**
```json
{
  "success": true,
  "filename": "script.py"
}
```

---

## ファイル

### ディレクトリ一覧

```http
GET /api/files?path={directory_path}
```

**パラメータ:**
| 名前 | 型 | 説明 |
|------|------|-------------|
| path | string | ディレクトリパス (scripts, logs, backups) |

**レスポンス:**
```json
{
  "items": [
    {"name": "file.py", "is_dir": false, "size": 1234},
    {"name": "subdir", "is_dir": true, "size": 0}
  ],
  "path": "scripts"
}
```

### ファイル読み込み

```http
GET /api/files/read?path={file_path}
```

**レスポンス:**
```json
{
  "content": "ファイル内容...",
  "path": "scripts/file.py"
}
```

### ファイル書き込み

```http
POST /api/files/write
Content-Type: application/json
```

**ボディ:**
```json
{
  "path": "scripts/file.py",
  "content": "新しいファイル内容"
}
```

**レスポンス:**
```json
{
  "success": true
}
```

### ファイル削除

```http
POST /api/files/delete
Content-Type: application/json
```

**ボディ:**
```json
{
  "path": "scripts/file.py"
}
```

**レスポンス:**
```json
{
  "success": true
}
```

### ファイルダウンロード

```http
GET /api/files/download?path={file_path}
```

ファイルを添付ファイルとして返します。

---

## システム

### システム情報取得

```http
GET /api/system
```

**レスポンス:**
```json
{
  "cpu_percent": 15.2,
  "memory_percent": 45.8,
  "disk_percent": 62.3,
  "platform": "Linux",
  "resource_limits_available": true
}
```

---

## リソース設定

### スクリプトのリソース設定取得

```http
GET /api/config/{script_name}
```

**レスポンス:**
```json
{
  "memory_limit_mb": 256,
  "cpu_time_limit": 300
}
```

### スクリプトのリソース設定変更

```http
POST /api/config/{script_name}
Content-Type: application/json
```

**ボディ:**
```json
{
  "memory_limit_mb": 256,
  "cpu_time_limit": 300
}
```

**パラメータ:**
| 名前 | 型 | 説明 |
|------|------|-------------|
| memory_limit_mb | integer | メモリ制限（MB単位、0 = 無制限） |
| cpu_time_limit | integer | CPU時間制限（秒単位、0 = 無制限） |

**レスポンス:**
```json
{
  "success": true
}
```

**注意:** リソース制限はLinuxシステムでのみ動作します。

---

## エラーレスポンス

全てのエンドポイントでエラーレスポンスが返される可能性があります:

```json
{
  "success": false,
  "error": "エラーの説明"
}
```

または:

```json
{
  "error": "エラーの説明"
}
```

一般的なHTTPステータスコード:
- `400` - 不正なリクエスト（パラメータ不足）
- `403` - アクセス拒否（無効なパス）
- `404` - 見つかりません
- `500` - サーバーエラー
