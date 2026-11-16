"""
從上線中的「予晴美粧代購」網站，同步真實的商品和店家規則到 data/ 資料夾。

會產生：
    data/products.json   所有上架商品（名稱、分類、敘述、各規格的價格與庫存）＋運費設定
    data/faq.md          從網站的「退換貨說明」「服務條款」頁面整理出來的規則
    data/stores-711.json 全台 7-11 門市清單（從代購網站專案複製）

只讀取網站上「任何人都看得到」的公開頁面，不需要密碼，也不會碰會員、訂單等客戶資料。

執行方式（在專案資料夾）：
    .venv\\Scripts\\python.exe scripts\\sync_from_website.py

商品有更新時，重新執行一次就好。
"""

import json
import re
import shutil
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SITE = "https://yuchingmakeup.com"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HEADERS = {"User-Agent": "Mozilla/5.0 (LangChain-Daigo product sync)"}


# ------------------------------------------------------------
# 共用小工具
# ------------------------------------------------------------
def fetch(path: str) -> str:
    """下載一個網頁，失敗會重試 3 次。"""
    for attempt in range(3):
        try:
            req = urllib.request.Request(SITE + path, headers=HEADERS)
            return urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
        except Exception as e:  # 網路不穩時重試
            if attempt == 2:
                raise
            print(f"  （{path} 下載失敗，重試：{e}）")
            time.sleep(2)
    return ""


def rsc_payload(html: str) -> str:
    """Next.js 網站會把頁面資料放在 self.__next_f.push([1,"..."]) 裡，把它們接起來解碼。"""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html)
    return "".join(json.loads(c) for c in chunks)


def extract_json_object(text: str, key: str) -> dict | None:
    """在一段文字裡找到 "key":{...}，把後面那個 JSON 物件完整解析出來。"""
    i = text.find(f'"{key}":{{')
    if i < 0:
        return None
    obj, _ = json.JSONDecoder().raw_decode(text, i + len(key) + 3)
    return obj


class MainText(HTMLParser):
    """把網頁 <main> 裡的文字抓出來，遇到標題和段落就換行。"""

    BLOCKS = {"h1", "h2", "h3", "p", "li", "div", "section", "br"}

    def __init__(self):
        super().__init__()
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "main":
            self.depth += 1
        if self.depth and tag in self.BLOCKS:
            self.parts.append("\n")
        if self.depth and tag in {"h1", "h2", "h3"}:
            self.parts.append("## ")

    def handle_endtag(self, tag):
        if tag == "main":
            self.depth -= 1
        if self.depth and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.depth:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw.splitlines()]
        out, blank = [], False
        for ln in lines:
            if not ln:
                blank = True
                continue
            if blank and out:
                out.append("")
            out.append(ln)
            blank = False
        return "\n".join(out)


