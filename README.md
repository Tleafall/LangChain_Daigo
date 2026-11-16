# LangChain × Gemma 4 代購客服機器人（教學專案）

用**完全免費**的本機模型 Gemma 4，一步一步學會 LangChain，最後做出一個會查 FAQ、會推薦商品、會查價格庫存、會記得對話的客服機器人。

整套都在自己電腦上跑：不用付 API 費用，資料也不會傳到網路上。

---

## 這個專案適合誰

- 想學 LangChain、但不想先花錢買 API 的人
- 要教別人 LangChain 的講師（每一步都有詳細說明和教學建議）
- 會一點點 Python 就可以；完全沒學過也能看懂觀念

---

## 資料夾結構

```
LangChain_Daigo/
├── README.md              ← 你正在看的這份：總覽
├── requirements.txt       ← 要安裝的 Python 套件清單
├── setup.ps1              ← 一鍵安裝腳本（給學員用）
├── start.bat              ← 雙擊開啟主選單（推薦）
├── run_chat.bat           ← 雙擊直接開始聊天
├── run_demo.bat           ← 雙擊跑示範問題
├── sync_data.bat          ← 雙擊同步網站最新資料
│
├── docs/                  ← 教學文件
│   ├── 01_安裝教學.md      ← 從零開始安裝 Ollama、Gemma 4、Python 環境
│   ├── 02_程式說明.md      ← 每一支範例程式在做什麼、一段一段解釋
│   └── 03_教學建議.md      ← 給講師：課程安排、示範重點、練習題、常見問題
│
├── data/                  ← 從上線網站同步的真實資料
│   ├── faq.md             ← 店家規則（網站的退換貨說明、服務條款）
│   ├── products.json      ← 63 個商品、各規格價格與庫存、運費設定
│   └── stores-711.json    ← 全台 7,380 家 7-11 門市（找取貨門市用）
│
├── scripts/
│   ├── sync_from_website.py ← 從 yuchingmakeup.com 同步最新的商品和規則
│   └── menu.ps1             ← 主選單（start.bat 會呼叫它）
│
├── eval/                  ← 評估：48 題測試集、評分程式、結果報告
│   ├── cases.jsonl        ← 測試題與判斷規則
│   ├── grader.py          ← 評分規則（全部用程式判斷）
│   ├── test_grader.py     ← 評分規則的自我測試
│   ├── variants.py        ← 要比較的三種設定（早期版／只加規則／目前版）
│   ├── run_eval.py        ← 一鍵執行
│   ├── results/           ← 每一題的原始紀錄和結果表
│   └── REPORT.md          ← 評估報告
│
└── src/                   ← 範例程式，照編號順序學
    ├── config.py          ← 共用設定：模型名稱都在這裡改
    ├── step1_hello.py     ← 步驟 1：跟 AI 說第一句話
    ├── step2_chain.py     ← 步驟 2：模板 + 管線
    ├── step3_tool_test.py ← 步驟 3：測試模型會不會用工具
    ├── step4_rag_faq.py   ← 步驟 4：RAG，先查 FAQ 再回答
    ├── knowledge.py       ← 步驟 5 用的知識庫模組
    └── step5_agent.py     ← 步驟 5：完整的客服 Agent
```

---

## 快速開始（已經裝好環境的話）

**最簡單：雙擊檔案**

| 檔案 | 做什麼 |
| --- | --- |
| **`start.bat`** | **主選單**：聊天、示範、同步資料、教學步驟都可以從這裡選 |
| `run_chat.bat` | 直接開始跟客服聊天 |
| `run_demo.bat` | 自動跑一輪示範問題，不用打字 |
| `sync_data.bat` | 從網站同步最新的商品和規則 |

這幾個檔案都會先檢查 Ollama 有沒有在執行，沒有的話會自動幫你打開。

> 小知識：`.bat` 檔裡面只寫英文，中文選單放在 `scripts\menu.ps1`（存成 UTF-8 BOM）。因為 Windows 的 cmd 讀取 `.bat` 裡的中文常常會亂碼，甚至讓指令被跳過。

