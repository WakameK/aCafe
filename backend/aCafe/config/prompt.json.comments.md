# prompt.json 設定キー説明

## 📋 プロンプト管理について

`prompt.json` は Ollama / LLMに送信するプロンプトを一元管理するファイルです。
プロンプトをコード内に埋め込まずに、設定ファイルで管理することで：
- ✨ プロンプト修正が容易
- 🔄 プロンプトの再利用が簡単
- 📝 プロンプト履歴の管理が可能
- 🌍 環境ごとに異なるプロンプトを使用可能

---

## 🎭 sosuke (茅根聡介)

聡介は「喫茶くまの隠れ家」の店主で、元カウンセラー。
ユーザーの話を傾聴するAIキャラクター。

### sosuke.listening_chat
傾聴チャット用のプロンプト設定

#### sosuke.listening_chat.model
- **タイプ**: `string`
- **値**: `"gemma3:4b"`
- **説明**: Ollama で使用するモデル名
- **使用箇所**: `sosuke/views.py` の `chat_api()` 関数
- **オプション**: 
  - `"gemma3:4b"` (軽量・高速)
  - `"gemma3:13b"` (精度重視)
  - `"llama2"` (汎用)
- **環境別推奨値**:
  - 開発環境: `"gemma3:4b"` (高速)
  - 本番環境: `"gemma3:13b"` (精度重視)

#### sosuke.listening_chat.system_prompt
- **タイプ**: `string` (複数行テキスト)
- **説明**: Ollamaに与えるシステムプロンプト（キャラクター設定）
- **使用箇所**: `sosuke/views.py` の `chat_api()` 関数
- **内容の要素**:
  - **キャラクター紹介**: 誰かを説明
  - **役割**: どのような立場で会話するか
  - **会話方針**: どのようなトーンで返答するか
  - **禁止事項**: 絶対にやってはいけないこと
  - **口調の例**: 具体的な話し方の例

**テンプレート例**:
```
あなたは「[キャラクター名]」という[性別]です。
[店舗名]の[役職]で、[性格描写]です。

会話方針（重要）:
- [方針1]
- [方針2]
- [方針3]

口調の例:
- [例1]
- [例2]

禁止事項:
- [禁止事項]
```

**修正時の注意**:
- 改行は `\n` で表現（JSON内での改行は `\n` に自動変換）
- 特殊文字は JSON エスケープ（`"` は `\"`）
- 日本語の扱い: UTF-8で保存

#### sosuke.listening_chat.user_format
- **タイプ**: `string` (テンプレート)
- **値**: `"ユーザー: {message}\n茅根聡介として返答:"`
- **説明**: ユーザー入力の形式テンプレート
- **使用箇所**: `sosuke/views.py` の `chat_api()` 関数
- **プレースホルダー**:
  - `{message}`: ユーザーのメッセージに置き換わる
- **用途**: 
  - LLMにユーザー入力の役割を明確に伝える
  - 返答開始点を明示

---

## 🎨 ayaka (彩花)

彩花は「喫茶くまの隠れ家」の絵描き。
ユーザーとの会話をもとに、画像生成プロンプトを作成するAI。

### ayaka.image_generation
画像生成用プロンプト設定

#### ayaka.image_generation.system_prompt
- **タイプ**: `string` (複数行テキスト)
- **値**: 画像生成用のシステムプロンプト
- **説明**: ユーザーの会話をどのようにプロンプトに変換するか指示
- **使用箇所**: `ayaka/views.py` の `build_prompt_from_messages()` 関数
- **役割**:
  - 与えられた会話内容をどう解釈するか
  - 画像生成用プロンプトの要件
  - スタイルや雰囲気の指定

**テンプレート例**:
```
以下の会話内容を参考にして、
[店舗名]の世界観に合う[コンテンツ]を作成してください。

[具体的な指示]

出力形式: [期待される出力形式]
```

#### ayaka.image_generation.user_format
- **タイプ**: `string` (テンプレート)
- **値**: `"会話内容:\n{messages}\n\n出力は画像生成用の短いプロンプトのみ。"`
- **説明**: 会話内容の形式テンプレート
- **使用箇所**: `ayaka/views.py` の `build_prompt_from_messages()` 関数
- **プレースホルダー**:
  - `{messages}`: 最近のメッセージに置き換わる
- **用途**: LLMに会話内容を構造化した形で提示

---

## 🔄 プロンプト全体の組み立て流れ

### sosuke の場合
```python
system_prompt = get_config('sosuke.listening_chat.system_prompt')
user_format = get_config('sosuke.listening_chat.user_format')

# 最終プロンプト = システムプロンプト + ユーザー形式
full_prompt = system_prompt + "\n\n" + user_format.format(message=msg)

# Ollama に送信
payload = {
    "model": get_config('sosuke.listening_chat.model'),
    "prompt": full_prompt,
    "stream": False,
}
```

### ayaka の場合
```python
system_prompt = get_config('ayaka.image_generation.system_prompt')
user_format = get_config('ayaka.image_generation.user_format')

# 最終プロンプト = システムプロンプト + ユーザー形式
full_prompt = system_prompt + "\n\n" + user_format.format(messages=recent_messages)

# LLMに送信して画像生成用プロンプトを生成
```

---

## 📝 新しいプロンプトを追加する方法

### ステップ1: prompt.json に追加
```json
{
  "new_character": {
    "greeting": {
      "model": "gemma3:4b",
      "system_prompt": "あなたは...",
      "user_format": "ユーザー: {message}\n..として返答:"
    }
  }
}
```

### ステップ2: このファイルに説明を追加
```markdown
### new_character.greeting
説明文...

#### new_character.greeting.model
- **タイプ**: `string`
- **値**: `"gemma3:4b"`
...
```

### ステップ3: views.py で使用
```python
from config.settings_loader import get_config

model = get_config('new_character.greeting.model')
system = get_config('new_character.greeting.system_prompt')
user_fmt = get_config('new_character.greeting.user_format')

full_prompt = system + "\n\n" + user_fmt.format(message=msg)
```

---

## ✅ プロンプト設計のベストプラクティス

### 命名規則
```
[キャラクター名].[機能]
```
例: `sosuke.listening_chat`, `ayaka.image_generation`

### システムプロンプントの要素
✅ **含めるべき**
- キャラクター名と性別
- 役職・立場
- 話すときのトーン
- 具体的な話し方の例
- 禁止事項（やってはいけないこと）

❌ **含めないべき**
- 可変的なユーザー入力（user_formatで処理）
- テストケース（プロンプト内では不要）
- 不必要に長い背景設定

### user_format の要素
- `{message}` または `{messages}` プレースホルダー
- LLMに入力形式を明確に伝える
- 返答開始点を示唆

---

## 🌍 環境別プロンプトのオーバーライド

本番環境で異なるプロンプトを使いたい場合：

### production.json
```json
{
  "sosuke": {
    "listening_chat": {
      "model": "gemma3:13b"
    }
  }
}
```

この場合、`model` のみ `"gemma3:13b"` に変更され、
`system_prompt` と `user_format` は `default.json` の値が使用されます。

---

## 🐛 トラブルシューティング

### プロンプトが反映されない
→ `get_config()` のキーパスが正しいか確認
→ JSON の形式に誤りがないか確認（`python -m json.tool config/prompt.json`）

### 日本語が文字化けする
→ JSON ファイルが UTF-8 で保存されているか確認
→ VSCode右下の「エンコーディング」が UTF-8 になっているか確認

### 改行が反映されない
→ JSONでは改行を `\n` で表現（バックスラッシュ + n）
→ 環境別ファイルで改行を修正する場合も同じ
