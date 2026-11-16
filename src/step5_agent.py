"""
步驟 5：代購客服 Agent（把前面學的全部組起來）

這個 Agent 有 5 個工具，它會自己判斷要用哪一個：
    search_faq          查店家規則（RAG）
    search_products     用需求找商品（RAG＋混合搜尋，可以設預算）
    get_product_detail  用商品編號查即時價格、庫存
    get_shipping_info   查運費和免運門檻
    search_711_store    用地址找附近的 7-11 門市

還加上了記憶：同一個 thread_id 的對話會被記住，可以連續問。

執行方式：
    python src/step5_agent.py
輸入 exit 離開，輸入 new 換一個新顧客（清空記憶）。
"""

from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from config import get_model
from knowledge import (
    build_faq_store,
    build_product_store,
    get_embeddings,
    hybrid_rank,
    load_shop_data,
    load_stores,
    search_stores,
)

# ============================================================
# 準備知識庫
# ============================================================
print("準備知識庫中（第一次會比較久）...")
shop = load_shop_data()
embeddings = get_embeddings()
faq_store = build_faq_store(embeddings)
product_store = build_product_store(embeddings, shop)
products_by_id = {p["id"]: p for p in shop["products"]}
stores = load_stores()   # 全台 7-11 門市（用地址精準比對，不需要向量搜尋）

# 相似度低於這個值，就當作「沒找到相關資料」。這個數字要用自己的資料去試。
# 實測：相關的問題大多在 0.45 以上，「你們有賣電視嗎」這種無關問題約 0.34，所以設 0.4。
MIN_SCORE = 0.4


# ============================================================
# 定義工具：docstring 寫得越清楚，AI 越知道什麼時候該用
# ============================================================
@tool
def search_faq(question: str) -> str:
    """查詢店家的規則和流程，例如：下單方式、付款、取貨、出貨時間、退換貨、取消訂單、聯絡客服。"""
    results = faq_store.similarity_search_with_score(question, k=2)
    hits = [doc.page_content for doc, score in results if score >= MIN_SCORE]
    return "\n\n".join(hits) if hits else "FAQ 裡沒有找到相關的資料。"


def _variant_lines(p: dict) -> str:
    """列出每個規格的價格和庫存。只有一種規格的商品，就只寫一行。"""
    lines = []
    for v in p["variants"]:
        name = " ".join(v["options"].values()) or "單一規格"
        stock = f"剩 {v['stock']} 件" if v["stock"] > 0 else "缺貨"
        lines.append(f"  - {name}：{v['price']} 元，{stock}")
    return "\n".join(lines)


def _format_product(doc, max_desc: int = 100) -> str:
    """把一個搜尋結果整理成文字。

    - 價格和庫存從商品資料「即時」讀取（不是存在向量庫裡的）。
    - 商品敘述只取前 100 個字：真實敘述常常好幾百字，全部丟給模型在 CPU 上會很慢。
    """
    p = products_by_id[doc.metadata["product_id"]]
    desc = p["description"].replace("\n", " ")
    if len(desc) > max_desc:
        desc = desc[:max_desc] + "…"
    status = "有現貨" if p["stock"] > 0 else "目前缺貨"
    return (
        f"[商品編號 {p['id']}] {p['name']}\n"
        f"分類：{p['category']}｜最低 {p['price']} 元｜{status}\n"
        f"規格與價格：\n{_variant_lines(p)}\n"
        f"說明：{desc}"
    )


def _unique_by_name(docs: list) -> list:
    """網站上有些商品名稱完全一樣（只是商品編號不同），只留第一個，避免重複推薦。"""
    seen, out = set(), []
    for d in docs:
        name = products_by_id[d.metadata["product_id"]]["name"]
        if name not in seen:
            seen.add(name)
            out.append(d)
    return out