**用 PowerShell 一步一步跑**：在專案資料夾打開 PowerShell，依序執行：

```powershell
# 1. 啟動虛擬環境（每次開新的終端機都要做一次）
.\.venv\Scripts\Activate.ps1

# 2. 照順序跑範例
python src\step1_hello.py
python src\step2_chain.py
python src\step3_tool_test.py
python src\step4_rag_faq.py
python src\step5_agent.py --demo   # 自動示範
python src\step5_agent.py          # 自己跟客服聊天
```

還沒安裝的話，請先看 [docs/01_安裝教學.md](docs/01_安裝教學.md)。

---

## 五個步驟在學什麼

| 步驟 | 程式 | 學到的觀念 | 對應手冊章節 |
| --- | --- | --- | --- |
| 1 | `step1_hello.py` | 建立模型、`invoke` 發問、`.content` 拿答案、三種訊息角色 | 第 3 章 |
| 2 | `step2_chain.py` | 模板填空、`\|` 管線、`StrOutputParser` | 第 4 章 |
| 3 | `step3_tool_test.py` | `@tool`、docstring 的重要性、`create_agent`、看 Agent 每一步 | 第 6 章 |
| 4 | `step4_rag_faq.py` | 切段、Embeddings、向量資料庫、餘弦相似度、RAG Chain 的字典 | 第 8 章 |
| 5 | `step5_agent.py` | 多個工具、兩個知識庫、混合搜尋、相似度門檻、記憶 | 第 6～8 章 |

每一步的詳細解說在 [docs/02_程式說明.md](docs/02_程式說明.md)。

---

## 使用的技術

| 元件 | 用什麼 | 費用 |
| --- | --- | --- |
| 語言模型（AI 的大腦） | Gemma 4 E4B，透過 Ollama 在本機執行 | 免費 |
| 框架 | LangChain 1.x | 免費 |
| Embeddings（轉成向量） | `paraphrase-multilingual-mpnet-base-v2`（支援中文） | 免費 |
| 向量資料庫 | `InMemoryVectorStore`（程式關掉就消失，練習用） | 免費 |

---

## 想換模型怎麼辦？

只要改 [src/config.py](src/config.py) 裡的 `MODEL_NAME`，其他程式都不用動。例如：

```python
MODEL_NAME = "gemma4:e2b"   # 更小、更快，但比較容易用錯工具
MODEL_NAME = "gemma4:12b"   # 比較聰明，但需要更多記憶體、更慢
```

換之前要先下載：`ollama pull gemma4:e2b`

---

## 重要提醒

1. **資料是從上線網站同步的真實資料。** 商品上下架、改價格或庫存以後，執行下面這行重新同步，再重新啟動客服就會生效：

   ```powershell
   .\.venv\Scripts\python.exe scripts\sync_from_website.py
   ```

   同步只讀取網站上任何人都看得到的公開頁面（商品頁、退換貨說明、服務條款），不需要密碼，也不會碰會員、訂單等客戶資料。
2. **本機小模型偶爾會出錯。** 例如沒有用工具就自己回答、中文怪怪的。這是模型能力的限制，不一定是程式寫錯。
3. **預設只用 CPU 跑**（`config.py` 的 `USE_GPU = False`）。AMD 顯卡在 Windows 上實測會讓 Ollama 當掉，所以預設關掉 GPU。有 NVIDIA 顯卡的話可以改成 `True` 加速。
4. **CPU 速度參考**（AMD Ryzen 筆電、16GB 記憶體）：模型第一次載入約 15 秒，之後簡單問答約 2～5 秒，Agent 每題約 10～20 秒。

---

## 評估：客服答得對不對、會不會亂編

`eval/` 裡有一套可以重跑的評估：48 題測試（商品推薦、店家規則、7-11 門市、規則外的問題、多輪追問），用程式自動評分，算出**答對率、捏造率、工具正確率、回答時間**，並比較三種設定：

