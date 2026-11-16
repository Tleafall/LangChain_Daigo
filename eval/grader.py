"""
評分規則：全部用程式判斷（字串、正規表示式、數字比對），同樣的輸入一定得到同樣的分數。

每一題會得到三個判斷：
    correct     答對：回答包含該有的資訊，而且沒有違反任何規則
    fabricated  捏造：說出資料裡沒有的服務、價格、品牌或門市
    tool_ok     工具：最後一輪有沒有呼叫該用的工具（題目沒指定就是 None，不列入計算）

為什麼不用 LLM 當裁判？見 eval/REPORT.md 的「設計決策」。
"""

import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SHOP = json.loads((DATA_DIR / "products.json").read_text(encoding="utf-8"))
STORE_NAMES = {s["name"] for s in json.loads((DATA_DIR / "stores-711.json").read_text(encoding="utf-8"))}

# 資料裡所有商品、規格的價格
PRODUCT_PRICES = {p["price"] for p in SHOP["products"]} | {
    v["price"] for p in SHOP["products"] for v in p["variants"]
}
FEE = SHOP["shipping"]["fee"]                                   # 60
THRESHOLD = SHOP["shipping"]["free_shipping_threshold"]         # 899

# ------------------------------------------------------------
# 全域捏造規則：本店「沒有」的服務。不管哪一題，回答裡出現肯定句就算捏造。
# 否定句（「沒有宅配」「目前沒有提供分期」）由 find_affirmative() 排除。
# ------------------------------------------------------------
SERVICE_FABRICATION = {
    "宅配": [
        r"有(提供)?宅配",
        r"宅配(服務)?的?運費",
        r"(可以|能)(幫您)?(宅配|寄(送)?到(您的?)?(家|府|住家))",
    ],
    "其他超商": [r"(可以|能)(寄|送|選|到)[^。，！\n]{0,4}(全家|萊爾富|OK超商)"],
    "刷卡": [r"(可以|能|支援|接受)(使用)?(線上)?(刷卡|信用卡)"],
    "分期": [r"(可以|能|支援|提供)(使用)?分期"],
}
NEGATION = "不沒無未非否"   # 「否」：「是否可以開發票」是疑問，不是肯定句


def find_affirmative(pattern: str, text: str) -> str | None:
    """找出「肯定句」的命中：命中位置前面 3 個字裡有 不／沒／無／未／非，就當成否定句跳過。

    例如「目前沒有提供分期」：命中「提供分期」，前 3 個字是「前沒有」→ 否定句，不算。
    只看前 1 個字不夠：「沒有提供」的前 1 個字是「有」，會被誤判成捏造（人工檢查時發現的）。
    """
    for m in re.finditer(pattern, text):
        if not any(ch in NEGATION for ch in text[max(0, m.start() - 3):m.start()]):
            return m.group(0)
    return None

# 本店沒有賣的常見品牌。回答提到（而且顧客沒先提）就算捏造商品。
UNSOLD_BRANDS = [
    "SK-II", "雅詩蘭黛", "蘭芝", "資生堂", "契爾氏", "Kiehl", "La Mer", "海洋拉娜", "Bioderma", "貝德瑪",
    "薇姿", "珂潤", "Curel", "露得清", "妮維雅", "Olay", "肌研", "DHC", "Cetaphil", "舒特膚", "雅漾",
    "Avene", "曼秀雷敦", "蘇菲娜", "Innisfree", "悅詩風吟", "雪花秀", "克蘭詩", "嬌蘭", "Dyson",
]

# 目前缺貨的商品（products.json 裡 stock = 0）。回答提到它卻沒說缺貨，算答錯（不算捏造）。
OUT_OF_STOCK = {
    "Kanebo 防曬": ["Kanebo", "佳麗寶", "ALLIE"],
    "MISS DIOR 淡香水": ["MISS DIOR", "Miss Dior", "花漾迪奧"],
    "ZARA 淡香精": ["ZARA"],
}
OOS_WORDS = r"缺貨|沒貨|無庫存|沒有庫存|售完|賣完|沒有現貨|暫無|補貨|庫存為 ?0|沒有存貨"

# 「XX門市」前面常見的一般字詞（不是門市名稱），例如「附近的門市」「取貨門市」
STORE_GENERIC_SUFFIX = ("的", "家", "些", "間", "個", "這", "那", "其他", "附近", "取貨", "選擇", "指定",
                        "推薦", "11", "超商", "該", "此", "各", "哪", "到", "在", "去", "區", "一", "最近",
                        "符合", "以下", "上述", "兩", "三", "鄉", "鎮", "市", "路", "街", "段",
                        "搜尋", "查詢", "找到", "相關")


def numbers_with_unit(text: str) -> list[int]:
    """抓出回答裡所有「金額」：123 元、123元、NT$123、$123。"""
    found = re.findall(r"(\d[\d,]*)\s*(?:元|塊)", text) + re.findall(r"(?:NT\$|\$)\s*(\d[\d,]*)", text)
    return [int(n.replace(",", "")) for n in found]


def first_price(text: str) -> int | None:
    """回答裡第一個出現、而且是商品價格的金額（給「那第一個多少錢」用）。"""
    for n in numbers_with_unit(text):
        if n in PRODUCT_PRICES:
            return n
    return None


def any_in(text: str, words: list[str]) -> bool:
    return any(w in text for w in words)


