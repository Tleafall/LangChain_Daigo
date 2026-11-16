"""
步驟 4：RAG —— 讓 AI 先查 FAQ 再回答

學習重點：
- 讀檔案、依「## 問題」切成一題一段
- Embeddings：把文字轉成數字向量（用免費的本機模型）
- 向量資料庫：存向量、找出意思最像的段落（用餘弦相似度）
- 那個最難懂的字典：{"context": ..., "question": ...}

執行方式：
    python src/step4_rag_faq.py
"""

from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter

from config import EMBEDDING_MODEL, get_model

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ============================================================
# 第一部分：事前準備（只做一次）
# ============================================================

# 1. 讀取 FAQ 檔案
faq_text = (DATA_DIR / "faq.md").read_text(encoding="utf-8")

# 2. 切段：遇到「## 」就切一刀，一題一段
#    切完每段的 metadata 會記住它的標題（就是問題本身）
splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[("##", "question")])
chunks = splitter.split_text(faq_text)
chunks = [c for c in chunks if "question" in c.metadata]   # 去掉最上面的說明文字

# 把問題也放進內文，搜尋時比較容易找到
for c in chunks:
    c.page_content = f"問：{c.metadata['question']}\n答：{c.page_content}"

print(f"FAQ 切成了 {len(chunks)} 段")

# 3. 準備 Embeddings 模型（第一次執行會下載約 1GB，之後就不用）
print("載入 Embeddings 模型中...")
embeddings = HuggingFaceEmbeddings(
    model_name=EMBEDDING_MODEL,
    encode_kwargs={"normalize_embeddings": True},   # 正規化，讓餘弦相似度更準
)

# 4. 轉成向量並存進向量資料庫（InMemory 預設就是用餘弦相似度）
store = InMemoryVectorStore.from_documents(chunks, embeddings)
print("向量資料庫建立完成\n")

# ============================================================
# 小實驗：先看看「搜尋」這一步找到什麼
# ============================================================
test_q = "東西壞掉可以換嗎"
print(f"=== 搜尋測試：「{test_q}」===")
for doc, score in store.similarity_search_with_score(test_q, k=3):
    print(f"  相似度 {score:.3f} → {doc.metadata['question']}")
print("（注意：問題裡沒有「瑕疵」兩個字，還是找得到，因為比的是意思）\n")

# ============================================================
# 第二部分：組成 RAG Chain
# ============================================================

retriever = store.as_retriever(search_kwargs={"k": 2})   # 每次拿最像的 2 段


def format_docs(docs):
    """把找到的好幾段 Document，合成一整段文字，才能填進模板。"""
    return "\n\n".join(d.page_content for d in docs)


prompt = ChatPromptTemplate.from_messages([
    ("system",
     "你是代購店的客服，用繁體中文、親切簡短地回答。\n"
     "只能根據下面的資料回答。資料裡沒有的，就說「這個問題我不確定，"
     "建議您透過官方 LINE 詢問真人客服」，不要自己編。\n\n"
     "資料：\n{context}"),
    ("human", "{question}"),
])

# 那個字典：同一個問題同時走兩條路
#   "context"  這條路：問題 → 去資料庫找相關段落 → 合成一段文字
#   "question" 這條路：問題原封不動傳下去
rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | get_model()
    | StrOutputParser()
)

# ============================================================
# 第三部分：實際提問
# ============================================================
questions = [
    "我要怎麼付錢？",
    "粉底拆開用過了還能退嗎？",
    "你們有賣電視嗎？",   # FAQ 裡沒有的問題，看 AI 會不會亂編
]

for q in questions:
    print(f"顧客：{q}")
    print(f"客服：{rag_chain.invoke(q)}\n")