| 設定 | 內容 |
| --- | --- |
| `A_early` | 早期版：修正「編造宅配」之前的 prompt 和工具 |
| `B_rules` | A ＋ FAQ 補上宅配題 ＋ prompt 防捏造規則 |
| `C_current` | B ＋ 程式保證（預算過濾、去重複、門市分組），也就是目前的 `step5_agent.py` |

結果（各 48 題 × 3 次，gemma4:e4b、CPU）：

| 設定 | 答對率 | 偵測到的捏造 |
| --- | --- | --- |
| `A_early` | 78.5% | 5/144 筆（3 題） |
| `B_rules` | 85.4% | 0/144 |
| `C_current` | 85.4% | 0/144 |

- **A → B：** 原本會編造宅配、說可以寄全家的題目，加上規則後都答對了。但以題目為單位做配對檢定，答對率差距（+6.9pp，95% 信賴區間 −2.8～+17.4）並不顯著。
- **B → C：** 程式邏輯的修改讓空白回答從 4 筆降到 1 筆，整體答對率沒有差別。
- **代價：** 規則加多以後，商品推薦類從 90% 降到 70%，例如問洗髮精時會先反問，而不是直接查商品。
- **現有問題：** 目前版本仍會在「顧客講錯行政區」時漏列最符合的門市。
- **讀數字時要注意：** 「0 筆捏造」只代表評分規則沒抓到，偵測器的漏抓率還沒量過；評分規則也在看過結果後修改過。

細節、失敗案例和限制都寫在 [eval/REPORT.md](eval/REPORT.md)。

**怎麼跑**（要先開著 Ollama）：

```powershell
# 評分規則的自我測試（不需要模型，1 秒）
.\.venv\Scripts\python.exe eval\test_grader.py

# 目前版跑一次（48 題，CPU 約 15 分鐘）
.\.venv\Scripts\python.exe eval\run_eval.py

# 報告裡的完整比較：三種設定 × 3 個 seed（CPU 約 2～3 小時，中斷後重跑會接著跑）
.\.venv\Scripts\python.exe eval\run_eval.py --variants all --repeats 3

# 不呼叫模型，只用存好的回答重新評分（改了評分規則時用）
.\.venv\Scripts\python.exe eval\run_eval.py --regrade
```

每次評估都固定 seed（第 1、2、3 次分別用 seed 1、2、3），同一台電腦重跑會得到一樣的回答。結果表在 `eval/results/summary.md`，每一題的完整紀錄（回答、呼叫的工具、工具回傳）在 `eval/results/raw/`。

> 記憶體只有 16GB 時，Ollama 已經載入模型的情況下建立向量庫可能會記憶體不足。先執行 `ollama stop gemma4:e4b` 再跑評估即可（第一題會自動重新載入模型）。

---

## 關於資料與隱私

- `data/` 是從上線網站同步的**公開資料**（商品、店家規則、7-11 門市），不含任何會員、訂單或顧客資料。
- 開發時曾用真實的顧客提問測試過。公開前已檢查整個專案：文件和測試集裡**沒有顧客的對話內容或個資**；文件裡原本有一個寫到巷弄樓層的完整地址（可能來自真實對話），已換成虛構地址。測試集 `eval/cases.jsonl` 的題目都是重新寫的虛構提問；其中幾題參考了開發時遇到的情境（例如問宅配、地址的行政區講錯），地址只寫到路名，不含門牌。

---

## 測試紀錄

本專案已在下列環境實際跑過全部五個步驟：

| 項目 | 版本 |
| --- | --- |
| 電腦 | MSI Alpha 15（AMD Ryzen + RX 5600M），16GB 記憶體，Windows 10 |
| Ollama | 0.40.15 |
| 模型 | gemma4:e4b（6.6GB），CPU 模式 |
| Python | 3.11.9 |
| LangChain | langchain 1.4.9、langchain-ollama 1.1.0 |

開發過程踩到的六個坑（GPU 當掉、客服只說不做、「第一個」查錯商品、不管預算還編造商品、換真實資料後搜不到商品、編出不存在的宅配服務）和解法，都寫在 [docs/03_教學建議.md](docs/03_教學建議.md) 的「實測踩雷紀錄」，很適合拿來上課討論。
