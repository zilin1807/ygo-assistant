"""多模态视觉识别 - 把游戏画面解析成结构化 JSON。

支持三种 Provider:
  · dashscope: 通义千问 qwen-vl-max
  · glm:       智谱 GLM-4V-Plus（OpenAI 兼容）
  · openai:    OpenAI 兼容协议（GPT-4o / 其他）
"""
from __future__ import annotations

import base64
import io
import json
import re
from typing import Any, Dict, Optional

from PIL import Image

from config import SETTINGS
from logger import log


# === 视觉抽取 Prompt：把画面翻译成 JSON ===
VISION_PROMPT = """你是一名资深的游戏王（Yu-Gi-Oh! Master Duel）玩家和 AI 视觉识别助手。
请观察截图中的游戏画面，输出严格的 JSON 描述当前局面。

字段说明：
- turn: 1=我方回合, 2=对方回合
- phase: "DP"|"SP"|"M1"|"BP"|"M2"|"EP"  (draw/stand/main1/battle/main2/end)
- my_lp, opp_lp: 数字 0-8000+
- my_hand_count: 我方手牌张数（不必识别具体卡名就标数）
- my_hand: ["卡名1", "卡名2"]    // 识别得到就填，识别不到留 []
- my_field: [{"name":"卡名","atk":2500,"def":2000,"position":"ATK|DEF|FACE-DOWN"}]
- opp_field: 同上
- my_grave: ["卡名"]
- opp_grave: ["卡名"]
- my_banished: ["卡名"]
- opp_banished: ["卡名"]
- notes: "额外观察（伏卡、连锁、覆盖等）"

严格按 JSON 输出；识别不到的信息用合理空值。不要任何额外解释。"""


def encode_image_for_llm(img: Image.Image, max_side: int = 1280, quality: int = 80) -> str:
    """压缩图片再 base64 编码，降低 token 消耗。"""
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / float(max(w, h))
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """LLM 偶尔会包一层 ```json ... ```，去掉再 parse。"""
    text = text.strip()
    # 去掉代码块包裹
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # 直接尝试
    try:
        return json.loads(text)
    except Exception:
        pass
    # 抓 JSON 子串
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


# ============ Provider 实现 ============

def _call_dashscope(image_b64: str) -> str:
    import dashscope
    from dashscope import MultiModalConversation

    dashscope.api_key = SETTINGS.dashscope_api_key
    messages = [
        {
            "role": "user",
            "content": [
                {"image": f"data:image/jpeg;base64,{image_b64}"},
                {"text": VISION_PROMPT},
            ],
        }
    ]
    # 按百炼控制台实际开通的视觉模型名调用
    resp = MultiModalConversation.call(
        model="qwen-vl-ocr-2025-11-20",
        messages=messages,
        result_format="message",
    )
    if getattr(resp, "status_code", 200) != 200:
        raise RuntimeError(f"qwen-vl-max 调用失败: {getattr(resp, 'message', resp)}")
    # 取出 text
    return resp.output.choices[0].message.content[0]["text"]


def _call_glm(image_b64: str) -> str:
    from openai import OpenAI

    client = OpenAI(
        api_key=SETTINGS.glm_api_key,
        base_url="https://open.bigmodel.cn/api/paas/v4",
    )
    resp = client.chat.completions.create(
        model="glm-4v-plus",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    {"type": "text", "text": VISION_PROMPT},
                ],
            }
        ],
    )
    return resp.choices[0].message.content


def _call_openai(image_b64: str) -> str:
    from openai import OpenAI

    client = OpenAI(
        api_key=SETTINGS.openai_api_key,
        base_url=SETTINGS.openai_base_url,
    )
    model = SETTINGS.openai_model if hasattr(SETTINGS, "openai_model") else "gpt-4o"
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    {"type": "text", "text": VISION_PROMPT},
                ],
            }
        ],
    )
    return resp.choices[0].message.content


def _call(image_b64: str) -> str:
    p = SETTINGS.llm_provider
    if p == "dashscope":
        return _call_dashscope(image_b64)
    if p == "glm":
        return _call_glm(image_b64)
    if p == "openai":
        return _call_openai(image_b64)
    raise RuntimeError(f"未知 LLM_PROVIDER: {p}")


def analyze_frame(image: Image.Image) -> Optional[Dict[str, Any]]:
    """入口：拿一帧图，返回结构化局面 JSON；失败返回 None。"""
    if not image:
        return None
    image_b64 = encode_image_for_llm(image)
    try:
        raw = _call(image_b64)
    except Exception as e:
        log.error("视觉 LLM 调用失败：%s", e)
        return None
    parsed = _extract_json(raw)
    if parsed is None:
        log.warning("无法解析 LLM 返回：%s", raw[:200])
    return parsed
