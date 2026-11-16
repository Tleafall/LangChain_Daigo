"""
步驟 2：模板 + 管線（Chain）

學習重點：
- ChatPromptTemplate：有空格可以填的指令模板
- StrOutputParser：把 AI 的回傳物件變成純文字
- | 管線：前一站的輸出 = 下一站的輸入

執行方式：
    python src/step2_chain.py
"""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from config import get_model

# 第一站：模板，{role} 和 {question} 是要填的空格
prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一位{role}，用繁體中文回答，不超過三句話。"),
    ("human", "{question}"),
])

# 第二站：模型
model = get_model()

# 第三站：只留下文字
parser = StrOutputParser()

# 用 | 串成一條輸送帶
chain = prompt | model | parser

# 同一個問題，換不同身分，看回答有什麼不同
question = "我第一次網購，要注意什麼？"

for role in ["代購店的親切客服", "嚴肅的消費者保護專家"]:
    print(f"=== 身分：{role} ===")
    print(chain.invoke({"role": role, "question": question}))
    print()

# 小實驗：也可以只跑其中一站，看資料長什麼樣子
print("=== 只跑模板這一站，看填好的樣子 ===")
print(prompt.invoke({"role": "客服", "question": "測試"}))
