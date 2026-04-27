# 設定管理ガイド

## 📁 ディレクトリ構造

```
aCafe/
├── config/
│   ├── __init__.py
│   ├── default.json          # デフォルト設定（全環境の基本値）
│   ├── development.json      # 開発環境のオーバーライド設定
│   ├── production.json       # 本番環境のオーバーライド設定
│   ├── settings_loader.py    # 設定読み込みモジュール
│   └── USAGE_EXAMPLE.py      # 使用例
├── .env                      # 環境変数（.gitignoreに追加）
├── .gitignore               # .envと環境別JSONを除外
└── mysite/
    └── settings.py          # Django設定
```

## 🔧 設定の優先度（高い順）

1. **環境変数** (`DJANGO_ENV=production`)
2. **環境別JSON** (`development.json`, `production.json`)
3. **デフォルトJSON** (`default.json`)

## 📝 使用方法

### 1️⃣ 設定値の取得
```python
from config.settings_loader import get_config

# ドット記法でネストされた値にアクセス
url = get_config('api.pixazo.url')
width = get_config('image.generation.width')
limit = get_config('chat.recent_messages_limit')
```

### 2️⃣ views.pyの書き換え例
```python
# ❌ 変更前（ハードコーディング）
def generate_image(prompt):
    url = "https://api.pixazo.com/v1/image"  # マジックナンバー
    payload = {"model": "sdxl", "width": 1024, "height": 1024}  # ハードコード

# ✅ 変更後（設定ファイル化）
def generate_image(prompt):
    url = get_config('api.pixazo.url')
    payload = {
        "model": get_config('api.pixazo.model'),
        "width": get_config('image.generation.width'),
        "height": get_config('image.generation.height'),
    }
```

## 🔐 セキュリティと環境分離

### .gitignoreに追加
```
# 環境別ファイル
config/production.json
config/staging.json
.env
.env.local

# 本番環境の秘匿情報
*.key
*.pem
```

### 環境変数の使用（オプション）
```bash
# コマンドラインから環境を指定
export DJANGO_ENV=production
python manage.py runserver

# または .envファイルから自動読み込み
# .env の内容：
# DJANGO_ENV=production
```

## 📊 環境別設定の例

### default.json（全環境の基本値）
- API URLのデフォルト値
- 画像生成の基本サイズ
- タイムアウトのデフォルト値

### development.json（開発環境）
- より大きな limit値（デバッグしやすい）
- 短いタイムアウト（エラー検出が早い）

### production.json（本番環境）
- より安全な limit値（負荷軽減）
- 長いタイムアウト（安定性重視）
- キャッシュ設定の有効化など

## 🎯 ベストプラクティス

✅ **すべきこと**
- 環境ごとに異なる値は `development.json`/`production.json` に記載
- URLやタイムアウトは `default.json` に記載
- APIキーなどの秘匿情報は `.env` に記載

❌ **すべきでないこと**
- `production.json` を Git にコミット（本番の秘密情報漏洩リスク）
- `.env` ファイルを Git にコミット
- 複数の場所で同じ値をハードコード

## 🔄 移行ステップ

1. `config/` ディレクトリを作成（✅ 完了）
2. `views.py`の `get_config()` への置き換え
3. `sosuke/views.py`のCookie設定の置き換え
4. `desk/views.py`の日時フォーマットの置き換え
5. テストを実行して確認

## 📌 参考資料

- [Django Settings](https://docs.djangoproject.com/en/6.0/topics/settings/)
- [12 Factor App - Config](https://12factor.net/config)
