"""
一鍵評估：把 eval/cases.jsonl 的每一題丟給客服 Agent，自動評分並產生結果表。

執行方式（在專案資料夾，要先開著 Ollama）：
    .venv\\Scripts\\python.exe eval\\run_eval.py                       # 目前版，跑 1 次
    .venv\\Scripts\\python.exe eval\\run_eval.py --variants all --repeats 3   # 三種設定各跑 3 次（約 2～3 小時）
    .venv\\Scripts\\python.exe eval\\run_eval.py --only S01,M03         # 只跑某幾題（除錯用）
    .venv\\Scripts\\python.exe eval\\run_eval.py --regrade              # 不呼叫模型，只用存好的回答重新評分

產出：
    eval/results/raw/<設定>_seed<N>.jsonl   每一題的完整紀錄（問題、回答、呼叫的工具、工具回傳、秒數、評分）
    eval/results/summary.md                 結果表格（REPORT.md 的數字從這裡來）

重跑時會「接著跑」：已經跑過的題目會跳過。想全部重跑，先刪掉 eval/results/raw/。
"""

import argparse
import json
import math
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR.parent / "src"))   # 讓 import step5_agent、config 找得到
sys.path.insert(0, str(EVAL_DIR))

from grader import grade  # noqa: E402

RAW_DIR = EVAL_DIR / "results" / "raw"
VARIANTS = ["A_early", "B_rules", "C_current"]


