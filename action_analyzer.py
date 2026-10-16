"""操作推断器 — 通过对比前后两帧判断用户做了什么。

策略：
  · 优先：把前后两张图都喂给 qwen-vl-ocr，让它直接看出视觉差异
  · fallback：如果图不清晰，只用状态 JSON，让 qwen-max 推断
  · 输出严格的 JSON：{"action": "用<卡>做<事>", "reason": "依据", "confidence": 0-1}
"""
from __future__ import annotations

import base64
import io
import json
from typing import Any, Dict, Optional, Tuple

from PIL import Image

from config import SETTINGS
from logger import log


INFER_SYSTEM = """你是 Yu-Gi-Oh (Master Duel) 的对战观察 AI。
会给你两幅截图或两份状态 JSON，分别对应【操作前】与【操作后】。
请你推断这段时间（1-3 秒）用户做了什么操作：

- "用手中的<XXX卡>做<XXX事>"：发动效果 / 攻击 / 召唤 / set / 抽牌 / 移动阶段 / 通招 / 翻转
- 描述保持中文、≤30 字
- 给出依据（哪个字段变了）+ 置信度 0-1

严格按 JSON 输出（不要任何其他文字）：
{"action":"...", "reason":"...", "confidence":0.0~1.0}
"""


def _img_to_data_url(img: Image.Image) -> str:
    w, h = img.size
    if max(w, h) > 1024:
        scale = 1024 / float(max(w, h))
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _extract_json(text: str) -> Optional[dict]:
    text = text.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    import re
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def _call_with_images(img_before: Image.Image, img_after: Image.Image) -> Optional[str]:
    """调 qwen-vl-ocr 看两图。"""
    try:
        import dashscope
        from dashscope import MultiModalConversation

        dashscope.api_key = SETTINGS.dashscope_api_key
        resp = MultiModalConversation.call(
            model="qwen-vl-ocr-2025-11-20",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"image": _img_to_data_url(img_before)},
                        {"image": _img_to_data_url(img_after)},
                        {"text": "上面两图是游戏王对战同一桌面的前后两帧（约 1-3 秒间隔）。"
                                 "请仔细对比两图差异，推断这段时间用户做了什么操作。"
                                 "严格按 JSON 输出：{\"action\":\"...\",\"reason\":\"...\",\"confidence\":0~1}"
                        },
                    ],
                }
            ],
            result_format="message",
            timeout=10,
        )
        if getattr(resp, "status_code", 200) != 200:
            return None
        return resp.output.choices[0].message.content[0]["text"]
    except Exception as e:
        log.debug("vision 双图推断失败：%s", e)
        return None


def _call_with_states(s_before: dict, s_after: dict) -> Optional[str]:
    """fallback：调 qwen-max 看 JSON。"""
    try:
        import dashscope
        from dashscope import Generation

        dashscope.api_key = SETTINGS.dashscope_api_key
        user_prompt = (
            "【操作前】\n" + json.dumps(s_before, ensure_ascii=False, indent=2) +
            "\n\n【操作后】\n" + json.dumps(s_after, ensure_ascii=False, indent=2) +
            "\n\n请推断这段时间发生了什么操作。"
            "严格按 JSON 输出。"
        )
        resp = Generation.call(
            model="qwen-max",
            messages=[
                {"role": "system", "content": INFER_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            result_format="message",
            timeout=10,
        )
        if getattr(resp, "status_code", 200) != 200:
            return None
        return resp.output.choices[0].message.content
    except Exception as e:
        log.debug("text 推断失败：%s", e)
        return None


def infer(
    state_before: dict,
    state_after: dict,
    img_before: Optional[Image.Image] = None,
    img_after: Optional[Image.Image] = None,
) -> Dict[str, Any]:
    """主入口。返回 {"action": str, "reason": str, "confidence": float}。

    失败时返回 action="未能推断"。
    """
    if not SETTINGS.dashscope_api_key:
        return {"action": "(无 API Key)", "reason": "未配置 DASHSCOPE_API_KEY", "confidence": 0.0}

    # 优先：双图推断
    raw = None
    if img_before is not None and img_after is not None:
        raw = _call_with_images(img_before, img_after)
    if not raw:
        raw = _call_with_states(state_before, state_after)

    if not raw:
        return {"action": "未能推断", "reason": "LLM 调用失败", "confidence": 0.0}

    parsed = _extract_json(raw)
    if parsed:
        return {
            "action": str(parsed.get("action", "未知"))[:35],
            "reason": str(parsed.get("reason", ""))[:80],
            "confidence": float(parsed.get("confidence", 0.0) or 0.0),
        }
    return {"action": raw[:30] or "未能解析", "reason": "", "confidence": 0.0}


def diff_key(state_before: dict, state_after: dict) -> Tuple[str, ...]:
    """返回发生变化的字段名（lp/turn/field/hand），用于诊断。"""
    changed = []
    for k in ("my_lp", "opp_lp", "turn", "phase",
              "my_hand_count", "my_field", "opp_field",
              "my_grave", "opp_grave"):
        if state_before.get(k) != state_after.get(k):
            changed.append(k)
    return tuple(changed)
