#!/usr/bin/env python3
"""
カウンセリング台本 → JSONL 変換 (技法注釈対応)

使い方:
    python convert.py nao.txt                # nao の分だけ作り直して、既存の学習データと合体
    python convert.py scripts/               # ディレクトリ内の *.txt を全部
    python convert.py                        # 入力なし = 保存済みデータから全出力を再生成(techniques.txt を直した後など)
    python convert.py --remove nao           # nao の分を学習データから外す
    python convert.py scripts/ -o out/ --augment 3 --techniques techniques.txt
    python convert.py scripts/ --profile-dropout 0.3   # 3割のサンプルでクライアント情報を伏せる

差分更新:
    ファイル名(拡張子なし)がキー。nao.txt を変換すると out/sources/nao.json が丸ごと上書きされ、
    他のファイル分はそのまま残る。最終的な jsonl は毎回 sources/ 全体から作り直すので重複しない。
    名前差し替え・プロフィールの伏せ方はセッションIDから決まる乱数なので、再生成しても変わらない。

出力 (out/):
    sources/<名前>.json    ファイル単位の保存データ(ここが本体)
    sessions.jsonl         構造化データ(Unity・分析用)
    train.jsonl            学習用: 意図+技法  <function>受け止めを伝える</function><tech>ペーシング</tech>難しいでしょうねー。
    train_tech_only.jsonl  学習用: 技法のみ    (比較用)
    train_notech.jsonl     学習用: タグなし    (比較用)
    report.txt             技法・意図の自動補正ログ / 不明な名前 / 技法・意図・プロフィールの分布

入力書式:
    クライアント                 ← 話者名だけの行の下〜最初のセリフまでがプロフィール
    20代の男性
    主訴: バイトでのミスをきっかけに自己否定が強まる
    注意障害

    カウンセラー                 ← カウンセラー側も同様(流派・口調などのペルソナ)
    来談者中心寄り、穏やかでゆっくり話す

    カウンセラー【ペーシング】「難しいでしょうねー。」
    カウンセラー【繰り返し｜自己評価の言語化】「ミスすると、自分のことを欠陥品だと思ってしまう。」
    カウンセラー【｜考える余地を残す】「どうでしょう。」          ← 意図だけでも可
    カウンセラー【沈黙】(3秒考える)
    カウンセラー「そこには、【開かれた質問】どんな違いがあるのでしょう。」   ← 「」の中の【】は文字扱い。外に書く
  - 【】は行の「」の外ならどこでも可。複数は 【繰り返し/開かれた質問】 (/ ・ 、 , + 区切り)
  - 技法名はうろ覚えでOK。techniques.txt の正式名に自動補正(結果は report に出る)
  - ｜(または |)の右側が意図(なぜその技法を使うか)。functions.txt の正式名に自動補正、
    リストに無ければ書いたまま使う(report に一覧が出るので、揺れていたら別名に足す)
  - 話者: カウンセラー/カ/Co, クライアント/ク/Cl   () と （） は混在OK
  - 1ファイル複数セッションは === 行で区切る
  - 任意ヘッダ: #counselor: xx  #client: oo  #theme: ...  (「クライアント⇒カウンセラー名はxx」形式も可)
"""
import argparse
import difflib
import json
import random
import re
import sys
import unicodedata
from datetime import datetime
from collections import Counter, defaultdict
from pathlib import Path

# ================================================================ 設定
SPEAKERS = {
    "カウンセラー": "counselor", "カ": "counselor", "co": "counselor",
    "クライアント": "client", "ク": "client", "cl": "client",
}
JA_ROLE = {"カウンセラー": "counselor", "クライアント": "client"}
CHAT_ROLE = {"counselor": "assistant", "client": "user"}

SYSTEM_BASE = (
    "あなたは傾聴を重視するカウンセラーです。相手の言葉を急いで解決せず、"
    "問い返しや沈黙を使って相手自身の気づきを促してください。"
    "動作は<act>…</act>、間は<pause s=\"秒\"/>で表現します。"
)
SYSTEM_TECH = SYSTEM_BASE + "発話や動作の直前に、使う技法を<tech>技法名</tech>で示してください。"
SYSTEM_FULL = (SYSTEM_BASE + "発話や動作の直前に、その応答の意図を<function>意図</function>、"
               "使う技法を<tech>技法名</tech>の順で示してください。")
