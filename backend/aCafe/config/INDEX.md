# config/ フォルダ ファイルガイド

## 📂 フォルダ全体の構成

```
config/
├── __init__.py                    # configモジュール説明
├── settings_loader.py             # 設定読み込みロジック
├── README.md                      # 設定管理システム総合ガイド
├── PROMPT_GUIDE.md               # プロンプト管理ガイド
├── USAGE_EXAMPLE.py              # 実装例
├── INDEX.md                      # このファイル（ファイルガイド）
│
├── default.json                  # 全環境共通設定（デフォルト値）
├── development.json              # 開発環境のオーバーライド設定
├── production.json               # 本番環境のオーバーライド設定
│
├── prompt.json                   # Ollama/LLMプロンプト一元管理
│
├── default.json.comments.md      # default.jsonの全キー説明
└── prompt.json.comments.md       # prompt.jsonの全キー説明
```

---

## 📄 各ファイルの役割

### 🔧 実装ファイル

#### `__init__.py`
- **用途**: configモジュールの説明とドキュメンテーション
- **内容**:
  - ファイル構成の概要
  - 基本的な使い方
  - 環境選択方法
  - セキュリティに関する注意
- **読むべき人**: config機能を初めて使う人、プロジェクト新参者

#### `settings_loader.py`
- **用途**: 設定ファイル読み込みの実装
- **主要クラス**: `ConfigLoader`
- **主要関数**: `get_config(key_path, default=None)`
- **機能**:
  - JSONファイルの読み込み
  - 環境別ファイルのマージ
  - ドット記法での値取得
  - デフォルト値の指定
- **インポート**: `from config.settings_loader import get_config`
- **実装の詳細**: このファイルのdocstringと関数コメントを参照

---

### 📊 設定ファイル

#### `default.json` (必須)
- **用途**: 全環境共通のデフォルト設定値
- **内容セクション**:
  - `api`: 外部API設定（Pixazo等）
  - `image`: 画像生成設定（サイズ等）
  - `chat`: チャット関連設定（制限数、フォーマット等）
  - `cookie`: Cookie設定（名前、有効期限等）
  - `pagination`: ページネーション設定