@tool
def search_products(need: str, max_price: int | None = None) -> str:
    """依照顧客的需求找商品，回傳商品編號、說明、即時價格和庫存。

    need：顧客的膚質、用途或想要的類型，例如「乾燥肌保濕」、「送禮」、「防曬」。
          不要把預算、性別、價格寫進 need。
    max_price：顧客的預算上限（新台幣，整數）。顧客有提到預算才填，例如「500 以內」就填 500。
    """
    # 1. 混合搜尋：把所有商品依「跟需求的相關程度」排好順序
    #    每一筆是（總分, 關鍵字重疊比例, doc）
    ranked = hybrid_rank(product_store, need)
    if not ranked:
        return "沒有找到符合的商品。"
    keep = {id(d) for d in _unique_by_name([d for _, _, d in ranked])}
    ranked = [row for row in ranked if id(row[2]) in keep]

    # 2. 沒有預算限制：回傳最相關的 3 個
    if max_price is None:
        return "\n\n".join(_format_product(d) for _, _, d in ranked[:3])

    # 3. 有預算：數字比較交給程式做，不交給模型，才不會出錯
    #    先篩預算、再取最相關的，才不會漏掉「便宜又適合、但整體排名不夠前面」的商品。
    def price(d):
        return products_by_id[d.metadata["product_id"]]["price"]

    in_budget = [(score, overlap, d) for score, overlap, d in ranked if price(d) <= max_price]
    # 預算內「有命中關鍵字」的才算候選。實測：預算內相關的商品只有 3 個時，
    # 以前會把第 4 名的面膜、身體乳湊進來；這些湊數的商品，關鍵字命中都是 0。
    matched = [d for _, overlap, d in in_budget if overlap > 0]
    within = (matched or [d for _, _, d in in_budget])[:3]
    over = [d for _, _, d in ranked[:2] if price(d) > max_price]   # 最相關的前兩名裡，超出預算的

    parts = [f"【預算 {max_price} 元以內的候選】"]
    parts.append("\n\n".join(_format_product(d) for d in within) if within else "（沒有）")
    if over:
        parts.append(f"【跟需求最相關、但超出預算 {max_price} 元的商品】")
        parts.append("\n\n".join(_format_product(d) for d in over))
    parts.append(
        "注意：候選商品不一定都符合顧客的需求，請看說明判斷，不符合的不要推薦。"
        "如果預算內沒有符合的，就照實告訴顧客，再介紹超出預算的選擇並說明超出多少。"
    )
    return "\n\n".join(parts)


@tool
def get_product_detail(product_id: str) -> str:
    """用商品編號（例如 cmucbfqaccybh）查詢即時的價格和庫存，有多種規格的會分別列出。
    回答價格或有沒有貨之前，一定要先用這個工具查。"""
    p = products_by_id.get(product_id.strip().lower())
    if not p:
        return f"找不到商品編號 {product_id}。"
    return f"{p['name']}\n規格與價格：\n{_variant_lines(p)}\n商品頁：{p['url']}"


@tool
def search_711_store(address: str) -> str:
    """用顧客的地址找附近可以取貨的 7-11 門市（本店只能寄到 7-11 取貨）。

    address：顧客說的地址或地區，例如「新北市樹林區學勤路」、「台中市西屯區」。
    回傳分組的門市清單：在顧客說的那條路上的門市（最推薦），以及同一區的其他門市。
    """
    r = search_stores(stores, address, k=3)
    if not r["on_road"] and not r["in_town"]:
        return "找不到符合的 7-11 門市，請顧客提供更完整的地址（縣市、行政區、路名）。"

    def lines(group):
        return "\n".join(f"- {s['name']}門市（店號 {s['id']}）：{s['addr']}" for s in group)

    parts = []
    if r["note"]:
        parts.append(r["note"])
    if r["on_road"]:
        parts.append(f"【最推薦：在「{r['road']}」上的門市】（回答時一定要列出這一組）\n{lines(r['on_road'])}")
    if r["in_town"]:
        parts.append(f"【{r['town']}的其他門市】\n{lines(r['in_town'])}")
    parts.append("下單時在結帳頁搜尋門市名稱即可選擇。")
    return "\n\n".join(parts)


@tool
def get_shipping_info() -> str:
    """查詢目前的運費和免運門檻。"""
    s = shop["shipping"]
    return f"運費 {s['fee']} 元，單筆訂單滿 {s['free_shipping_threshold']} 元免運費。"


# ============================================================
# 組成 Agent
# ============================================================
SHOP_NAME = shop["shop"]["shop_name"]
LINE_ID = shop["shop"]["line_id"]