SESSION_START = "<session_start/>"

NAME_POOL = {
    "counselor": ["佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村"],
    "client": ["小林", "加藤", "吉田", "山田", "佐々木", "松本", "井上", "木村"],
}

# ================================================================ 正規表現
SEP_RE = re.compile(r"^\s*={3,}\s*$")
META_RE = re.compile(r"^\s*#\s*(\w+)\s*[:：]\s*(.+?)\s*$")
NAME_RE = re.compile(r"^\s*(クライアント|カウンセラー)\s*[⇒→>]\s*(クライアント|カウンセラー)名は\s*(\S+)")
SPEAKER_RE = re.compile(r"^\s*(カウンセラー|クライアント|Co|Cl|co|cl|カ|ク)\s*(?=[(「【])")
SEC_RE = re.compile(r"(\d+(?:\.\d+)?)\s*秒")
SEC_STRIP_RE = re.compile(r"\d+(?:\.\d+)?\s*秒(?:ほど|くらい|ぐらい|程度|間|弱|未満|満たない)?(?:の)?")
UNDER_RE = re.compile(r"満たない|未満|弱")
TECH_SPLIT_RE = re.compile(r"[/／・、,，+＋&]")

BRACKETS = {"(": ")", "「": "」", "【": "】"}
NORMALIZE = str.maketrans({"（": "(", "）": ")"})
STRIP = " 　\t"


class ParseError(Exception):
    pass


# ================================================================ 技法辞書
def tech_key(s):
    """表記揺れ吸収用のキー: NFKC → ひらがな→カタカナ → 記号/長音/空白除去 → 末尾の「技法」等を除去"""
    s = unicodedata.normalize("NFKC", s).lower()
    s = "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in s)
    s = re.sub(r"[\sー\-・･/／_.,、。「」『』()]", "", s)
    s = re.sub(r"(ノ)?(技法|技術|テクニック|法)$", "", s)
    return s


class TechniqueDB:
    def __init__(self, path=None, cutoff=0.72):
        self.cutoff = cutoff
        self.canon = []                 # 正式名(定義順)
        self.category = {}              # 正式名 → カテゴリ
        self.desc = {}
        self.key2canon = {}
        if path:
            self._load(Path(path))

    def _load(self, path):
        cat = "未分類"
        for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.strip()
            if not line:
                continue
            if line.startswith("##"):
                cat = line.lstrip("#").strip()
                continue
            if line.startswith("#"):
                continue
            body, _, desc = line.partition("|")
            name, _, aliases = body.partition(":")
            if not _:
                name, _, aliases = body.partition("：")
            name = name.strip()
            if not name:
                continue
            self.canon.append(name)
            self.category[name] = cat
            self.desc[name] = desc.strip()
            for a in [name] + [x.strip() for x in re.split(r"[,，、]", aliases) if x.strip()]:
                k = tech_key(a)
                if k in self.key2canon and self.key2canon[k] != name:
                    print(f"WARN {path}:{n}: 別名 {a!r} が {self.key2canon[k]!r} と重複", file=sys.stderr)
                    continue
                self.key2canon[k] = name

    @property
    def enabled(self):
        return bool(self.canon)

    def resolve(self, raw):
        """→ (正式名 or None, 方法, 候補リスト)"""
        if not self.enabled:
            return raw, "raw", []
        k = tech_key(raw)
        if not k:
            return None, "empty", []
        if k in self.key2canon:
            c = self.key2canon[k]
            return c, ("exact" if c == raw else "alias"), []
        keys = list(self.key2canon)
        m = difflib.get_close_matches(k, keys, n=1, cutoff=self.cutoff)
        if m:
            return self.key2canon[m[0]], "fuzzy", []
        # 部分一致(「繰り返しの質問」→ 繰り返し 等)。長い別名を優先
        # 候補が1つの正式名に絞れる時だけ採用(「反映」→ 感情の反映 等)。割れたら不明扱い
        hits = [kk for kk in keys if len(kk) >= 2 and len(k) >= 2 and (kk in k or k in kk)]
        cands = list(dict.fromkeys(self.key2canon[h] for h in sorted(hits, key=len, reverse=True)))
        if len(cands) == 1:
            return cands[0], "partial", []
        sugg = cands or [self.key2canon[s] for s in difflib.get_close_matches(k, keys, n=3, cutoff=0.4)]
        return None, "unknown", list(dict.fromkeys(sugg))[:3]