- **修正時**: 環境を問わず統一したい値のみここに記載
- **詳細説明**: [default.json.comments.md](#default.json.comments.md) を参照

#### `development.json` (オプション)
- **用途**: 開発環境専用のオーバーライド設定
- **内容**: `default.json` で定義されたキーの一部をオーバーライド
- **例**:
  ```json
  {
    "chat": { "recent_messages_limit": 50 },
    "api": { "pixazo": { "timeout": 20 } }
  }
  ```
- **使用条件**: `DJANGO_ENV=development` 時に読み込まれる
- **Git**: コミット可（開発環境用なので秘密情報不要）

#### `production.json` (オプション)
- **用途**: 本番環境専用のオーバーライド設定
- **内容**: `default.json` で定義されたキーの一部をオーバーライド
- **例**:
  ```json
  {
    "chat": { "recent_messages_limit": 10 },
    "image": { "generation": { "width": 768, "height": 768 } }
  }
  ```
- **使用条件**: `DJANGO_ENV=production` 時に読み込まれる
- **Git**: ⚠️ `.gitignore` に追加して Git にコミットしないこと
- **理由**: 本番環境の秘密情報や重要な設定が含まれるため

---

### 🎭 プロンプト設定

#### `prompt.json`
- **用途**: Ollama/LLMに送信するプロンプトの一元管理
- **構成セクション**:
  - `sosuke`: 茅根聡介（傾聴AI）関連
    - `listening_chat`: チャット用プロンプト
  - `ayaka`: 彩花（画像生成AI）関連
    - `image_generation`: 画像生成用プロンプト
- **各セクションの要素**:
  - `model`: 使用するOllamaモデル名
  - `system_prompt`: キャラクター設定・会話ルール
  - `user_format`: ユーザー入力の形式テンプレート
- **使用方法**: 
  ```python
  from config.settings_loader import get_config
  model = get_config('sosuke.listening_chat.model')
  ```
- **詳細説明**: [prompt.json.comments.md](#prompt.json.comments.md) を参照

---

### 📖 ガイド・説明ファイル

#### `README.md`
- **用途**: 設定管理システム全体の総合ガイド
- **内容**:
  - ディレクトリ構造
  - 設定の優先度
  - 基本的な使用方法
  - 環境分離の方法
  - ベストプラクティス
  - 参考資料
- **読むべき人**: 設定管理システムを理解したい全員

#### `PROMPT_GUIDE.md`
- **用途**: プロンプト管理の詳細ガイド
- **内容**:
  - prompt.json の構造
  - プロンプトの使用例
  - 新しいプロンプトの追加方法
  - 環境別プロンプト管理
  - ベストプラクティス
- **読むべき人**: プロンプトを追加・修正する人

#### `default.json.comments.md`
- **用途**: `default.json` の全キーについての詳細説明
- **内容**: 各設定値の：
  - タイプ（`string`, `integer` など）
  - 現在の値
  - 説明
  - 使用箇所
  - 推奨値（環境別）
  - 注意事項
- **活用**: 新しい設定値を追加する時、このファイルにも説明を追加

#### `prompt.json.comments.md`
- **用途**: `prompt.json` の全キーについての詳細説明
- **内容**: 各プロンプトの：
  - タイプ（`string`, `array` など）
  - 値
  - 説明
  - 使用箇所
  - テンプレート例
  - 修正時の注意
- **活用**: 新しいプロンプトを追加する時、このファイルにも説明を追加

#### `USAGE_EXAMPLE.py`
- **用途**: 実装例のコード集
- **内容**:
  - `get_config()` の基本的な使用方法
  - views.py での実装例
  - models.py での実装例
  - テスト時の独立設定
- **活用**: 実装時に参考にするコードサンプル

#### `INDEX.md`
- **用途**: このファイル（ファイルガイド）
- **内容**: configフォルダ内の各ファイルの役割と説明

---

## 🔄 ファイル間の依存関係

```
views.py など実装ファイル
    ↓ import
settings_loader.py
    ↓ 読み込み
default.json
    ↓ マージ
[development.json | production.json]

    ↓ 別パス
prompt.json
    ↓
views.py などで使用
```

---

## 💡 よくある使用シーン

### シーン1: 新しい設定値を追加する
1. `default.json` にキーを追加
2. `default.json.comments.md` に説明を追加
3. views.py で `get_config()` で取得
4. 環境別に異なる値が必要なら `development.json`/`production.json` に記載

### シーン2: 新しいキャラクターを追加する
1. `prompt.json` に新セクション追加
2. `prompt.json.comments.md` に説明を追加
3. views.py で設定を読み込んで使用

### シーン3: 環境ごとに値を変える
1. `default.json` にデフォルト値
2. `production.json` に本番環境用の値をオーバーライド
3. コード側は `get_config()` で統一

### シーン4: 新しい開発者をオンボーディング
1. まず `README.md` を読んでもらう
2. 実装例は `USAGE_EXAMPLE.py` で確認
3. 詳細な説明は `default.json.comments.md` や `prompt.json.comments.md` を参照

---

## ✅ チェックリスト

### 新しい設定値を追加する時
- [ ] `default.json` にキーを追加
- [ ] `default.json.comments.md` に説明を追加
- [ ] テストで動作確認
- [ ] views.py で `get_config()` で取得

### 新しいプロンプトを追加する時
- [ ] `prompt.json` に追加
- [ ] `prompt.json.comments.md` に説明を追加
- [ ] views.py で設定を読み込んで使用
- [ ] テストで動作確認

### 本番環境に変更をデプロイする時
- [ ] `production.json` に必要な値が設定されているか確認
- [ ] `.gitignore` に `production.json` が記載されているか確認
- [ ] 秘密情報が Git にコミットされていないか確認
- [ ] 環境変数 `DJANGO_ENV=production` が設定されているか確認

---

## 🔗 関連リンク

- [README.md](README.md) - 総合ガイド
- [PROMPT_GUIDE.md](PROMPT_GUIDE.md) - プロンプト管理ガイド
- [USAGE_EXAMPLE.py](USAGE_EXAMPLE.py) - 実装例
- [default.json.comments.md](default.json.comments.md) - 設定値説明
- [prompt.json.comments.md](prompt.json.comments.md) - プロンプト説明