SYSTEM_PROMPT = f"""你是「{SHOP_NAME}」的線上客服，用親切、簡短的繁體中文回答。

最重要的規則：需要資料時，直接呼叫工具，拿到結果後再回答。
不要先跟顧客說「我幫您查一下」、「請稍等」，也不要反問顧客，先用顧客給的資訊去查。

該用哪個工具：
1. 店家規則、流程（付款、取貨、出貨、退換貨、取消）→ search_faq
2. 找商品、推薦商品 → search_products（結果已經包含價格和庫存）
   - 顧客有提到預算，就把金額填進 max_price，不要寫進 need。
3. 顧客說「第一個」、「那個」時，指的是你上一次「回答給顧客看」的清單裡的商品，
   不是工具搜尋結果的順序。找出那個商品的編號，用 get_product_detail 查。
4. 運費、免運 → get_shipping_info
5. 顧客問住家附近的 7-11、要在哪裡取貨 → search_711_store，用顧客說的地址查

取貨方式只有一種：商品寄到顧客選的 7-11 門市，顧客到門市取貨時再付款（叫做「7-11 賣貨便取貨付款」）。
這是「一種」方式，不要說成兩種。沒有宅配、不能寄到家裡、也不能寄到全家等其他超商。
不要問顧客「要店到店還是宅配」。

推薦商品的規則：
- 推薦前，先看每個商品的說明，判斷它是否真的符合顧客的需求（膚質、用途）。
  不符合的不要推薦，也不要列出來再說「它不太適合」。寧可只推薦一個，也不要硬湊。
- 回答要簡潔：最多推薦 3 個商品，每個用一兩句話介紹，附上價格和有沒有貨。
- 名稱一樣的商品只介紹一次。
- 工具說「預算內沒有符合的商品」時，要照實告訴顧客，再介紹最接近的選擇，並清楚說明超出預算多少。

其他規則：
- 價格、庫存、運費一定要用工具查，不能自己猜。
- 工具查不到的，就說不確定，請顧客透過官方 LINE（{LINE_ID}）詢問真人客服。
- 店家規則裡沒有寫的服務（例如宅配、刷卡、分期），不能說有。不可以自己推論或編造。
- 商品有多種規格（例如不同期限、容量）時，要說清楚每種規格的價格和庫存。
- 不誇大商品功效，不說商品能治療任何問題。
- 不談論其他顧客或訂單的資料。
"""

TOOLS = [search_faq, search_products, get_product_detail, get_shipping_info, search_711_store]

agent = create_agent(
    model=get_model(),
    tools=TOOLS,
    system_prompt=SYSTEM_PROMPT,
    checkpointer=InMemorySaver(),   # 記憶
)


def ask(question: str, thread_id: str) -> str:
    """送出一個問題，印出 Agent 用了哪些工具，回傳最後的回答。"""
    config = {"configurable": {"thread_id": thread_id}}
    before = len(agent.get_state(config).values.get("messages", []))
    result = agent.invoke({"messages": [{"role": "user", "content": question}]}, config)

    # 只看這一輪新增的訊息，印出用了哪些工具（教學時很好用）
    for m in result["messages"][before:]:
        if isinstance(m, AIMessage):
            for call in m.tool_calls:
                print(f"   （呼叫工具：{call['name']} {call['args']}）")
    return result["messages"][-1].content


# ============================================================
# 互動模式
# ============================================================
DEMO_QUESTIONS = [
    "有沒有適合乾肌的保濕產品？",
    "那第一個多少錢？還有貨嗎？",   # 測試記憶：「第一個」指的是上一題推薦的商品
    "運費怎麼算？",
    "拆開用過的可以退嗎？",
]

if __name__ == "__main__":
    import sys

    # 示範模式：python src/step5_agent.py --demo，自動問一輪固定問題
    if "--demo" in sys.argv:
        for q in DEMO_QUESTIONS:
            print(f"顧客：{q}")
            print(f"客服：{ask(q, thread_id='demo')}\n")
        sys.exit(0)

    customer_no = 1
    print("\n客服機器人已啟動！輸入 exit 離開，輸入 new 換新顧客。\n")
    while True:
        question = input("顧客：").strip()
        if not question:
            continue
        if question.lower() == "exit":
            break
        if question.lower() == "new":
            customer_no += 1
            print(f"--- 換成第 {customer_no} 位顧客（記憶清空）---\n")
            continue
        print(f"客服：{ask(question, thread_id=f'customer-{customer_no}')}\n")