def grade(case: dict, run: dict) -> dict:
    """run 的格式：{"turns": [{"user", "answer", "tool_calls": [{"name", "args"}], "tool_outputs": [str]}]}"""
    last = run["turns"][-1]
    answer = last["answer"]
    users = " ".join(t["user"] for t in run["turns"])
    all_tool_text = "\n".join(o for t in run["turns"] for o in t["tool_outputs"])
    wrong, fab = [], []   # 答錯原因、捏造原因

    # ---------- 0. 空白回答：模型呼叫完工具後，有時最後一則訊息是空的，顧客什麼都看不到 ----------
    empty = not answer.strip()
    if empty:
        wrong.append("回答是空的")

    # ---------- 1. 必須包含：每一組至少出現其中一個 ----------
    for group in case.get("must", []):
        if not any_in(answer, group):
            wrong.append(f"缺少：{'／'.join(group[:4])}")

    # ---------- 2. 不可以出現（答錯，但不一定是捏造）----------
    for pattern in case.get("must_not", []):
        if re.search(pattern, answer):
            wrong.append(f"不該出現：{pattern}")

    # ---------- 3. 捏造：服務 ----------
    for service, patterns in SERVICE_FABRICATION.items():
        for pattern in patterns:
            hit = find_affirmative(pattern, answer)
            if hit:
                fab.append(f"捏造服務（{service}）：「{hit}」")
    for pattern in case.get("fabrication", []):
        hit = find_affirmative(pattern, answer)
        if hit:
            fab.append(f"捏造（本題規則）：「{hit}」")

    # ---------- 4. 捏造：金額 ----------
    # 合理的數字 = 資料裡的價格、運費、工具回傳過的數字、顧客說過的數字，以及由它們算出來的差額
    user_numbers = [int(n) for n in re.findall(r"\d+", users)]
    allowed = PRODUCT_PRICES | {FEE, THRESHOLD} | set(user_numbers)
    allowed |= {int(n) for n in re.findall(r"\d+", all_tool_text)}
    allowed |= {THRESHOLD - n for n in user_numbers}           # 還差多少免運
    allowed |= {n + FEE for n in user_numbers}                 # 加上運費
    allowed |= {p - n for p in PRODUCT_PRICES for n in user_numbers}   # 超出預算多少
    for n in numbers_with_unit(answer):
        if n not in allowed:
            fab.append(f"捏造金額：{n} 元")

    # ---------- 5. 捏造：沒賣的品牌 ----------
    for brand in UNSOLD_BRANDS:
        if brand.lower() in answer.lower() and brand.lower() not in users.lower():
            fab.append(f"捏造商品（沒賣的品牌）：{brand}")

    # ---------- 6. 捏造：門市名稱要出現在工具回傳的門市清單裡 ----------
    # 只檢查「像店名」的位置：行首、項目符號、粗體、頓號、引號後面緊接的「XX門市」，
    # 例如「* **學勤門市**」「、三暉門市」。句子中間的「可以搜尋門市」不會被當成店名。
    tool_store_names = set(re.findall(r"- (\S+?)門市（店號", all_tool_text))
    for cap in re.findall(r"(?:^|[\s*、「：:（(])([一-鿿A-Za-z0-9]{1,8})\s*門市", answer, flags=re.M):
        if cap.endswith(STORE_GENERIC_SUFFIX):
            continue
        if not any(cap.endswith(name) for name in tool_store_names):
            fab.append(f"門市不在工具結果裡：{cap}門市")

    # ---------- 7. 預算：提到超出預算的商品價格，就要說明超出 ----------
    budget = case.get("budget")
    if budget:
        over = [n for n in numbers_with_unit(answer) if n in PRODUCT_PRICES and n > budget]
        if over and not re.search(r"超出|超過|超了|高出|預算外|高於|不在預算|預算以上", answer):
            wrong.append(f"推薦超出預算的商品（{over}）卻沒說明")

    # ---------- 8. 缺貨商品要說缺貨 ----------
    for product, words in OUT_OF_STOCK.items():
        if any_in(answer, words) and not re.search(OOS_WORDS, answer):
            wrong.append(f"提到缺貨商品（{product}）沒說缺貨")

    # ---------- 9. 多輪：「那第一個多少錢」要回答第一輪清單第一個商品的價格 ----------
    if case.get("first_price_repeat"):
        target = first_price(run["turns"][0]["answer"])
        if target is None:
            wrong.append("第一輪回答沒有列出價格，無法判斷")
        elif str(target) not in answer.replace(",", ""):
            wrong.append(f"第一個商品是 {target} 元，第二輪回答沒提到這個價格")

    # ---------- 10. 工具：最後一輪有沒有用對工具 ----------
    called = [c["name"] for c in last["tool_calls"]]
    tool_ok = None
    if case.get("tools"):
        tool_ok = all(any(name in called for name in req.split("|")) for req in case["tools"])
        for name, expected in case.get("args", {}).items():
            calls = [c["args"] for c in last["tool_calls"] if c["name"] == name]
            if not any(all(a.get(k) == v for k, v in expected.items()) for a in calls):
                tool_ok = False

    fabricated = bool(fab)
    return {
        "correct": not wrong and not fabricated,
        "fabricated": fabricated,
        "empty": empty,
        "tool_ok": tool_ok,
        "reasons": wrong + fab,
    }