# ================================================================ パーサ
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
            elif ch == "【" and not in_speech:
                flush()
                left, _, func = inner.replace("｜", "|").partition("|")
                seg = {"type": "tech", "raw": [t.strip(STRIP) for t in TECH_SPLIT_RE.split(left) if t.strip(STRIP)]}
                if func.strip(STRIP):
                    seg["func_raw"] = func.strip(STRIP)
                segs.append(seg)
            elif ch == "「" and not in_speech:
                flush()
                segs.extend(scan(inner, where, warn, in_speech=True))
            else:  # 発話中の「」【】はそのまま文字として残す
                buf.append(text[i:j + 1])
            i = j + 1
            continue
        buf.append(ch)
        i += 1
    flush()
    return segs


def parse_session(lines, source, idx, warn):
    meta, names, turns = {}, {}, []
    profile = {"counselor": [], "client": []}
    profile_role = None  # 話者名だけの行の直後はプロフィール読み取り中
    for lineno, raw in lines:
        line = raw.translate(NORMALIZE).rstrip()
        if not line.strip(STRIP):
            continue
        where = f"{source}:{lineno}"

        if m := META_RE.match(line):
            k, v = m.group(1).lower(), m.group(2)
            (names if k in ("counselor", "client") else meta)[k] = v
            continue
        if m := NAME_RE.match(line):
            names[JA_ROLE[m.group(2)]] = m.group(3)
            continue
        if line.strip(STRIP) in JA_ROLE:
            profile_role = JA_ROLE[line.strip(STRIP)]
            continue
        m = SPEAKER_RE.match(line)
        if not m:
            if profile_role:
                item = re.sub(r"^[-・*●]\s*", "", line.strip(STRIP))
                profile[profile_role].append(item)
            else:
                warn(f"{where}: 解釈できない行をスキップ: {line!r}")
            continue
        profile_role = None

        speaker = SPEAKERS[m.group(1).lower()]
        segs = scan(line[m.end():], where, warn)

        for sg in segs:
            if sg["type"] == "tech":
                sg["src"] = f"{Path(source).name}:{lineno}"
        if not [s for s in segs if s["type"] != "tech"] and not segs:
            continue
        if turns and turns[-1]["speaker"] == speaker:
            turns[-1]["segments"].extend(segs)
        else:
            turns.append({"speaker": speaker, "segments": segs})

    repl = sorted(((v, k) for k, v in names.items()), key=lambda x: -len(x[0]))
    def ph(t):
        for name, role in repl:
            t = t.replace(name, "{" + role + "}")
        return t
    for t in turns:
        for s in t["segments"]:
            if "text" in s:
                s["text"] = ph(s["text"])
    profile = {r: [ph(x) for x in v] for r, v in profile.items() if v}

    return {"id": f"{Path(source).stem}_{idx:03d}", "source": str(source),
            "meta": meta, "names": names, "profile": profile, "turns": turns}


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


def resolve_techniques(sessions, techdb, funcdb):
    """保存データの raw から毎回解決し直す(techniques.txt / functions.txt の更新が過去分にも効く)"""
    techlog, funclog = [], []
    for s in sessions:
        for t in s["turns"]:
            for sg in t["segments"]:
                if sg["type"] != "tech":
                    continue
                resolved, unknown = [], []
                for r in sg["raw"]:
                    c, how, sugg = techdb.resolve(r)
                    techlog.append({"raw": r, "canon": c, "how": how, "sugg": sugg,
                                    "where": sg.get("src", s["id"]), "speaker": t["speaker"]})
                    if c and c not in resolved:
                        resolved.append(c)
                    elif not c:
                        unknown.append(r)
                sg["names"] = resolved
                sg.pop("unknown", None)
                if unknown:
                    sg["unknown"] = unknown
                sg.pop("function", None)
                if sg.get("func_raw"):
                    r = sg["func_raw"]
                    c, how, sugg = funcdb.resolve(r)
                    funclog.append({"raw": r, "canon": c, "how": how, "sugg": sugg,
                                    "where": sg.get("src", s["id"]), "speaker": t["speaker"],
                                    "techs": resolved})
                    sg["function"] = c or r  # 意図は自由記述も許す(リスト外は書いたまま)
    return techlog, funclog


