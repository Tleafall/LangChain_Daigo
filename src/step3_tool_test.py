"""
步驟 3：測試模型會不會「用工具」

做 Agent 之前一定要先跑這個測試。
不是每個模型都會正確呼叫工具，小模型常常會自己編答案。

學習重點：
- @tool 把一般函式變成工具
- docstring（三個引號裡的說明）是 AI 判斷要不要用工具的唯一依據
- create_agent 把模型和工具組成 Agent
- 從回傳的訊息看出 Agent 每一步做了什麼

執行方式：
    python src/step3_tool_test.py
"""

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from config import get_model


@tool
def get_price(product_name: str) -> str:
    """查詢商品目前的售價。只要顧客問到價格，一定要用這個工具查。"""
    print(f"   >>> [工具被呼叫了] get_price(product_name='{product_name}')")
    return f"{product_name} 目前售價 680 元"   # 測試用的假資料


agent = create_agent(
    model=get_model(),
    tools=[get_price],
    system_prompt=(
        "你是代購店的客服，用繁體中文回答。\n"
        "顧客問價格時，直接把顧客說的商品名稱當作參數，呼叫 get_price 查詢，不要先反問顧客。\n"
        "價格一定要用工具查，不能自己猜。"
    ),
)

question = "保濕乳液多少錢？"
print(f"顧客問：{question}\n")

result = agent.invoke({"messages": [{"role": "user", "content": question}]})

# 一則一則印出對話紀錄，看 Agent 的思路
print("\n=== Agent 的每一步 ===")
used_tool = False
for m in result["messages"]:
    name = type(m).__name__
    if isinstance(m, AIMessage) and m.tool_calls:
        used_tool = True
        print(f"[{name}] 決定呼叫工具：{m.tool_calls[0]['name']}({m.tool_calls[0]['args']})")
    elif isinstance(m, ToolMessage):
        print(f"[{name}] 工具回傳：{m.content}")
    else:
        print(f"[{name}] {m.content}")

print("\n=== 測試結果 ===")
if used_tool and "680" in result["messages"][-1].content:
    print("通過：模型有呼叫工具，也用了工具給的價格。可以拿來做 Agent。")
elif used_tool:
    print("部分通過：有呼叫工具，但最後回答沒用到工具的價格，可以多跑幾次看看。")
else:
    last = result["messages"][-1].content
    if any(ch.isdigit() for ch in last):
        print("沒通過：模型沒有用工具，回答裡的價格是它自己編的。")
    else:
        print("沒通過：模型沒有用工具（它選擇先反問顧客，或直接回答）。")
    print("可以試試：多跑幾次、把 docstring 和 system prompt 寫得更明確、換大一點的模型。")
