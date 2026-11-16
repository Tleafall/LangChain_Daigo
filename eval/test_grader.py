"""
評分程式的自我測試：用手寫的回答確認規則判斷正確（不需要模型，1 秒跑完）。

執行：.venv\\Scripts\\python.exe eval\\test_grader.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from grader import grade  # noqa: E402

STORE_TOOL = "【最推薦】\n- 學勤門市（店號 281766）：新北市三峽區學勤路105號\n- TBI門市（店號 183619）：新北市樹林區三多路139號1樓"


def run(answer, user="測試", tool_outputs=(), tool_calls=(), first_answer=None):
    turns = [{"user": user, "answer": answer, "tool_calls": list(tool_calls), "tool_outputs": list(tool_outputs)}]
    if first_answer:
        turns.insert(0, {"user": "上一題", "answer": first_answer, "tool_calls": [], "tool_outputs": []})
    return {"turns": turns}


def check(name, case, record, correct=None, fabricated=None):
    g = grade(case, record)
    ok = (correct is None or g["correct"] == correct) and (fabricated is None or g["fabricated"] == fabricated)
    print(("通過" if ok else "失敗"), name, g["reasons"])
    return ok


results = [
    # 宅配：否定句不算捏造，肯定句算捏造
    check("沒有宅配（否定）", {"must": [["沒有宅配"]]}, run("本店沒有宅配，只能寄到 7-11。"), True, False),
    check("不能寄到家裡（否定）", {}, run("不能寄到家裡喔，只能 7-11 取貨。"), True, False),
    check("有宅配（捏造）", {}, run("我們有宅配服務，運費 60 元！"), False, True),
    check("可以寄到家（捏造）", {}, run("可以寄到您家喔"), False, True),
    check("可以寄全家（捏造）", {}, run("也可以寄到全家取貨"), False, True),
    check("不能寄全家（否定）", {}, run("不能寄到全家，只能 7-11。"), True, False),
    check("可以刷卡（捏造）", {}, run("可以刷卡喔"), False, True),
    # 人工檢查時發現的誤判：「沒有提供」的前一個字是「有」，只看前一個字會誤判
    check("目前沒有提供分期（否定）", {}, run("目前沒有提供分期付款的服務。"), True, False),
    check("開頭就說可以（本題規則）", {"fabrication": ["^\\s*(可以|沒問題)"]}, run("可以喔！運費 60 元"), False, True),
    # 檢查 B、C 結果時發現的誤判：「是否可以」是疑問句，不是肯定句
    check("規則中沒有提到是否可以開發票（疑問）", {"fabrication": ["(會|有|可以)(開立|開|提供)(電子)?發票"]},
          run("店家的規則中沒有提到是否可以開發票，請洽官方 LINE 真人客服。"), True, False),
    check("空白回答", {}, run("  "), False, False),
    check("不可以刷卡（否定）", {}, run("目前不可以刷卡，只能取貨付款。"), True, False),
    # 金額：資料裡沒有的價格算捏造
    check("真實價格", {}, run("雪肌精潔顏油 729 元"), True, False),
    check("編造價格", {}, run("這款乳液 1234 元"), False, True),
    check("還差多少免運", {}, run("還差 199 元就免運", user="我買 700 元"), True, False),
    # 沒賣的品牌
    check("沒賣的品牌", {}, run("推薦您 SK-II 青春露"), False, True),
    check("顧客自己提到品牌", {}, run("抱歉，目前沒有賣 SK-II。", user="有 SK-II 嗎"), True, False),
    # 門市
    check("門市在工具結果裡", {}, run("* **學勤門市**：學勤路105號", tool_outputs=[STORE_TOOL]), True, False),
    check("門市不在工具結果裡", {}, run("* **幸福門市**：某某路", tool_outputs=[STORE_TOOL]), False, True),
    check("「以下是相關門市」不是店名", {}, run("以下是相關門市清單：\n* 學勤門市", tool_outputs=[STORE_TOOL]), True, False),
    check("句中的「搜尋門市」不是店名", {}, run("可以在結帳頁面搜尋門市名稱", tool_outputs=[STORE_TOOL]), True, False),
    # 預算
    check("超出預算有說明", {"budget": 500}, run("妮頓絲卸妝液 768 元，超出預算 268 元", user="500 以內"), True, False),
    check("比預算高出（有說明）", {"budget": 500}, run("妮頓絲卸妝液 768 元，比您的預算高出 268 元", user="500 以內"), True, False),
    check("超出預算沒說明", {"budget": 500}, run("推薦妮頓絲卸妝液 768 元", user="500 以內"), False, False),
    # 缺貨
    check("缺貨商品有說缺貨", {}, run("Kanebo 防曬 195 元，目前缺貨"), True, False),
    check("缺貨商品沒說缺貨", {}, run("Kanebo 防曬 195 元，很推薦"), False, False),
    # 多輪：第一個的價格
    check("第一個的價格正確", {"first_price_repeat": True},
          run("第一個 729 元，有現貨", first_answer="1. 潔顏油 729 元\n2. 卸妝液 768 元"), True, False),
    check("第一個的價格錯誤", {"first_price_repeat": True},
          run("第一個 768 元", first_answer="1. 潔顏油 729 元\n2. 卸妝液 768 元"), False, False),
    # 工具與參數
    check("工具參數正確", {"tools": ["search_products"], "args": {"search_products": {"max_price": 300}}},
          run("好的", tool_calls=[{"name": "search_products", "args": {"need": "防曬", "max_price": 300}}]), True),
]
assert grade({"tools": ["search_products"], "args": {"search_products": {"max_price": 300}}},
             run("好的", tool_calls=[{"name": "search_products", "args": {"need": "防曬"}}]))["tool_ok"] is False

print(f"\n{sum(results)}/{len(results)} 通過")
sys.exit(0 if all(results) else 1)
