"""
aCafe 設定管理モジュール

このモジュールは、プロジェクト全体の設定を一元管理します。
マジックナンバーやハードコーディングを排除し、
環境ごとに異なる値を効率的に管理するための仕組みです。

=================================================================
ファイル構成
=================================================================

📄 __init__.py
  - このモジュールの説明

📄 settings_loader.py
  - JSON設定の読み込みと環境変数対応の実装
  - get_config() 関数でドット記法での値取得が可能

📄 default.json
  - 全環境共通のデフォルト設定値
  - 環境別ファイルでオーバーライド可能

📄 development.json (オプション)
  - 開発環境でのみ使う設定値
  - development.jsonで指定された値が default.json を上書き

📄 production.json (オプション)
  - 本番環境でのみ使う設定値
  - production.jsonで指定された値が default.json を上書き

📄 prompt.json
  - Ollama/LLM用プロンプト一元管理
  - キャラクターごとのシステムプロンプトや会話ルール

📄 default.json.comments.md
  - default.json内の全設定キーについての説明

📄 prompt.json.comments.md
  - prompt.json内の全設定キーについての説明

📄 README.md
  - 設定管理システム全体のガイド

📄 PROMPT_GUIDE.md
  - プロンプト管理の詳細ガイド

📄 USAGE_EXAMPLE.py
  - 実際の使用例

=================================================================
基本的な使い方
=================================================================

1. settings_loader から get_config 関数をインポート:
   from config.settings_loader import get_config

2. ドット記法で値を取得:
   url = get_config('api.pixazo.url')
   width = get_config('image.generation.width')
   model = get_config('sosuke.listening_chat.model')

3. デフォルト値を指定:
   timeout = get_config('api.pixazo.timeout', default=30)

=================================================================
環境の選択
=================================================================

環境は DJANGO_ENV 環境変数で指定:
  export DJANGO_ENV=production    # 本番環境
  export DJANGO_ENV=development   # 開発環境 (デフォルト)

=================================================================
設定ファイルの優先度（高い順）
=================================================================

1. 環境別JSONファイル (production.json / development.json)
2. デフォルトJSONファイル (default.json)
3. コード内のハードコード値

環境別ファイルが存在しない場合は、該当のキーのデフォルト値が使用されます。

=================================================================
セキュリティ
=================================================================

✅ .gitignore に以下を追加してください:
   config/production.json
   config/staging.json
   .env
   .env.local

本番の秘密情報を Git にコミットしないようにしてください。

=================================================================
"""
