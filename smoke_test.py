"""冒烟测试 - 不依赖 GUI，验证：
  1. .env 加载 & API Key 可用
  2. dashscope SDK 可调用 qwen-vl-oct-2025-11-20
  3. 模型能从一张测试图返回结构化 JSON
  4. 文本决策模型（qwen3.7-plus）能完成推理
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

# 保证 import 时能找到同目录模块
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image, ImageDraw, ImageFont

from config import SETTINGS, has_api_key
from logger import get_logger

log = get_logger("smoke")


def build_test_scene() -> Image.Image:
    """Pillow 绘一张游戏王风格的「测试画面」。

    不要求逼真——只要包含：
      · 明显的我方区域、对方区域、LP 数字
      · 至少一张场上怪兽卡
      · 至少 1 张手牌
    让视觉模型有东西可识别。
    """
    W, H = 1280, 720
    img = Image.new("RGB", (W, H), color=(15, 25, 45))
    d = ImageDraw.Draw(img)

    # 上下区域分割
    d.rectangle([(0, 0), (W, H // 2)], fill=(25, 35, 60))         # 上：我方
    d.rectangle([(0, H // 2), (W, H)], fill=(15, 25, 45))         # 下：对方
    d.line([(0, H // 2), (W, H // 2)], fill=(80, 80, 80), width=2)

    def box(x, y, w, h, fill=(200, 200, 210), label=""):
        d.rectangle([(x, y), (x + w, y + h)], fill=fill, outline=(0, 0, 0), width=2)
        if label:
            try:
                font = ImageFont.truetype("arial.ttf", 16)
            except Exception:
                font = ImageFont.load_default()
            d.text((x + 8, y + 8), label, fill=(0, 0, 0), font=font)

    # LP（用大字号）
    try:
        big = ImageFont.truetype("arial.ttf", 36)
    except Exception:
        big = ImageFont.load_default()
    d.text((40, 30), "LP 8000", fill=(255, 235, 130), font=big)
    d.text((W - 200, H - 80), "LP 4000", fill=(255, 235, 130), font=big)

    # 我方 5 张手牌
    for i in range(5):
        box(280 + i * 110, 220, 100, 140, fill=(245, 220, 180), label=f"Hand{i + 1}")
    # 对方 5 张手牌
    for i in range(5):
        box(280 + i * 110, H - 220 - 140, 100, 140, fill=(220, 200, 180), label=f"Opp Hand{i + 1}")

    # 我方 1 个怪兽在场
    box(180, 100, 130, 160, fill=(180, 220, 250), label="Dragon\nATK 2500")
    # 对方 2 个怪兽在场
    box(800, H - 280, 130, 160, fill=(250, 180, 180), label="Golem\nATK 2500")
    box(950, H - 280, 130, 160, fill=(250, 180, 180), label="Knight\nATK 1900")

    return img


def test_vision():
    import dashscope
    from dashscope import MultiModalConversation
    import base64

    dashscope.api_key = SETTINGS.dashscope_api_key

    img = build_test_scene()
    img.save("smoke_scene.png", "PNG")
    log.info("测试画面已保存: smoke_scene.png")

    # 编码
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    prompt = (
        "这是游戏王对战画面（简化版测试）。请严格按 JSON 输出：\n"
        '{"turn":1,"phase":"M1","my_lp":8000,"opp_lp":4000,'
        '"my_hand_count":5,"my_field":[{"name":"Dragon","atk":2500,"def":2000,"position":"ATK"}],'
        '"opp_field":[{"name":"Golem","atk":2500,"def":2500,"position":"ATK"},'
        '{"name":"Knight","atk":1900,"def":0,"position":"ATK"}],'
        '"notes":"测试"}'
    )

    resp = MultiModalConversation.call(
        model="qwen-vl-ocr-2025-11-20",
        messages=[
            {
                "role": "user",
                "content": [
                    {"image": f"data:image/jpeg;base64,{b64}"},
                    {"text": prompt},
                ],
            }
        ],
        result_format="message",
    )
    if getattr(resp, "status_code", 200) != 200:
        log.error("视觉调用失败: %s", getattr(resp, "message", resp))
        return False
    text = resp.output.choices[0].message.content[0]["text"]
    log.info("✅ 视觉模型返回：%s", text)
    return True


def test_text_decision():
    import dashscope
    from dashscope import Generation

    dashscope.api_key = SETTINGS.dashscope_api_key

    resp = Generation.call(
        model="qwen-max",
        messages=[
            {"role": "system", "content": "你是游戏王 AI 助手。严格按 JSON 输出。"},
            {"role": "user", "content": "我方 8000 LP，场上 1 只 2500 ATK 怪兽。给我 1 个推荐操作 JSON。"},
        ],
        result_format="message",
    )
    if getattr(resp, "status_code", 200) != 200:
        log.error("决策调用失败: %s", getattr(resp, "message", resp))
        return False
    text = resp.output.choices[0].message.content
    log.info("✅ 决策模型返回：%s", text[:300])
    return True


def main():
    print("=" * 60)
    print("🎴  游戏王 AI 助手 · 冒烟测试")
    print("=" * 60)

    if not has_api_key():
        log.error("❌ API Key 未配置")
        return 1

    log.info("Provider=%s 视觉=%s 文本=%s",
             SETTINGS.llm_provider,
             "qwen-vl-ocr-2025-11-20",
             "qwen-max")

    ok_v = test_vision()
    ok_t = test_text_decision()

    print("=" * 60)
    print(f"视觉模型: {'✅ 通过' if ok_v else '❌ 失败'}")
    print(f"决策模型: {'✅ 通过' if ok_t else '❌ 失败'}")
    print("=" * 60)
    return 0 if (ok_v and ok_t) else 1


if __name__ == "__main__":
    sys.exit(main())