# ================================================================ 保存データ (sources/)
def atomic_write(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def save_source(store, key, path, sessions):
    data = {"key": key, "source": str(path), "updated": datetime.now().isoformat(timespec="seconds"),
            "sessions": sessions}
    atomic_write(store / f"{key}.json", json.dumps(data, ensure_ascii=False, indent=1))


def load_sources(store):
    out = []
    for f in sorted(store.glob("*.json")):
        out.extend(json.loads(f.read_text(encoding="utf-8"))["sessions"])
    return out


def migrate_legacy(out, store):
    """sources/ が無い頃の sessions.jsonl があれば取り込む"""
    legacy = out / "sessions.jsonl"
    if any(store.glob("*.json")) or not legacy.exists():
        return
    groups = defaultdict(list)
    for line in legacy.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            groups[Path(rec.get("source", rec["id"])).stem].append(rec)
    for key, ss in groups.items():
        save_source(store, key, ss[0].get("source", key), ss)
    print(f"既存の sessions.jsonl から {len(groups)} ファイル分を sources/ に取り込みました", file=sys.stderr)


# ================================================================ 出力
def fmt(x):
    return str(int(x)) if float(x).is_integer() else str(x)


def render(segs, names, with_tech, with_func=False):
    out = []
    for s in segs:
        t = s["type"]
        if t == "speech":
            out.append(s["text"])
        elif t == "pause":
            out.append(f'<pause s="{fmt(s["sec"])}"/>')
        elif t == "action":
            attr = f' s="{fmt(s["sec"])}"' if "sec" in s else ""
            out.append(f"<act{attr}>{s['text']}</act>")
        elif t == "tech":
            if with_func and s.get("function"):
                out.append(f"<function>{s['function']}</function>")
            if with_tech and s.get("names"):
                out.append(f"<tech>{'/'.join(s['names'])}</tech>")
    text = "".join(out)
    for role, name in names.items():
        text = text.replace("{" + role + "}", name)
    return text


def fill(text, names):
    for role, name in names.items():
        text = text.replace("{" + role + "}", name)
    return text


def build_system(base, session, names, use_client_profile):
    parts = [base]
    prof = session.get("profile", {})
    # カウンセラー設定はモデル自身の人格なので常に入れる。クライアント情報だけドロップアウト対象
    if prof.get("counselor"):
        parts.append("【カウンセラー設定】\n" + "\n".join(f"- {fill(x, names)}" for x in prof["counselor"]))
    if use_client_profile and prof.get("client"):
        parts.append("【クライアント情報(インテーク)】\n" + "\n".join(f"- {fill(x, names)}" for x in prof["client"]))
    return "\n\n".join(parts)


def to_train(session, names, with_tech, system_prompt, with_func=False):
    turns = list(session["turns"])
    while turns and turns[-1]["speaker"] == "client":
        turns.pop()
    if not turns:
        return None
    msgs = [{"role": "system", "content": system_prompt}]
    if turns[0]["speaker"] == "counselor":
        msgs.append({"role": "user", "content": SESSION_START})
    for t in turns:
        # 技法タグはカウンセラー側だけに出す(クライアント側の【】は sessions.jsonl にのみ残る)
        co = t["speaker"] == "counselor"
        content = render(t["segments"], names, with_tech and co, with_func and co)
        if not content:
            content = "<pause/>" if t["speaker"] == "counselor" else "……"
        msgs.append({"role": CHAT_ROLE[t["speaker"]], "content": content})
    return {"id": session["id"], "messages": msgs}


def name_section(L, title, log, db, unknown_note):
    fixed = Counter((e["raw"], e["canon"], e["how"]) for e in log if e["how"] in ("fuzzy", "partial", "alias"))
    unknown = defaultdict(list)
    for e in log:
        if e["canon"] is None:
            unknown[e["raw"]].append(e)
    L.append(f"■ {title}: 自動補正 (fuzzy/partial は誤補正の可能性あり。正しければ別名に足すと確実)")
    for (raw, canon, how), n in sorted(fixed.items(), key=lambda x: (x[0][2] == "alias", -x[1])):
        L.append(f"  [{how:7}] {raw} → {canon}  ×{n}")
    if not fixed:
        L.append("  なし")
    L.append(f"\n■ {title}: リストに無い名前 ({unknown_note})")
    for raw, es in sorted(unknown.items(), key=lambda x: -len(x[1])):
        sugg = es[0]["sugg"]
        hint = f"  候補: {', '.join(sugg)}" if sugg else ""
        L.append(f"  {raw} ×{len(es)}  ({es[0]['where']}){hint}")
    if not unknown:
        L.append("  なし")
    return len(fixed), len(unknown)


def usage_section(L, title, counter, db):
    L.append(f"\n■ {title}: 使用回数 (カウンセラー側)")
    total = sum(counter.values()) or 1
    names = list(db.canon) + [c for c in counter if c not in db.category]
    cat = None
    for c in names:
        cc = db.category.get(c, "リスト外")
        if cc != cat:
            cat = cc
            L.append(f"  -- {cat}")
        n = counter.get(c, 0)
        bar = "#" * round(40 * n / total)
        L.append(f"  {c:　<16}{n:4}  {bar}" + ("   ← 未使用" if n == 0 else ""))


def write_report(path, techdb, techlog, sessions, funcdb, funclog):
    L = []
    n_fixed, n_unknown = name_section(L, "技法", techlog, techdb, "学習データからは除外")
    co = [e for e in techlog if e["canon"] and e["speaker"] == "counselor"]
    usage_section(L, "技法", Counter(e["canon"] for e in co), techdb)

    L.append("")
    name_section(L, "意図", funclog, funcdb, "書いたまま使う。揺れていたら functions.txt の別名に足す")
    fco = [e for e in funclog if e["speaker"] == "counselor"]
    usage_section(L, "意図", Counter(e["canon"] or e["raw"] for e in fco), funcdb)

    L.append("\n■ 意図 × 技法 (どの意図をどの技法で実現しているか)")
    pair = defaultdict(Counter)
    for e in fco:
        for t in e["techs"] or ["(技法なし)"]:
            pair[e["canon"] or e["raw"]][t] += 1
    for f, cnt in sorted(pair.items(), key=lambda x: -sum(x[1].values())):
        L.append(f"  {f}: " + ", ".join(f"{t}×{n}" for t, n in cnt.most_common()))
    if not pair:
        L.append("  なし")
    n_tagged = sum(1 for e in techlog if e["speaker"] == "counselor")
    L.append(f"  (技法タグのうち意図つき: {len(fco)}/{n_tagged})")
    L.append("\n■ クライアントプロフィールの分布 (セッション数)")
    pc = Counter(x for s in sessions for x in s.get("profile", {}).get("client", []))
    no_prof = sum(1 for s in sessions if not s.get("profile", {}).get("client"))
    for x, n in pc.most_common():
        L.append(f"  {n:4}  {x}")
    L.append(f"  {no_prof:4}  (プロフィールなし)")
    L.append("  ※ 件数が少ない属性は言い回しを丸暗記しやすい。同じ属性で展開違いの台本を足すと偏りが減る")

    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return n_fixed, n_unknown


# ================================================================ main
def main():
    ap = argparse.ArgumentParser(description="カウンセリング台本 → JSONL")
    ap.add_argument("inputs", nargs="*", help="txtファイル or ディレクトリ (省略すると保存データから再生成のみ)")
    ap.add_argument("--remove", nargs="+", default=[], metavar="NAME", help="学習データから外すファイル名(拡張子なし)")
    ap.add_argument("-o", "--out", default="out")
    ap.add_argument("--techniques", default=str(Path(__file__).with_name("techniques.txt")),
                    help="技法リスト (無ければ正規化なしで素の名前を使う)")
    ap.add_argument("--functions", default=str(Path(__file__).with_name("functions.txt")),
                    help="意図リスト (無ければ書いたまま使う)")
    ap.add_argument("--cutoff", type=float, default=0.72, help="技法名のあいまい一致のしきい値 (0〜1, 上げるほど厳しい)")
    ap.add_argument("--augment", type=int, default=0, help="名前ランダム差し替えの複製数")
    ap.add_argument("--system", default=None, help="システムプロンプトを書いたファイル(技法タグありの版に使う)")
    ap.add_argument("--profile-dropout", type=float, default=0.3,
                    help="クライアント情報を伏せるサンプルの割合 (0〜1)。情報なしでも応答できるようにする")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--strict", action="store_true", help="警告のあるファイルは保存しない / 不明な技法があれば出力しない")
    args = ap.parse_args()

    tpath = Path(args.techniques)
    techdb = TechniqueDB(tpath if tpath.exists() else None, args.cutoff)
    if not techdb.enabled:
        print(f"WARN 技法リスト {tpath} が無いので技法名は正規化しません", file=sys.stderr)
    sys_full = Path(args.system).read_text(encoding="utf-8").strip() if args.system else SYSTEM_FULL
    fpath = Path(args.functions)
    funcdb = TechniqueDB(fpath if fpath.exists() else None, args.cutoff)

    out = Path(args.out)
    store = out / "sources"
    store.mkdir(parents=True, exist_ok=True)
    migrate_legacy(out, store)

    # --- 削除
    for key in args.remove:
        f = store / f"{key}.json"
        if f.exists():
            f.unlink()
            print(f"削除: {key}")
        else:
            print(f"WARN 削除対象 {key} は保存データにありません", file=sys.stderr)

    # --- 入力ファイルを変換してファイル単位で上書き保存
    files = []
    for p in map(Path, args.inputs):
        files += sorted(p.rglob("*.txt")) if p.is_dir() else [p]
    files = [f for f in files if f.resolve() not in (tpath.resolve(), fpath.resolve())]

    seen, warnings = {}, []
    for f in files:
        key = f.stem
        if key in seen:
            print(f"WARN 同じ名前のファイルが複数: {seen[key]} と {f} → 後者をスキップ", file=sys.stderr)
            continue
        seen[key] = f
        fw = []
        def warn(msg):
            fw.append(msg)
            print("WARN", msg, file=sys.stderr)
        sessions = []
        for i, chunk in enumerate(split_sessions(f)):
            try:
                s = parse_session(chunk, f, i, warn)
            except ParseError as e:
                warn(str(e))
                continue
            if s["turns"]:
                sessions.append(s)
        warnings += fw
        if args.strict and fw:
            print(f"スキップ: {key} (警告{len(fw)}件, --strict)", file=sys.stderr)
            continue
        if not sessions:
            print(f"WARN {f}: セッションが1つも読めなかったので保存データは変更しません", file=sys.stderr)
            continue
        existed = (store / f"{key}.json").exists()
        save_source(store, key, f, sessions)
        print(f"{'上書き' if existed else '追加'}: {key}  ({len(sessions)}セッション)")

    # --- 全保存データから出力を作り直す
    sessions = load_sources(store)
    techlog, funclog = resolve_techniques(sessions, techdb, funcdb)
    n_fixed, n_unknown = write_report(out / "report.txt", techdb, techlog, sessions, funcdb, funclog)
    if args.strict and n_unknown:
        sys.exit(f"不明な技法{n_unknown}種のため出力を中断(--strict)。report.txt を確認して")

    n = 0
    lines = {"sessions": [], "train": [], "tech": [], "notech": []}
    for s in sessions:
        lines["sessions"].append(json.dumps(s, ensure_ascii=False))
        rng = random.Random(f"{args.seed}:{s['id']}")  # セッションごとに固定の乱数 → 再生成しても同じ結果
        variants = [s["names"]] + [
            {r: rng.choice(NAME_POOL[r]) for r in ("counselor", "client")} for _ in range(args.augment)
        ]
        for k, names in enumerate(variants):
            use_prof = rng.random() >= args.profile_dropout
            for key, wt, wf, base in (("train", True, True, sys_full), ("tech", True, False, SYSTEM_TECH),
                                      ("notech", False, False, SYSTEM_BASE)):
                rec = to_train(s, names, wt, build_system(base, s, names, use_prof), wf)
                if rec:
                    if k:
                        rec["id"] += f"_aug{k}"
                    lines[key].append(json.dumps(rec, ensure_ascii=False))
            n += 1
    for key, fname in (("sessions", "sessions.jsonl"), ("train", "train.jsonl"),
                       ("tech", "train_tech_only.jsonl"), ("notech", "train_notech.jsonl")):
        atomic_write(out / fname, "".join(l + "\n" for l in lines[key]))

    n_src = len(list(store.glob("*.json")))
    print(f"合計 ファイル: {n_src}  セッション: {len(sessions)}  サンプル: {n}  警告: {len(warnings)}  "
          f"技法 自動補正: {n_fixed}種 / 不明: {n_unknown}種  → {out}/ (report.txt を確認)")


if __name__ == "__main__":
    main()