def load_cases(only: str | None) -> list[dict]:
    lines = (EVAL_DIR / "cases.jsonl").read_text(encoding="utf-8").splitlines()
    cases = [json.loads(ln) for ln in lines if ln.strip()]
    if only:
        wanted = set(only.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    return cases


def run_case(agent, case: dict, thread_id: str) -> dict:
    """依序送出這一題的每一輪問題，記下回答、工具呼叫、工具回傳和花的時間。"""
    from langchain_core.messages import AIMessage, ToolMessage

    config = {"configurable": {"thread_id": thread_id}}   # 每一題用新的 thread，記憶互不干擾
    turns = []
    for user in case["turns"]:
        before = len(agent.get_state(config).values.get("messages", []))
        start = time.perf_counter()
        result = agent.invoke({"messages": [{"role": "user", "content": user}]}, config)
        seconds = time.perf_counter() - start

        new = result["messages"][before:]   # 只看這一輪新增的訊息
        turns.append({
            "user": user,
            "answer": new[-1].content,
            "tool_calls": [{"name": c["name"], "args": c["args"]}
                           for m in new if isinstance(m, AIMessage) for c in m.tool_calls],
            "tool_outputs": [m.content for m in new if isinstance(m, ToolMessage)],
            "seconds": round(seconds, 2),
        })
    return {"turns": turns}


def run(variants: list[str], repeats: int, cases: list[dict]) -> None:
    from variants import build_agent   # 載入時會建知識庫（約 30 秒），--regrade 不需要

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for variant in variants:
        for seed in range(1, repeats + 1):
            path = RAW_DIR / f"{variant}_seed{seed}.jsonl"
            done = set()
            if path.exists():
                done = {json.loads(ln)["id"] for ln in path.read_text(encoding="utf-8").splitlines() if ln}
            todo = [c for c in cases if c["id"] not in done]
            if not todo:
                continue

            agent = build_agent(variant, seed=seed)
            # 暖機：第一次呼叫要把模型載入記憶體（CPU 約 15～60 秒），不算進回答時間
            agent.invoke({"messages": [{"role": "user", "content": "你好"}]},
                         {"configurable": {"thread_id": "warmup"}})

            for i, case in enumerate(todo, 1):
                # Ollama 偶爾會串流中斷（No data received），整題換一個新的 thread 重跑，最多 3 次
                for attempt in range(1, 4):
                    try:
                        record = run_case(agent, case, thread_id=f"{case['id']}-try{attempt}")
                        break
                    except (ValueError, ConnectionError) as e:
                        print(f"   {case['id']} 第 {attempt} 次失敗：{e}")
                        if attempt == 3:
                            raise
                        time.sleep(10)
                record = {"id": case["id"], "variant": variant, "seed": seed, **record}
                record["grade"] = grade(case, record)
                with path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                g = record["grade"]
                mark = "✔" if g["correct"] else ("✘ 捏造" if g["fabricated"] else "✘")
                secs = sum(t["seconds"] for t in record["turns"])
                print(f"[{variant} seed{seed}] {i}/{len(todo)} {case['id']} {mark} {secs:.0f}s {g['reasons']}")


def load_records(cases: list[dict]) -> list[dict]:
    """讀取所有存好的紀錄，並用「目前的」評分規則重新評分（規則改了，分數就跟著更新）。"""
    by_id = {c["id"]: c for c in cases}
    records = []
    for path in sorted(RAW_DIR.glob("*.jsonl")):
        for ln in path.read_text(encoding="utf-8").splitlines():
            if not ln:
                continue
            r = json.loads(ln)
            if r["id"] in by_id:
                r["grade"] = grade(by_id[r["id"]], r)
                records.append(r)
    return records


def sign_test(up: int, down: int) -> float:
    """雙尾符號檢定：如果其實沒差（變好、變差機率各半），看到這麼不平均的機率。"""
    n, k = up + down, min(up, down)
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def pct(values: list[bool]) -> str:
    return f"{100 * sum(values) / len(values):.1f}%" if values else "—"


def summarize(records: list[dict], cases: list[dict]) -> str:
    """把紀錄整理成 Markdown 表格。"""
    by_variant = defaultdict(list)
    for r in records:
        by_variant[r["variant"]].append(r)
    variants = [v for v in VARIANTS if v in by_variant]
    out = ["# 評估結果（由 eval/run_eval.py 自動產生，請勿手動修改）", ""]

    # ---------- 總表 ----------
    out += ["## 總表", "",
            "| 設定 | 執行次數 | 題數×次數 | 答對率 | 捏造率 | 空白回答率 | 工具正確率 | 每輪平均秒數 | 每題平均秒數 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for v in variants:
        rs = by_variant[v]
        seeds = sorted({r["seed"] for r in rs})
        turn_secs = [t["seconds"] for r in rs for t in r["turns"]]
        case_secs = [sum(t["seconds"] for t in r["turns"]) for r in rs]
        tools = [r["grade"]["tool_ok"] for r in rs if r["grade"]["tool_ok"] is not None]
        out.append(
            f"| {v} | {len(seeds)} | {len(rs)} | {pct([r['grade']['correct'] for r in rs])} "
            f"| {pct([r['grade']['fabricated'] for r in rs])} | {pct([r['grade']['empty'] for r in rs])} | {pct(tools)} "
            f"| {sum(turn_secs) / len(turn_secs):.1f} | {sum(case_secs) / len(case_secs):.1f} |"
        )

    # ---------- 每次執行的答對率（看隨機性有多大）----------
    out += ["", "## 每次執行（seed）的答對率／捏造率", "", "| 設定 | " + " | ".join(
        f"seed{s}" for s in sorted({r['seed'] for r in records})) + " |",
        "| --- |" + " --- |" * len({r["seed"] for r in records})]
    for v in variants:
        cells = []
        for s in sorted({r["seed"] for r in records}):
            rs = [r for r in by_variant[v] if r["seed"] == s]
            cells.append(f"{pct([r['grade']['correct'] for r in rs])}／{pct([r['grade']['fabricated'] for r in rs])}"
                         if rs else "—")
        out.append(f"| {v} | " + " | ".join(cells) + " |")

    # ---------- 兩兩配對比較（以「題」為單位）----------
    # 同一題的 3 個 seed 結果高度相關，所以把每題 3 次的答對數當成一個樣本，有效樣本是 48 題，不是 144 筆。
    out += ["", "## 兩兩配對比較（以題為單位）", "",
            "每題算「後者答對次數 − 前者答對次數」。符號檢定：只看變好、變差的題數（雙尾、精確二項）。"
            "Bootstrap：對 48 題重抽 10000 次（random seed 0），取答對率差的 2.5%～97.5%。", "",
            "| 比較 | 答對率差 | 95% 信賴區間 | 變好題數 | 變差題數 | 符號檢定 p | 捏造：有捏造的題數（前者→後者） |",
            "| --- | --- | --- | --- | --- | --- | --- |"]
    ids = [c["id"] for c in cases]

    def per_case(v, key):
        return {i: sum(r["grade"][key] for r in by_variant[v] if r["id"] == i) for i in ids}

    for x, y in [("A_early", "B_rules"), ("B_rules", "C_current"), ("A_early", "C_current")]:
        if x not in by_variant or y not in by_variant:
            continue
        n_runs = len({r["seed"] for r in by_variant[x]})
        cx, cy = per_case(x, "correct"), per_case(y, "correct")
        diff = [cy[i] - cx[i] for i in ids]
        up, down = sum(d > 0 for d in diff), sum(d < 0 for d in diff)
        rng = random.Random(0)
        boots = sorted(sum(rng.choice(diff) for _ in ids) / (n_runs * len(ids)) * 100 for _ in range(10000))
        fx, fy = per_case(x, "fabricated"), per_case(y, "fabricated")
        out.append(
            f"| {x} → {y} | {sum(diff) / (n_runs * len(ids)) * 100:+.1f}pp | [{boots[250]:+.1f}, {boots[9749]:+.1f}] "
            f"| {up} | {down} | {sign_test(up, down):.2f} | {sum(v > 0 for v in fx.values())} → {sum(v > 0 for v in fy.values())} |"
        )

    # ---------- 分類別答對率 ----------
    def group(cat: str) -> str:
        return cat.split("（")[0]
    cats = list(dict.fromkeys(group(c["category"]) for c in cases))
    cat_of = {c["id"]: group(c["category"]) for c in cases}
    out += ["", "## 各類別答對率（括號內為捏造率）", "", "| 類別 | 題數 | " + " | ".join(variants) + " |",
            "| --- | --- |" + " --- |" * len(variants)]
    for cat in cats:
        n = sum(1 for c in cases if cat_of[c["id"]] == cat)
        cells = []
        for v in variants:
            rs = [r for r in by_variant[v] if cat_of[r["id"]] == cat]
            cells.append(f"{pct([r['grade']['correct'] for r in rs])}（{pct([r['grade']['fabricated'] for r in rs])}）")
        out.append(f"| {cat} | {n} | " + " | ".join(cells) + " |")

    # ---------- 每一題 ----------
    out += ["", "## 每一題（答對次數／執行次數）", "", "| 題號 | 類別 | 問題 | " + " | ".join(variants) + " |",
            "| --- | --- | --- |" + " --- |" * len(variants)]
    for c in cases:
        cells = []
        for v in variants:
            rs = [r for r in by_variant[v] if r["id"] == c["id"]]
            ok = sum(r["grade"]["correct"] for r in rs)
            fab = sum(r["grade"]["fabricated"] for r in rs)
            cells.append(f"{ok}/{len(rs)}" + (f" ⚠捏造{fab}" if fab else "") if rs else "—")
        question = " → ".join(c["turns"])
        out.append(f"| {c['id']} | {c['category']} | {question} | " + " | ".join(cells) + " |")

    # ---------- 失敗原因 ----------
    out += ["", "## 失敗原因（評分程式判斷的理由）", ""]
    for v in variants:
        fails = [r for r in by_variant[v] if not r["grade"]["correct"]]
        out += [f"### {v}（{len(fails)} 筆）", ""]
        for r in sorted(fails, key=lambda r: (r["id"], r["seed"])):
            out.append(f"- {r['id']} seed{r['seed']}：{'；'.join(r['grade']['reasons'])}")
        out.append("")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description="客服 Agent 評估")
    parser.add_argument("--variants", default="C_current", help="A_early,B_rules,C_current 或 all")
    parser.add_argument("--repeats", type=int, default=1, help="每種設定跑幾次（seed 1..N）")
    parser.add_argument("--only", help="只跑這些題號，用逗號分隔，例如 S01,M03")
    parser.add_argument("--regrade", action="store_true", help="不跑模型，只重新評分、重新產生表格")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    cases = load_cases(args.only)
    if not args.regrade:
        variants = VARIANTS if args.variants == "all" else args.variants.split(",")
        run(variants, args.repeats, cases)

    records = load_records(load_cases(None))
    summary = summarize(records, load_cases(None))
    (EVAL_DIR / "results" / "summary.md").write_text(summary + "\n", encoding="utf-8")
    print("\n" + summary.split("## 每次執行")[0])
    print(f"完整結果：{EVAL_DIR / 'results' / 'summary.md'}")


if __name__ == "__main__":
    main()
