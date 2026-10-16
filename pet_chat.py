"""桌宠闲聊 LLM 生成。

轻量 prompt + 极速模型（qwen-turbo），用于偶尔飘一句话。
失败 fallback 到内置静态短句。
"""
from __future__ import annotations

import random
import time
from typing import Optional

from config import SETTINGS
from logger import log

# 内置 fallback 短句（API 失败时用）
STATIC_LINES = [
    "要打牌吗？",
    "今天手感应该不错 ✨",
    "...",
    "☕ 摸鱼中",
    "想看魔法禁书目录吗",
    "你觉得这副牌几几开？",
    "我没在偷看你屏幕",
    "摸 — 抽牌！",
    "(´・ω・`)",
    "MD 启动一下呗",
    "这副牌我熟",
    "ECT（?）",
]


CHITCHAT_SYSTEM = """你扮演一只桌面宠物小猫，戴着耳机、闭眼笑的赛博风格。
正在陪主人等《游戏王 Master Duel》。你有时有点懒、有时吐槽主人不陪你玩。

每次只说一句简短的回复：
- 中文，10-22 字之间
- 语气要活泼、像小猫撒娇、带点后缀（"喵""~""(´・ω・`)""..."等）
- 不要换行
- 不主动问用户问题
- 偶尔吐槽下主人最近决策偏好（如果 user 提示给了）

只输出那一句话本身，不要引号、不要解释、不要 Q&A 风格。"""


def _call_llm_chitchat(prev: Optional[str] = None) -> Optional[str]:
    """调用 LLM 生成一句。失败返回 None。

    优先 qwen-max（用户已开通的旗舰文本模型）。
    如果以后他开通了 qwen-flash，会自动切到更便宜的。
    """
    if not SETTINGS.dashscope_api_key:
        return None
    # 候选模型：角色扮演特化版优先，其次轻量 chat
    candidates = ["qwen-flash-character-2026-02-26", "qwen-flash", "qwen-turbo", "qwen-max"]
    try:
        import dashscope
        from dashscope import Generation
        dashscope.api_key = SETTINGS.dashscope_api_key

        user_msg = "说一句新的话。"
        if prev:
            user_msg += f"上一句说过：'{prev}'，换换风格。"

        for model in candidates:
            try:
                resp = Generation.call(
                    model=model,
                    messages=[
                        {"role": "system", "content": CHITCHAT_SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                    result_format="message",
                    timeout=4,
                )
            except Exception:
                continue
            if getattr(resp, "status_code", 200) != 200:
                continue
            text = (resp.output.choices[0].message.content or "").strip()
            text = text.replace('"', '').replace("'", '').replace('\n', ' ').strip()
            if not text:
                continue
            if len(text) > 28:
                text = text[:28].rstrip("，、。 ") + "…"
            log.debug("chitchat via %s -> %s", model, text)
            return text
        return None
    except Exception as e:
        log.debug("chitchat LLM 全部失败：%s", e)
        return None


def next_line(prev: Optional[str] = None) -> str:
    """返回桌宠下一句。优先 LLM（如果配置），失败回静态。"""
    if SETTINGS.chitchat_mode == "llm":
        t0 = time.time()
        line = _call_llm_chitchat(prev)
        if line:
            log.debug("chitchat LLM %.2fs -> %s", time.time() - t0, line)
            return line
        # fallback
        log.debug("chitchat LLM 失败，使用静态")
    return random.choice(STATIC_LINES)
