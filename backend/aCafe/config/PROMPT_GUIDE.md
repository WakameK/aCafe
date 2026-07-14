# プロンプト管理ガイド

## 📁 ファイル構成

```
config/
├── prompt.json           # Ollama/LLMのプロンプト一元管理
└── README.md            # このファイル
```

## 🎯 prompt.json の構造

```json
{
  "sosuke": {
    "listening_chat": {
      "model": "gemma3:4b",
      "system_prompt": "キャラクター説明と会話ルール",
      "user_format": "ユーザー入力の形式（{message}で置き換え）"
    }
  },
  "ayaka": {
    "image_generation": {
      "system_prompt": "画像生成用のシステムプロンプト",
      "user_format": "ユーザー入力の形式（{messages}で置き換え）"
    }
  }
}
```

## 📝 使用例

### sosuke チャット（傾聴AIの場合）
```python
from config.settings_loader import get_config

model = get_config('sosuke.listening_chat.model')
system_prompt = get_config('sosuke.listening_chat.system_prompt')
user_format = get_config('sosuke.listening_chat.user_format')

# プロンプト組み立て
full_prompt = system_prompt + "\n\n" + user_format.format(message=user_message)

# Ollama に送信
payload = {
    "model": model,
    "prompt": full_prompt,
    "stream": False,
}
```

### ayaka 画像生成（プロンプト生成の場合）
```python
from config.settings_loader import get_config

system_prompt = get_config('ayaka.image_generation.system_prompt')
user_format = get_config('ayaka.image_generation.user_format')

# プロンプト組み立て
full_prompt = system_prompt + "\n\n" + user_format.format(messages=recent_messages)
```

## 🔧 新しいプロンプトを追加する方法

### 例：新しいキャラクター「鈴香」を追加する場合

1. **prompt.json に追加**
```json
{
  "suzuka": {
    "greeting": {
      "model": "llama2",
      "system_prompt": "鈴香のキャラクター説明...",
      "user_format": "ユーザー: {message}\n鈴香として返答:"
    }
  }
}
```

2. **views.py で使用**
```python
from config.settings_loader import get_config

model = get_config('suzuka.greeting.model')
system = get_config('suzuka.greeting.system_prompt')
user_fmt = get_config('suzuka.greeting.user_format')

full_prompt = system + "\n\n" + user_fmt.format(message=msg)
```

## 🎨 ベストプラクティス

✅ **すべきこと**
- `system_prompt`: キャラクターの設定や会話ルール
- `user_format`: ユーザー入力の形式（`{message}` や `{messages}` で置き換え）
- `model`: 使用するOllamaモデル名

❌ **すべきでないこと**
- views.py にプロンプトをハードコード
- 複数のプロンプトで同じルールを重複記述
- 長すぎるプロンプト（必要に応じて別ファイル化を検討）

## 📊 環境別プロンプトの管理

開発環境と本番環境でプロンプトを変えたい場合は `development.json` / `production.json` でオーバーライド可能：

```json
{
  "sosuke": {
    "listening_chat": {
      "model": "gemma3:13b"
    }
  }
}
```

## 🔗 関連ファイル

- [settings_loader.py](settings_loader.py) - 設定読み込みモジュール
- [default.json](default.json) - その他の設定値
- [src/sosuke/views.py](../sosuke/views.py) - 使用例
- [src/ayaka/views.py](../ayaka/views.py) - 使用例
