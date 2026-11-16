"""
要比較的三種設定（都用同一個模型、同一份商品與門市資料）。

    A_early      早期版：「坑 6」修正之前的樣子（還原自 docs/03_教學建議.md 的踩雷紀錄）
    B_rules      只加規則：A ＋ FAQ 補上「有宅配嗎？」＋ system prompt 的防捏造規則
    C_current    目前版：B ＋ 程式保證（預算內只留命中關鍵字的商品、同名商品去重複、門市分組）

A → B 看「把規則寫清楚」的效果；B → C 看「能用程式保證的交給程式」的效果。

注意：專案當時沒有用 git，所以 A 不是從版本紀錄拿回來的，而是依照踩雷紀錄
「修了什麼」反向拿掉。拿掉的每一段都列在下面，可以逐行對照 src/step5_agent.py。
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

import step5_agent as bot          # 載入時會建好目前版的知識庫和 Agent
from config import get_model
from knowledge import build_faq_store, hybrid_rank

DELIVERY_QUESTION = "有宅配嗎？可以寄到家裡嗎？"

# 坑 6 修正時加進 system prompt 的句子。A 版本把它們拿掉。
RULES_ADDED_FOR_PIT6 = [
    "取貨方式只有一種：商品寄到顧客選的 7-11 門市，顧客到門市取貨時再付款（叫做「7-11 賣貨便取貨付款」）。\n"
    "這是「一種」方式，不要說成兩種。沒有宅配、不能寄到家裡、也不能寄到全家等其他超商。\n"
    "不要問顧客「要店到店還是宅配」。\n\n",
    "- 回答要簡潔：最多推薦 3 個商品，每個用一兩句話介紹，附上價格和有沒有貨。\n",
    "- 名稱一樣的商品只介紹一次。\n",
    "- 店家規則裡沒有寫的服務（例如宅配、刷卡、分期），不能說有。不可以自己推論或編造。\n",
]


def remove_rules(prompt: str) -> str:
    for part in RULES_ADDED_FOR_PIT6:
        assert part in prompt, f"step5_agent.py 的 prompt 改過了，找不到這段：{part[:30]}"
        prompt = prompt.replace(part, "")
    return prompt


# ============================================================
# 早期版的工具：名稱、說明（docstring）、參數都跟目前版一模一樣，
# 模型看到的工具清單完全相同，只有「程式裡做的事」不同。
# ============================================================
def make_early_tools(faq_store):
    @tool("search_faq", description=bot.search_faq.description)
    def search_faq(question: str) -> str:
        results = faq_store.similarity_search_with_score(question, k=2)
        hits = [doc.page_content for doc, score in results if score >= bot.MIN_SCORE]
        return "\n\n".join(hits) if hits else "FAQ 裡沒有找到相關的資料。"

    @tool("search_products", description=bot.search_products.description)
    def search_products(need: str, max_price: int | None = None) -> str:
        # 差別 1：沒有去除同名商品
        ranked = hybrid_rank(bot.product_store, need)
        if not ranked:
            return "沒有找到符合的商品。"
        if max_price is None:
            return "\n\n".join(bot._format_product(d) for _, _, d in ranked[:3])

        def price(d):
            return bot.products_by_id[d.metadata["product_id"]]["price"]

        # 差別 2：預算內直接取前 3 名，沒有「必須命中關鍵字」這一關（會湊進不相關的商品）
        within = [d for _, _, d in ranked if price(d) <= max_price][:3]
        over = [d for _, _, d in ranked[:2] if price(d) > max_price]
        parts = [f"【預算 {max_price} 元以內的候選】"]
        parts.append("\n\n".join(bot._format_product(d) for d in within) if within else "（沒有）")
        if over:
            parts.append(f"【跟需求最相關、但超出預算 {max_price} 元的商品】")
            parts.append("\n\n".join(bot._format_product(d) for d in over))
        parts.append(
            "注意：候選商品不一定都符合顧客的需求，請看說明判斷，不符合的不要推薦。"
            "如果預算內沒有符合的，就照實告訴顧客，再介紹超出預算的選擇並說明超出多少。"
        )
        return "\n\n".join(parts)

    @tool("search_711_store", description=bot.search_711_store.description)
    def search_711_store(address: str) -> str:
        # 差別 3：門市不分組，同一條路和同一區的門市混在一起列 5 家（行政區不符的提醒保留）
        r = bot.search_stores(bot.stores, address, k=5)
        mixed = (r["on_road"] + r["in_town"])[:5]
        if not mixed:
            return "找不到符合的 7-11 門市，請顧客提供更完整的地址（縣市、行政區、路名）。"
        lines = "\n".join(f"- {s['name']}門市（店號 {s['id']}）：{s['addr']}" for s in mixed)
        parts = [r["note"]] if r["note"] else []
        parts += [lines, "下單時在結帳頁搜尋門市名稱即可選擇。"]
        return "\n\n".join(parts)

    return [search_faq, search_products, bot.get_product_detail, bot.get_shipping_info, search_711_store]


def build_agent(variant: str, seed: int | None = None):
    """依照設定名稱建立 Agent。三種設定都重新建立，才能一起固定 seed。"""
    if variant == "C_current":
        return create_agent(model=get_model(seed=seed), tools=bot.TOOLS,
                            system_prompt=bot.SYSTEM_PROMPT, checkpointer=InMemorySaver())

    if variant == "B_rules":
        prompt = bot.SYSTEM_PROMPT
        faq_store = bot.faq_store
    elif variant == "A_early":
        prompt = remove_rules(bot.SYSTEM_PROMPT)
        faq_store = build_faq_store(bot.embeddings, skip_questions=(DELIVERY_QUESTION,))
    else:
        raise ValueError(f"不認識的設定：{variant}")

    tools = make_early_tools(faq_store)
    # 確認模型看到的工具定義和目前版完全一樣（只比對名稱、說明、參數）
    for early, now in zip(tools, bot.TOOLS):
        assert early.name == now.name and early.description == now.description
        assert early.tool_call_schema.model_json_schema() == now.tool_call_schema.model_json_schema()
    return create_agent(model=get_model(seed=seed), tools=tools, system_prompt=prompt,
                        checkpointer=InMemorySaver())


VARIANTS = ["A_early", "B_rules", "C_current"]
