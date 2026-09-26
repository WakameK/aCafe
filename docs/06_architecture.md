# 06. アーキテクチャ（Architecture）

本章では、くまの隠れ家のシステム構成、データフロー、AI連携、  
および世界観機能（彩花のアトリエ・AIキャラ・オーナーAI）が  
どのように技術的に支えられるかを定義する。

---

# 6.1 全体構成（Overview Architecture）

本プロジェクトは以下の構成で動作する。

- **フロントエンド**：Next.js  
- **バックエンド**：Django REST + Django Channels  
- **リアルタイム通信**：WebSocket（Redis Pub/Sub）  
- **AI生成**：Ollama（ローカルLLM）  
- **データベース**：PostgreSQL  
- **キャッシュ / キュー**：Redis  
- **非同期処理**：Celery（AIキャラ入室・アトリエ加工など）

[Next.js]  ←→  [Django REST API]
↑                 ↓
[WebSocket] ←→ [Django Channels] ←→ [Redis Pub/Sub]

[Django] ←→ [PostgreSQL]

[Django / Celery] ←→ [Ollama LLM]


---

# 6.2 フロントエンド構成（Next.js）

### 役割
- UIレンダリング（喫茶店の世界観）
- チャット画面のリアルタイム更新
- 飲み物カード表示
- 彩花のアトリエ画面の描画
- オーナーAI要約画面の表示

### 主な技術
- Next.js App Router
- WebSocket クライアント
- Zustand（状態管理）
- Tailwind（柔らかいUI表現）
- SSR + CSR のハイブリッド

---

# 6.3 バックエンド構成（Django）

### 役割
- REST API（ルーム管理・ユーザー状態管理）
- WebSocket（チャット・AIキャラ入室）
- AIキャラの人格管理
- 彩花のアトリエの具現化処理
- オーナーAIの要約処理

### 主な技術
- Django REST Framework  
- Django Channels  
- Celery（非同期タスク）  
- Redis（Pub/Sub + キュー）  
- PostgreSQL（永続化）

---

# 6.4 AI連携構成（Ollama）

### 役割
- AIキャラの発言生成  
- 雰囲気要約生成  
- 彩花のアトリエの「悩み具現化」生成  
- オーナーAIの構造化要約生成  

### 特徴
- ローカルLLMのため、危険ワードを遮断しない  
- プロンプトを YAML で管理し、人格調整が容易  
- Celery 経由で非同期呼び出し

---

# 6.5 リアルタイム通信（WebSocket + Redis）

### 役割
- チャットメッセージのリアルタイム配信  
- AIキャラ入室イベントの配信  
- 飲み物カードの配信  
- 彩花のアトリエの加工結果の配信  

### フロー
1. フロントが WebSocket に接続  
2. Django Channels が受信  
3. Redis Pub/Sub にブロードキャスト  
4. 全クライアントへ配信

---

# 6.6 データモデル（Domain Model）

### User
- id  
- display_name  
- state（静かにしたい / 話したい）  

### Room
- id  
- name  
- theme  
- description  
- created_at  

### Message
- id  
- room_id  
- user_id（AIキャラ含む）  
- content  
- type（text / system / drink / atelier）  
- created_at  

### AICharacter
- id  
- name  
- personality_yaml  
- entry_behavior  

### AtelierObject（彩花のアトリエ）
- id  
- room_id  
- user_id  
- raw_emotion  
- object_type（石 / 粘土 / ガラスなど）  
- processed_object  
- process_log  

---

# 6.7 彩花のアトリエの技術構成（世界観 × 技術）

彩花のアトリエは世界観の核であり、  
技術的には以下のフローで動作する。

### フロー（悩み具現化）
1. ユーザーが「アトリエへ送る」と依頼  
2. Django が直近のメッセージを抽出  
3. Celery が非同期で Ollama に「悩みの核」を生成  
4. Ollama がメタファー化されたオブジェクトを返す  
5. Django が AtelierObject として保存  
6. フロントがアトリエ画面で表示

### フロー（彩花の加工）
1. Celery が加工タスクを実行  
2. Ollama が加工ログ（物語的描写）を生成  
3. 加工後オブジェクトを生成  
4. AtelierObject を更新  
5. フロントへ WebSocket で配信

---

# 6.8 AIキャラ入室ロジック

### フロー
1. ユーザーがルームに入室  
2. Celery が「AIキャラ入室タスク」を起動  
3. ランダムな遅延（30〜60秒）  
4. AIキャラを選択（人格・雰囲気に応じて）  
5. 入室メッセージを生成  
6. WebSocket で配信

---

# 6.9 オーナーAI要約ロジック

### フロー
1. ユーザーが「まとめて」と依頼  
2. Django が対象ログを抽出  
3. Celery が要約タスクを起動  
4. Ollama が診療情報提供書風に構造化  
5. フロントへ返却

---

# 6.10 アーキテクチャの設計思想

- **世界観と技術の両立**  
  喫茶店の柔らかい空気を壊さないよう、AIの存在を「常連」として扱う。

- **心理的負荷を下げる構造**  
  入室前に雰囲気要約を返し、AIキャラが自然に入室する。

- **危険ワードを遮断しない**  
  ローカルLLMを採用し、背景を丁寧に扱う。

- **悩みを具現化する技術**  
  彩花のアトリエは「感情のメタファー化」を技術で支える。

- **拡張性の高い構造**  
  AIキャラ追加、飲み物追加、Unity連動が容易。

