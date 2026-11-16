"""
步驟 1：跟 AI 說第一句話

學習重點：
- 怎麼建立模型
- invoke() 送出問題
- .content 拿出回答的文字
- 訊息有三種角色：System（規則）、Human（使用者）、AI（模型）

執行方式：
    python src/step1_hello.py
"""

import time

from langchain_core.messages import HumanMessage, SystemMessage

from config import get_model

model = get_model()

# --- 1. 最簡單的用法：直接丟一句話 ---
print("=== 1. 直接問問題 ===")
start = time.time()
answer = model.invoke("用一句話介紹你自己")
print(answer.content)
print(f"（花了 {time.time() - start:.1f} 秒）\n")

# --- 2. 加上角色：先用 SystemMessage 設定規則 ---
print("=== 2. 用 SystemMessage 設定身分 ===")
messages = [
    SystemMessage(content="你是一位代購店的親切客服，回答要簡短，用繁體中文。"),
    HumanMessage(content="你們店是賣什麼的？"),
]
answer = model.invoke(messages)
print(answer.content)

# --- 3. 看看回傳的「包裹」裡還有什麼 ---
print("\n=== 3. 回傳物件裡的其他資訊 ===")
print("型別：", type(answer).__name__)
print("用量：", answer.usage_metadata)   # 用了多少 token（本機模型不用錢，但可以觀察）
