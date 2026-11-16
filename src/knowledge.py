"""
知識庫模組：建立兩個向量資料庫，給步驟 5 的 Agent 使用。

- FAQ 庫：店家規則、流程（取貨、退換貨……）
- 商品庫：商品名稱、分類、敘述（不放價格和庫存，因為那些會變）

這裡做的事跟步驟 4 一樣，只是整理成函式方便重複使用。
"""

import json
import re
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter

from config import EMBEDDING_MODEL

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_shop_data() -> dict:
    """讀取商品和運費資料。

    data/products.json 是用 scripts/sync_from_website.py 從上線網站同步下來的真實資料。
    """
    return json.loads((DATA_DIR / "products.json").read_text(encoding="utf-8"))


def get_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        encode_kwargs={"normalize_embeddings": True},
    )


def build_faq_store(embeddings, skip_questions: tuple[str, ...] = ()) -> InMemoryVectorStore:
    """FAQ：依「## 問題」切段，一題一段。

    skip_questions：要拿掉的題目（只有評估「早期版本」時會用到，平常不用填）。
    """
    text = (DATA_DIR / "faq.md").read_text(encoding="utf-8")
    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[("##", "question")])
    chunks = [c for c in splitter.split_text(text) if "question" in c.metadata]
    chunks = [c for c in chunks if c.metadata["question"] not in skip_questions]
    for c in chunks:
        c.page_content = f"問：{c.metadata['question']}\n答：{c.page_content}"
    return InMemoryVectorStore.from_documents(chunks, embeddings)


def load_stores() -> list[dict]:
    """讀取全台 7-11 門市清單（每家有 id、name、addr、city、town）。"""
    return json.loads((DATA_DIR / "stores-711.json").read_text(encoding="utf-8"))


def search_stores(stores: list[dict], address: str, k: int = 3) -> dict:
    """用地址找附近的 7-11 門市。

    這裡「不用」向量搜尋，因為地址要的是精準比對：「學勤路」就是學勤路，
    意思相近的路名沒有意義。做法是把地址拆成「縣市、行政區、路名」三段來比對。

    回傳分組結果，讓模型清楚知道哪一家最符合（實測發現混在一起列的話，模型有時會漏掉最符合的那家）：
        {"road": 路名, "town": 行政區,
         "on_road": 在這條路上的門市, "in_town": 這個行政區的其他門市, "note": 提醒}
    """
    q = address.replace("臺", "台")   # 門市資料統一用「台」

    cities = sorted({s["city"] for s in stores}, key=len, reverse=True)
    # 顧客可能只說「高雄」沒說「高雄市」，所以也比對去掉「市／縣」的名稱
    city = next((c for c in cities if c in q), "") or next((c for c in cities if c[:-1] in q), "")
    towns = sorted({s["town"] for s in stores if not city or s["city"] == city}, key=len, reverse=True)
    town = next((t for t in towns if t in q), "")
    rest = q.replace(city, "").replace(town, "")
    m = re.search(r"([一-鿿]{1,6}?(?:大道|路|街))", rest)
    road = m.group(1) if m else ""

    in_city = [s for s in stores if not city or s["city"] == city]
    on_road = [s for s in in_city if road and road in s["addr"]]
    # 同一條路上，行政區也對的排前面
    on_road.sort(key=lambda s: s["town"] != town)
    on_road_ids = {s["id"] for s in on_road}
    in_town = [s for s in in_city if town and s["town"] == town and s["id"] not in on_road_ids]
    if not road and not town:   # 只說了縣市（例如「高雄」），就列這個縣市的門市
        in_town = in_city if city else []

    # 顧客常把行政區講錯（例如學勤路其實在三峽區，不在樹林區），找到的話要提醒
    note = ""
    if on_road and town and not any(s["town"] == town for s in on_road):
        real_towns = "、".join(sorted({s["town"] for s in on_road}))
        note = f"提醒：「{road}」上的 7-11 在{real_towns}，不在顧客說的{town}，請跟顧客確認地址。"
    return {"road": road, "town": town or city, "on_road": on_road[:k], "in_town": in_town[:k], "note": note}


def _bigrams(text: str) -> set[str]:
    """把中文切成「每兩個字一組」，例如「乾肌保濕」→ {乾肌, 肌保, 保濕}。"""
    chars = [ch for ch in text if ch.strip() and ch not in "，。？！、：「」（）\n"]
    return {chars[i] + chars[i + 1] for i in range(len(chars) - 1)}


def hybrid_rank(store: InMemoryVectorStore, query: str, keyword_weight: float = 0.3):
    """跟 hybrid_search 一樣，但回傳全部結果和分數：[(總分, 關鍵字重疊比例, doc), ...]。

    需要知道「有沒有命中關鍵字」時用這個（例如篩預算時，用來排除湊數的不相關商品）。
    """
    query_bigrams = _bigrams(query)
    rows = []
    for doc, score in store.similarity_search_with_score(query, k=min(len(store.store), 200)):
        overlap = len(query_bigrams & _bigrams(doc.page_content)) / max(len(query_bigrams), 1)
        rows.append((score + keyword_weight * overlap, overlap, doc))
    rows.sort(key=lambda x: x[0], reverse=True)
    return rows


def hybrid_search(store: InMemoryVectorStore, query: str, k: int = 3, keyword_weight: float = 0.3):
    """混合搜尋 = 意思相似度 + 關鍵字重疊程度。

    為什麼需要？只用意思搜尋時，「乾肌保濕」找出來的防曬乳（0.668）和保濕乳液（0.666）
    分數幾乎一樣，順序等於是隨機的。保濕乳液的說明裡真的有「保濕」兩個字，
    加上關鍵字分數以後，它就會排到前面。

    做法：
    1. 先用意思搜尋算出每個商品的相似度（商品少於 200 個時全部都算）
    2. 算每個商品跟問題有幾組「兩個字」相同（重疊比例 0～1）
    3. 總分 = 相似度 + keyword_weight × 重疊比例，重新排序取前 k 個

    為什麼要全部都算？實測搜「卸妝」時，名稱裡就有「卸妝液」「潔顏油」的兩個商品，
    在意思搜尋裡只排第 20、22 名（真實商品文案很長、又有很多 emoji，Embeddings 模型抓不準）。
    如果只取前 6 或前 20 名當候選，它們在第一步就被淘汰，關鍵字分數根本沒機會發揮。
    """
    return [doc for _, _, doc in hybrid_rank(store, query, keyword_weight)[:k]]


def build_product_store(embeddings, shop: dict) -> InMemoryVectorStore:
    """商品：一個商品一份 Document，metadata 記住 product_id，之後用來查價格。

    規格名稱（例如「10ML期限27.04」）也放進內文，顧客問容量、色號時比較找得到。
    價格和庫存「不」放進內文，因為它們會變，要查詢當下才讀取。
    """
    docs = []
    for p in shop["products"]:
        options = "、".join(
            " ".join(v["options"].values()) for v in p.get("variants", []) if v.get("options")
        )
        text = f"商品名稱：{p['name']}\n分類：{p['category']}\n"
        if options:
            text += f"規格：{options}\n"
        text += f"說明：{p['description']}"
        docs.append(Document(page_content=text, metadata={"product_id": p["id"]}))
    return InMemoryVectorStore.from_documents(docs, embeddings)