def clean_description(text: str) -> str:
    """整理商品敘述：統一換行、去掉多餘空白。保留原文內容。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


# ------------------------------------------------------------
# 1. 商品
# ------------------------------------------------------------
def list_product_slugs() -> list[str]:
    """從「全部商品」頁面一頁一頁翻，收集每個商品的網址代號。"""
    slugs: list[str] = []
    page = 1
    while True:
        html = fetch(f"/products?page={page}")
        found = re.findall(r'href="/products/([a-z0-9]+)"', html)
        new = [s for s in dict.fromkeys(found) if s not in slugs]
        if not new:
            break
        slugs.extend(new)
        print(f"  第 {page} 頁：{len(new)} 個商品")
        page += 1
    return slugs


def fetch_product(slug: str) -> dict | None:
    payload = rsc_payload(fetch(f"/products/{slug}"))
    p = extract_json_object(payload, "product")
    if not p:
        return None
    # 分類名稱：在麵包屑裡，格式是 "href":"/category/xxx",...,"children":"分類名稱"
    m = re.search(r'"href":"/category/[^"]+","className":"[^"]*","children":"([^"]+)"', payload)
    variants = [
        {"options": v.get("options", {}), "price": v["price"], "stock": v["stock"]}
        for v in p.get("variants", [])
    ]
    return {
        "id": p["slug"],
        "name": p["title"].strip(),
        "category": m.group(1) if m else p.get("categorySlug", ""),
        "description": clean_description(p.get("description", "")),
        "price": min((v["price"] for v in variants), default=p.get("price", 0)),
        "stock": sum(v["stock"] for v in variants),
        "variants": variants,
        "url": f"{SITE}/products/{p['slug']}",
    }


# ------------------------------------------------------------
# 2. 運費等網站設定
# ------------------------------------------------------------
def fetch_settings() -> dict:
    payload = rsc_payload(fetch("/cart"))
    i = payload.find('"freeShippingThreshold"')
    start = payload.rfind("{", 0, i)
    obj, _ = json.JSONDecoder().raw_decode(payload, start)
    return {
        "shop_name": obj.get("name", ""),
        "fee": obj.get("shippingFee"),
        "free_shipping_threshold": obj.get("freeShippingThreshold"),
        "announcement": obj.get("announcement", ""),
        "line_id": obj.get("lineId", ""),
        "line_url": obj.get("lineUrl", ""),
    }


# ------------------------------------------------------------
# 3. 店家規則（FAQ）
# ------------------------------------------------------------
def fetch_policy_page(path: str) -> str:
    parser = MainText()
    parser.feed(fetch(path))
    return parser.text()


def policy_to_faq(text: str, page_name: str) -> str:
    """把「一、xxx」「二、xxx」這種條列標題，轉成 FAQ 用的「## 」段落。

    每題前面加上頁面名稱（例如「退換貨說明：一、七天猶豫期」），
    因為「退換貨說明」和「服務條款」都有「一、」「六、聯絡我們」，不加會分不清楚。
    """
    nav_lines = {"隱私權政策服務條款退換貨說明"}
    out = []
    for ln in text.splitlines():
        if ln.startswith("首頁/") or ln in nav_lines or ln.startswith("最後更新"):
            continue  # 網頁的導覽列、更新日期，不是規則內容
        if re.match(r"^(## )?[一二三四五六七八九十]+、", ln):
            out.append(f"## {page_name}：" + ln.removeprefix("## "))
        elif ln.startswith("## "):
            continue  # 頁面大標題（例如「退換貨說明」）不當成一題
        elif out or ln:
            out.append(ln)
    return "\n".join(out).strip()


# ------------------------------------------------------------
# 主程式
# ------------------------------------------------------------
def main():
    DATA_DIR.mkdir(exist_ok=True)

    print("1. 收集商品清單...")
    slugs = list_product_slugs()
    print(f"   共 {len(slugs)} 個商品，開始逐一讀取...")
    products = []
    for n, slug in enumerate(slugs, 1):
        p = fetch_product(slug)
        if p:
            products.append(p)
        if n % 10 == 0:
            print(f"   已讀取 {n}/{len(slugs)}")
        time.sleep(0.3)  # 放慢一點，不要對網站造成負擔

    print("2. 讀取運費設定...")
    settings = fetch_settings()

    shop = {
        "_說明": f"從 {SITE} 同步的真實資料，同步時間 {time.strftime('%Y-%m-%d %H:%M')}。"
                "重新執行 scripts/sync_from_website.py 即可更新。",
        "shop": settings,
        "shipping": {"fee": settings["fee"], "free_shipping_threshold": settings["free_shipping_threshold"]},
        "products": products,
    }
    (DATA_DIR / "products.json").write_text(json.dumps(shop, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   已寫入 data/products.json（{len(products)} 個商品）")

    print("3. 讀取退換貨說明、服務條款...")
    faq = [
        f"# {settings['shop_name']} 店家規則",
        "",
        f"> 從 {SITE} 的公開頁面自動整理，同步時間 {time.strftime('%Y-%m-%d %H:%M')}。",
        "> 每一題用「## 」開頭，程式會依照 ## 切成一題一段。",
        "",
        "## 運費怎麼算？",
        f"運費 {settings['fee']} 元，單筆訂單滿 {settings['free_shipping_threshold']} 元免運費。"
        f"{settings['announcement']}",
        "",
        "## 怎麼聯絡客服？",
        f"請加入官方 LINE：{settings['line_id']}（{settings['line_url']}）。",
        "",
        # 這題是從服務條款「一、服務內容」整理的。實測發現：FAQ 沒有這題時，
        # 顧客問「有宅配嗎？」，模型會看到「運費 60 元」就自己推論成「有宅配」。
        "## 有宅配嗎？可以寄到家裡嗎？",
        "沒有宅配，不能寄到家裡。本店只透過統一超商「賣貨便」寄送到您指定的 7-11 門市，"
        "到門市取貨時再付款（見服務條款：一、服務內容）。下單時選擇想取貨的 7-11 門市即可。",
        "",
        policy_to_faq(fetch_policy_page("/returns"), "退換貨說明"),
        "",
        policy_to_faq(fetch_policy_page("/terms"), "服務條款"),
    ]
    (DATA_DIR / "faq.md").write_text("\n".join(faq) + "\n", encoding="utf-8")
    print("   已寫入 data/faq.md")

    print("4. 更新 7-11 門市清單...")
    # 門市清單來自代購網站專案（它用 scripts/fetch-711-stores.mjs 從 7-11 官方電子地圖抓的）。
    # 這台電腦有那個專案就複製最新的一份過來；沒有的話沿用 data/ 裡現有的。
    src = Path(r"D:\Project002\src\lib\data\stores-711.json")
    if src.exists():
        shutil.copyfile(src, DATA_DIR / "stores-711.json")
        n = len(json.loads(src.read_text(encoding="utf-8")))
        print(f"   已更新 data/stores-711.json（{n} 家門市）")
    else:
        print("   找不到代購網站專案，沿用現有的 data/stores-711.json")
    print("\n同步完成！")


if __name__ == "__main__":
    main()
