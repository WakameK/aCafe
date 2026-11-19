# desk — 焚火の対話空間

## 考え方
- 辛いときに、焚火にあたりに行く。話した言葉が薪になって、火が続く。話が減ると火が小さくなり、消えたら**焚火ごと(発言も)消える**。「また会えたらいいね」。
- 席数の固定はない。誰でも焚火を作れ(1人3つまで)、持ち主が定員(2〜12人)を決める。
- AIだけの焚火(`ambient`)が2つあり、火は消えない。AIキャラが雑談している。
- ひとりで火にあたっている人のところへ、30〜60秒後にAIキャラが来る(待った時間が長い順)。来るとまずコーヒーを置く。

## モデル(models.py)
| モデル | 役割 |
|---|---|
| Room | 焚火。kind = ambient / user / legacy(旧席の名残。見えず、触れず) |
| Presence | 輪にいる接続。`last_seen` が60秒止まったら、いない扱い |
| Message | 発言(人・AI)。焚火が消えると一緒に消える |
| DrinkGift | 贈り物(薪・コーヒー・お茶・毛布) |

## 火
- `fire_level`(0〜1)は時間で減る(既定 毎分0.02)。発言+0.08、贈り物+0.15、入室+0.05。
- 0.2を下回ると「そろそろ終いにしようか」を一度だけ。0.005以下で焚火ごと削除(保存方針A:すぐ消す)。
- ambient は下限0.5で消えない(発言は最新50件だけ残す)。

## 人数
カウンターではなく Presence から数える(同じ人の複数タブは1人)。ハートビート20秒、TTL60秒。
consumer が例外で落ちても `__call__` の finally で外れ、worker も止まった接続を掃除する。
→「誰もいないのに1人いる」が起きない。

## 見張り(safety.py。ルールベース。完全ではない)
| 種類 | 扱い |
|---|---|
| attack(他者への攻撃語) | 本人にだけ保留。やわらげ案 / こっそり燃やす / 書き直す。元の言葉は保存せず、他の人にも見せない |
| method(方法) | 公開しない。本人にだけ寄り添いと相談窓口 |
| ideation / imminent(死にたい) | 消さずに公開。本人にだけ静かな案内、周りには聴き方の案内(30分に1回)、AIキャラは「聴く」方針で返す。誰もいなければ1人呼ぶ |

死にたい気持ちへの返答は KEEPER_GUIDANCE に従い、「その気持ちは正しい」「仕方ない」とは言わない。
相談窓口の番号は `DESK_CRISIS_LINES` で差し替えられる。**公開前に最新の番号を確認すること。**

## 外向けのひとこと
worker が下書きを作るのは持ち主にだけ(`note.draft`)。持ち主が承認した `public_note` だけが一覧に出る。

## API
- `GET/POST /api/desk/fires/`(一覧は「ひとりで待っている」→2人以上→空→満員の順)
- `PATCH/DELETE /api/desk/fires/<id>/`(持ち主のみ)
- `POST .../join/` → fire, user, ws_path, history, gift_items(満員は409)
- `GET .../messages/?before=|after=&limit=`(輪にいる人のみ)
- `POST .../gifts/`(輪にいる人のみ。連続は429)

## WebSocket `/ws/fires/<id>/?anon_id=...`
close code(自動で再接続しない): 4401 anon_id不正 / 4403 満員 / 4404 無い / 4410 火が消えた。
送信: `chat.message` `{message}` / `chat.resolve_hold` `{hold_id, choice}`
受信: `chat.message` `chat.presence` `chat.gift` `fire.level` `fire.closing` `fire.out` `fire.updated`
`chat.hold` `chat.burned`(本人のみ)/ `chat.care`(本人のみ)/ `chat.guide`(本人以外)/ `note.draft`(持ち主のみ)

## 設定(settings.py に書けば上書き)
`DESK_FIRE_DECAY_PER_MIN` `DESK_FIRE_CLOSING_LEVEL` `DESK_MAX_CAPACITY` `DESK_MAX_FIRES_PER_USER`
`DESK_LONELY_JOIN_SECONDS` `DESK_MAX_JOINS_PER_TICK` `DESK_AMBIENT_CHARACTERS` `DESK_AMBIENT_INTERVAL_SECONDS`
`DESK_MIN_SEND_INTERVAL` `DESK_HEARTBEAT_SECONDS` `DESK_CRISIS_LINES`

## 既知の限界
- 見張りはルールベース。言い換えは通る。
- SQLite を backend と worker が共有する(ロックが出るなら PostgreSQL へ)。
- 旧ルーム(legacy)はDBに残る。不要なら手動で消す。
