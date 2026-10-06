#!/usr/bin/env python3
"""
カウンセリング台本 → JSONL 変換

使い方:
    python convert.py scripts/            # ディレクトリ内の *.txt を全部
    python convert.py session01.txt -o out/
    python convert.py scripts/ --augment 3   # 名前をランダム差し替えした複製を3件ずつ追加

出力:
    out/sessions.jsonl  構造化データ(Unity・分析用。動作/間/発話がセグメント単位)
    out/train.jsonl     学習用 messages 形式(動作と間はタグに直列化)

入力書式(最低限):
    カウンセラー「こんにちは。ooさん。」
    クライアント「そうですね。(3秒の沈黙)　ぼちぼちです。」
    カウンセラー(微笑む)
  - 話者は カウンセラー/カ/Co, クライアント/ク/Cl のどれでもOK
  - () と （） はどちらでもOK
  - 1ファイルに複数セッションを書く場合は === の行で区切る
  - 任意ヘッダ:  #counselor: xx   #client: oo   #theme: 自己否定  など
    (「クライアント⇒カウンセラー名はxx」形式も読む)
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- 設定
SPEAKERS = {
    "カウンセラー": "counselor", "カ": "counselor", "co": "counselor",
    "クライアント": "client", "ク": "client", "cl": "client",
}
JA_ROLE = {"カウンセラー": "counselor", "クライアント": "client"}
CHAT_ROLE = {"counselor": "assistant", "client": "user"}

SYSTEM_PROMPT = (
    "あなたは傾聴を重視するカウンセラーです。相手の言葉を急いで解決せず、"
    "問い返しや沈黙を使って相手自身の気づきを促してください。"
    "動作は<act>…</act>、間は<pause s=\"秒\"/>で表現します。"
)
SESSION_START = "<session_start/>"  # カウンセラーから話し始める場合の起点トークン

NAME_POOL = {
    "counselor": ["佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村"],
    "client": ["小林", "加藤", "吉田", "山田", "佐々木", "松本", "井上", "木村"],
}

# ---------------------------------------------------------------- 正規表現
SEP_RE = re.compile(r"^\s*={3,}\s*$")
META_RE = re.compile(r"^\s*#\s*(\w+)\s*[:：]\s*(.+?)\s*$")
NAME_RE = re.compile(r"^\s*(クライアント|カウンセラー)\s*[⇒→>]\s*(クライアント|カウンセラー)名は\s*(\S+)")
SPEAKER_RE = re.compile(r"^\s*(カウンセラー|クライアント|Co|Cl|co|cl|カ|ク)\s*(?=[(「])")
SEC_RE = re.compile(r"(\d+(?:\.\d+)?)\s*秒")
SEC_STRIP_RE = re.compile(r"\d+(?:\.\d+)?\s*秒(?:ほど|くらい|ぐらい|程度|間|弱|未満|満たない)?(?:の)?")
UNDER_RE = re.compile(r"満たない|未満|弱")

BRACKETS = {"(": ")", "「": "」"}
NORMALIZE = str.maketrans({"（": "(", "）": ")"})
STRIP = " 　\t"


class ParseError(Exception):
    pass


# ---------------------------------------------------------------- パーサ
def find_close(s, i):
    stack = []
    for j in range(i, len(s)):
        c = s[j]
        if c in BRACKETS:
            stack.append(BRACKETS[c])
        elif stack and c == stack[-1]:
            stack.pop()
            if not stack:
                return j
    return -1


def parse_action(inner):
    inner = inner.strip(STRIP)
    dur = None
    m = SEC_RE.search(inner)
    if m:
        dur = float(m.group(1))
        if UNDER_RE.search(inner):
            dur = round(dur * 0.5, 2)
    if "沈黙" in inner or inner in ("間", "…", "……"):
        return {"type": "pause", "sec": dur if dur is not None else 2.0}
    seg = {"type": "action", "text": inner}
    if dur is not None:
        seg["text"] = SEC_STRIP_RE.sub("", inner).strip(STRIP + "、。")
        seg["sec"] = dur
    return seg


def scan(text, where, warn, in_speech=False):
    segs, buf, i = [], [], 0

    def flush():
        t = "".join(buf).strip(STRIP)
        if t:
            if not in_speech:
                warn(f"{where}: 括弧の外に文字列があります → 発話扱い: {t!r}")
            segs.append({"type": "speech", "text": t})
        buf.clear()

    while i < len(text):
        ch = text[i]
        if ch in BRACKETS:
            j = find_close(text, i)
            if j < 0:
                raise ParseError(f"{where}: 閉じ括弧がありません: {text[i:]!r}")
            inner = text[i + 1:j]
            if ch == "(":
                flush()
                segs.append(parse_action(inner))
            elif not in_speech:  # トップレベルの「」= 発話
                flush()
                segs.extend(scan(inner, where, warn, in_speech=True))
            else:  # 発話中の「」は引用としてそのまま残す
                buf.append(text[i:j + 1])
            i = j + 1
            continue
        buf.append(ch)
        i += 1
    flush()
    return segs


def parse_session(lines, source, idx, warn):
    meta, names, turns = {}, {}, []
    for lineno, raw in lines:
        line = raw.translate(NORMALIZE).rstrip()
        if not line.strip(STRIP):
            continue
        where = f"{source}:{lineno}"

        if m := META_RE.match(line):
            k, v = m.group(1).lower(), m.group(2)
            if k in ("counselor", "client"):
                names[k] = v
            else:
                meta[k] = v
            continue
        if m := NAME_RE.match(line):
            names[JA_ROLE[m.group(2)]] = m.group(3)
            continue
        if line.strip(STRIP) in JA_ROLE:  # 「クライアント」だけの行(登場人物宣言)は無視
            continue
        m = SPEAKER_RE.match(line)
        if not m:
            warn(f"{where}: 解釈できない行をスキップ: {line!r}")
            continue

        speaker = SPEAKERS[m.group(1).lower()]
        segs = scan(line[m.end():], where, warn)
        if not segs:
            continue
        if turns and turns[-1]["speaker"] == speaker:  # 同じ話者の連続は1ターンにまとめる
            turns[-1]["segments"].extend(segs)
        else:
            turns.append({"speaker": speaker, "segments": segs})

    # 名前をプレースホルダ化(長い名前から置換)
    repl = sorted(((v, k) for k, v in names.items()), key=lambda x: -len(x[0]))
    def ph(t):
        for name, role in repl:
            t = t.replace(name, "{" + role + "}")
        return t
    for t in turns:
        for s in t["segments"]:
            if "text" in s:
                s["text"] = ph(s["text"])

    return {
        "id": f"{Path(source).stem}_{idx:03d}",
        "source": str(source),
        "meta": meta,
        "names": names,
        "turns": turns,
    }


def split_sessions(path):
    chunks, cur = [], []
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if SEP_RE.match(raw):
            chunks.append(cur)
            cur = []
        else:
            cur.append((n, raw))
    chunks.append(cur)
    return [c for c in chunks if any(r.strip(STRIP) for _, r in c)]


# ---------------------------------------------------------------- 出力
def fmt(x):
    return str(int(x)) if float(x).is_integer() else str(x)


def render(segs, names):
    out = []
    for s in segs:
        if s["type"] == "speech":
            out.append(s["text"])
        elif s["type"] == "pause":
            out.append(f'<pause s="{fmt(s["sec"])}"/>')
        else:
            attr = f' s="{fmt(s["sec"])}"' if "sec" in s else ""
            out.append(f"<act{attr}>{s['text']}</act>")
    text = "".join(out)
    for role, name in names.items():
        text = text.replace("{" + role + "}", name)
    return text


def to_train(session, names, system_prompt):
    turns = list(session["turns"])
    while turns and turns[-1]["speaker"] == "client":  # 末尾がユーザなら学習ターゲットが無いので落とす
        turns.pop()
    if not turns:
        return None
    msgs = [{"role": "system", "content": system_prompt}]
    if turns[0]["speaker"] == "counselor":
        msgs.append({"role": "user", "content": SESSION_START})
    for t in turns:
        msgs.append({"role": CHAT_ROLE[t["speaker"]], "content": render(t["segments"], names)})
    return {"id": session["id"], "messages": msgs}


def main():
    ap = argparse.ArgumentParser(description="カウンセリング台本 → JSONL")
    ap.add_argument("inputs", nargs="+", help="txtファイル or ディレクトリ")
    ap.add_argument("-o", "--out", default="out")
    ap.add_argument("--augment", type=int, default=0, help="名前ランダム差し替えの複製数")
    ap.add_argument("--system", default=None, help="システムプロンプトを書いたファイル")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--strict", action="store_true", help="警告をエラー扱い")
    args = ap.parse_args()

    random.seed(args.seed)
    system_prompt = Path(args.system).read_text(encoding="utf-8").strip() if args.system else SYSTEM_PROMPT

    files = []
    for p in map(Path, args.inputs):
        files += sorted(p.rglob("*.txt")) if p.is_dir() else [p]

    warnings = []
    def warn(msg):
        warnings.append(msg)
        print("WARN", msg, file=sys.stderr)

    sessions = []
    for f in files:
        for i, chunk in enumerate(split_sessions(f)):
            try:
                s = parse_session(chunk, f, i, warn)
            except ParseError as e:
                warn(str(e))
                continue
            if s["turns"]:
                sessions.append(s)

    if args.strict and warnings:
        sys.exit(f"{len(warnings)}件の警告があるため中断(--strict)")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    n_train = 0
    with open(out / "sessions.jsonl", "w", encoding="utf-8") as fs, \
         open(out / "train.jsonl", "w", encoding="utf-8") as ft:
        for s in sessions:
            fs.write(json.dumps(s, ensure_ascii=False) + "\n")
            variants = [s["names"]]
            for _ in range(args.augment):
                variants.append({r: random.choice(NAME_POOL[r]) for r in ("counselor", "client")})
            for k, names in enumerate(variants):
                rec = to_train(s, names, system_prompt)
                if rec:
                    if k:
                        rec["id"] += f"_aug{k}"
                    ft.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    n_train += 1

    print(f"sessions: {len(sessions)}  train samples: {n_train}  warnings: {len(warnings)}  → {out}/")


if __name__ == "__main__":
    main()
