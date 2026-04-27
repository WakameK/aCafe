# default.json 設定キー説明

## 📋 各設定値の詳細

### 🌐 api.pixazo
外部API（Pixazo）関連の設定

#### api.pixazo.url
- **タイプ**: `string`
- **値**: `"https://api.pixazo.com/v1/image"`
- **説明**: 画像生成API のエンドポイント
- **使用箇所**: `ayaka/views.py` の `generate_image()` 関数
- **注意**: 本番環境では別のURLに変更する可能性あり

#### api.pixazo.model
- **タイプ**: `string`
- **値**: `"sdxl"`
- **説明**: 使用する画像生成モデルの名前
- **使用箇所**: `ayaka/views.py` の `generate_image()` 関数
- **オプション**: `"sdxl"`, `"sd-turbo"` など

#### api.pixazo.timeout
- **タイプ**: `integer` (秒)
- **値**: `30`
- **説明**: API呼び出しのタイムアウト時間
- **使用箇所**: リクエスト発行時に使用（実装は別途）
- **推奨値**: 
  - 開発環境: `20` (エラーを早く検出)
  - 本番環境: `30` (安定性重視)

---

### 🖼️ image.generation
画像生成関連の設定

#### image.generation.width
- **タイプ**: `integer` (ピクセル)
- **値**: `1024`
- **説明**: 生成される画像の幅
- **使用箇所**: `ayaka/views.py` の `generate_image()` 関数
- **推奨値**: `512`, `768`, `1024`, `1280` など（モデルに依存）

#### image.generation.height
- **タイプ**: `integer` (ピクセル)
- **値**: `1024`
- **説明**: 生成される画像の高さ
- **使用箇所**: `ayaka/views.py` の `generate_image()` 関数
- **注意**: 計算コストに直結するため本番環境では調整が必要

---

### 💬 chat
チャット関連の設定

#### chat.recent_messages_limit
- **タイプ**: `integer`
- **値**: `20`
- **説明**: プロンプト作成時に参照する最近のメッセージ数の上限
- **使用箇所**: `ayaka/views.py` の `get_recent_messages()` 関数
- **推奨値**:
  - 開発環境: `50` (デバッグしやすい)
  - 本番環境: `10` (メモリ・コスト削減)

#### chat.date_format
- **タイプ**: `string` (Python strftime形式)
- **値**: `"%Y-%m-%d %H:%M"`
- **説明**: チャットメッセージの日時表示形式
- **使用箇所**: `desk/views.py` の `get_messages()` 関数
- **参考**: Python datetime のフォーマット仕様に従う
  - `%Y`: 4桁の年
  - `%m`: 2桁の月
  - `%d`: 2桁の日
  - `%H`: 2桁の時間(24時間)
  - `%M`: 2桁の分

---

### 🍪 cookie
Cookie関連の設定

#### cookie.user_id_name
- **タイプ**: `string`
- **値**: `"anon_user_id"`
- **説明**: 匿名ユーザーIDを保存するCookieの名前
- **使用箇所**: `sosuke/views.py` の `index()`, `chat_api()` 関数
- **注意**: ブラウザの Cookie名として有効な文字列である必要あり

#### cookie.max_age_days
- **タイプ**: `integer` (日数)
- **値**: `365`
- **説明**: Cookieの有効期限（日数）
- **使用箇所**: 各ビューの `set_cookie()` 呼び出し時に `秒数` に変換
- **計算式**: `max_age_seconds = max_age_days * 24 * 60 * 60`
- **推奨値**: 
  - テスト環境: `7` (1週間)
  - 本番環境: `365` (1年)

#### cookie.default_user_name
- **タイプ**: `string`
- **値**: `"お客さん"`
- **説明**: 初回アクセス時のデフォルトユーザー名
- **使用箇所**: `sosuke/views.py` の `index()` 関数
- **カスタマイズ**: 店舗名や挨拶に合わせて変更可能

---

### 📊 pagination
ページネーション関連の設定

#### pagination.default_limit
- **タイプ**: `integer`
- **値**: `20`
- **説明**: リスト表示時のデフォルト件数上限
- **使用箇所**: 将来的なリスト表示機能などで使用予定
- **推奨値**: 
  - 開発環境: `50` (全件確認しやすい)
  - 本番環境: `20` (パフォーマンス重視)

---

## 🔄 環境別のオーバーライド例

### development.json での上書き例
```json
{
  "chat": {
    "recent_messages_limit": 50
  },
  "api": {
    "pixazo": {
      "timeout": 20
    }
  }
}
```

### production.json での上書き例
```json
{
  "chat": {
    "recent_messages_limit": 10
  },
  "image": {
    "generation": {
      "width": 768,
      "height": 768
    }
  }
}
```

---

## 📝 新しい設定値を追加する方法

1. **default.json に追加**
   ```json
   {
     "feature": {
       "new_option": "value"
     }
   }
   ```

2. **このファイルに説明を追加**
   ```markdown
   #### feature.new_option
   - **タイプ**: `string`
   - **値**: `"value"`
   - **説明**: 機能説明...
   - **使用箇所**: どのファイルで使用するか
   ```

3. **views.py で使用**
   ```python
   from config.settings_loader import get_config
   
   value = get_config('feature.new_option')
   ```

---

## 🎯 設定値の命名規則

✅ **推奨事項**
- ネストされたキーは3層まで: `category.subcategory.key`
- `_` でスネークケース: `max_age_days`
- 意味のある名前: `timeout` (✅) vs `t` (❌)
- 単位を明示: `max_age_days` (日数), `timeout` (秒)

❌ **避けるべき**
- 数字のみ: `123` 
- 無意味な省略: `prm`, `cfg`
- 階層が深すぎ: `a.b.c.d.e.f`
