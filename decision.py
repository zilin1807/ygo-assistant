"""决策推理 - 综合「当前局面 + 历史决策 + 用户风格」给出推荐。

同样支持三种 Provider，但用文本模型即可（便宜且够用）。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from config import SETTINGS
from logger import log


DECISION_SYSTEM_PROMPT = """你是用户的游戏王对战私人助理。
你必须：
1. 综合当前局面 + 历史相似场面 + 用户过往偏好
2. 给出 2-3 个候选操作，按"推荐度"排序
3. 简洁中文，每条理由一句话（<= 25 字）
4. 严格输出 JSON，不要任何额外文本

JSON 字段：
{
  "summary": "一句话当前局面摘要",
  "urgent": "有时效性的建议，否则空字符串",
  "options": [
    {"idx": 0, "action": "操作描述", "reason": "为什么这样做"},
    {"idx": 1, "action": "...", "reason": "..."}
  ]
}
"""


def _format_memory(stats: Dict[str, Any], similar: List[Dict[str, Any]]) -> str:
    if stats.get("total", 0) == 0:
        return "（暂无历史决策可参考）"
    parts = []
    parts.append(
        f"【用户风格画像】共记录 {stats['total']} 次决策，采纳率 {stats['rate']:.0%}"
    )
    if similar:
        parts.append("【相似场面历史】")
        for r in similar[: SETTINGS.memory_top_k]:
            try:
                gs = json.loads(r["game_state_json"])
                sugs = json.loads(r["suggestions_json"])
            except Exception:
                continue
            chosen = r["chosen_idx"]
            if 0 <= chosen < len(sugs):
                pick = sugs[chosen].get("action", "")
            else:
                pick = "（忽略）"
            parts.append(
                f"  - 回合{gs.get('turn')} 阶段{gs.get('phase')} LP={gs.get('my_lp')}/{gs.get('opp_lp')} → 用户选择：{pick}"
            )
    return "\n".join(parts)


def build_user_prompt(game_state: Dict[str, Any], memory_text: str) -> str:
    state_text = json.dumps(game_state, ensure_ascii=False, indent=2)
    return f"""当前局面：
{state_text}

{memory_text}

请按要求输出 JSON。"""


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


# ===== Provider 文本模型调用 =====

def _call_dashscope_text(messages: List[Dict[str, Any]]) -> str:
    import dashscope
    from dashscope import Generation

    dashscope.api_key = SETTINGS.dashscope_api_key
    resp = Generation.call(
        model="qwen-max",  # 用户实际开通的文本旗舰模型
        messages=messages,
        result_format="message",
    )
    if getattr(resp, "status_code", 200) != 200:
        raise RuntimeError(f"qwen-plus 调用失败: {getattr(resp, 'message', resp)}")
    return resp.output.choices[0].message.content


def _call_openai_compat(messages: List[Dict[str, Any]], base_url: str, api_key: str, model: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url)
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.4,
    )
    return resp.choices[0].message.content


def _call_text(messages: List[Dict[str, Any]]) -> str:
    p = SETTINGS.llm_provider
    if p == "dashscope":
        return _call_dashscope_text(messages)
    if p == "glm":
        return _call_openai_compat(
            messages, "https://open.bigmodel.cn/api/paas/v4", SETTINGS.glm_api_key, "glm-4-plus"
        )
    if p == "openai":
        return _call_openai_compat(
            messages, SETTINGS.openai_base_url, SETTINGS.openai_api_key, "gpt-4o-mini"
        )
    raise RuntimeError(f"未知 LLM_PROVIDER: {p}")


def reason(
    game_state: Dict[str, Any],
    memory_stats: Dict[str, Any],
    similar_history: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """入口：返回 {"summary", "urgent", "options":[...]} 或 None。"""
    memory_text = _format_memory(memory_stats, similar_history)
    user_prompt = build_user_prompt(game_state, memory_text)
    messages = [
        {"role": "system", "content": DECISION_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    try:
        raw = _call_text(messages)
    except Exception as e:
        log.error("决策 LLM 调用失败：%s", e)
        return None
    parsed = _extract_json(raw)
    if parsed is None:
        log.warning("无法解析决策结果：%s", raw[:200])
    return parsed
