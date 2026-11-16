"""
共用設定檔：所有範例程式都從這裡拿模型。

想換模型時，只要改這個檔案，其他程式都不用動。
"""

import sys

from langchain_ollama import ChatOllama

# Windows 終端機預設編碼可能不是 UTF-8，中文會變亂碼，這行讓輸出固定用 UTF-8
sys.stdout.reconfigure(encoding="utf-8")

# 使用的模型名稱（要先用 `ollama pull gemma4:e4b` 下載）
MODEL_NAME = "gemma4:e4b"

# 把文字轉成向量用的模型（第一次執行會自動下載，約 1GB）
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"

# 要不要用顯示卡（GPU）跑模型
#   False：只用 CPU。比較慢，但每台電腦都能跑。AMD 顯卡在 Windows 上常常會出錯，建議用這個。
#   True ：讓 Ollama 自己決定要不要用 GPU。有 NVIDIA 顯卡的電腦改成 True 會快很多。
USE_GPU = False


def get_model(temperature: float = 0.2, seed: int | None = None) -> ChatOllama:
    """建立一個 Gemma 4 模型物件。

    temperature：越低回答越穩定、越高越有創意。客服用低一點比較好。
    seed：隨機種子。評估時固定它，同一台電腦重跑會得到一樣的回答；平常聊天不用填。
    reasoning=False：關掉「思考模式」，回答比較快。在只有 CPU 的電腦上差很多。
    num_gpu=0：模型的 0 層放到 GPU 上，也就是全部用 CPU 跑。
    """
    return ChatOllama(
        model=MODEL_NAME,
        temperature=temperature,
        reasoning=False,
        num_gpu=None if USE_GPU else 0,
        seed=seed,
    )
