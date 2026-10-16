"""高仿真游戏王大师决斗（Master Duel）场面生成器。

风格对齐 MD 的 3D 视角场地区域布局，让视觉模型在真实游戏场景下也能识别。
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont


def _load_font(size: int = 16, bold: bool = False) -> ImageFont.ImageFont:
    """尽量用微软雅黑 / Arial，失败 fallback 默认字体。"""
    candidates = [
        ("/Library/Fonts/PingFang.ttc", bold),
        ("C:/Windows/Fonts/msyh.ttc", bold),
        ("C:/Windows/Fonts/msyhbd.ttc", bold),
        ("C:/Windows/Fonts/arial.ttf", bold),
        ("/System/Library/Fonts/Helvetica.ttc", bold),
    ]
    for p, b in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _card(d: ImageDraw.ImageDraw, xy: Tuple[int, int], name: str,
           atk: Optional[int] = None, def_: Optional[int] = None,
           pos: str = "ATK", color: Tuple[int, int, int] = (210, 220, 245)) -> None:
    """画一张带 ATK/DEF 的怪兽卡（横置）。"""
    x, y = xy
    w, h = 75, 105
    # 卡背 & 边框
    d.rectangle([(x, y), (x + w, y + h)], fill=color, outline=(20, 20, 20), width=2)
    # 卡名
    name_font = _load_font(11)
    if len(name) > 7:
        name_font = _load_font(9)
    d.text((x + 5, y + 4), name, fill=(10, 10, 10), font=name_font)
    # 卡图区域
    d.rectangle([(x + 5, y + 22), (x + w - 5, y + 78)], fill=(255, 255, 255), outline=(120, 120, 120))
    d.line([(x + 5, y + 22), (x + w - 5, y + 78)], fill=(220, 220, 220))
    # ATK/DEF
    if atk is not None or def_ is not None:
        big = _load_font(11, bold=True)
        a = str(atk) if atk is not None else "?"
        df = str(def_) if def_ is not None else "?"
        d.text((x + 4, y + h - 18), f"ATK {a}", fill=(10, 10, 10), font=big)
        d.text((x + 4, y + h - 8), f"DEF {df}", fill=(10, 10, 10), font=big)
    # 表示形式
    if pos == "DEF" or pos == "FACE-DOWN":
        d.rectangle([(x, y), (x + w, y + h)], fill=(40, 30, 70), outline=(10, 10, 10), width=2)
        # 背面花纹
        for i in range(0, w + h, 8):
            d.line([(x, y + i), (x + max(0, i - h), y + h)], fill=(90, 70, 140), width=1)
            d.line([(x + i, y), (x + w, y + max(0, i - w))], fill=(90, 70, 140), width=1)


def _cover(d: ImageDraw.ImageDraw, xy: Tuple[int, int], name: str = "Cover") -> None:
    """覆盖卡（魔法/陷阱覆盖，背面）。"""
    x, y = xy
    w, h = 75, 105
    d.rectangle([(x, y), (x + w, y + h)], fill=(40, 60, 40), outline=(10, 10, 10), width=2)
    for i in range(0, w + h, 8):
        d.line([(x, y + i), (x + max(0, i - h), y + h)], fill=(70, 110, 70), width=1)
        d.line([(x + i, y), (x + w, y + max(0, i - w))], fill=(70, 110, 70), width=1)
    font = _load_font(11, bold=True)
    d.text((x + 8, y + 8), name, fill=(220, 230, 220), font=font)


def _hand(d: ImageDraw.ImageDraw, x0: int, y: int, n: int = 5, fan: bool = True,
          color: Tuple[int, int, int] = (220, 200, 180)) -> None:
    """手牌（扇形展开）。"""
    cw, ch = 75, 105
    if not fan:
        for i in range(n):
            _card(d, (x0 + i * (cw - 50), y), "?", color=color)
        return

    # 扇形
    cx, cy = x0 + (n - 1) * (cw - 50) // 2, y + ch // 2
    spread = 90  # 半弧角度
    for i in range(n):
        t = n - 1 and i / (n - 1) or 0.5
        angle_deg = -spread / 2 + spread * t
        ang = math.radians(angle_deg)
        ox = int(math.sin(ang) * 60)
        oy = int(math.cos(ang) * 12)
        _card(d, (cx + ox - cw // 2 + (i - (n - 1) / 2) * (cw - 25), y + oy), "?", color=color)


def render_battle_scene(path: str = "scene_battle.png") -> Image.Image:
    """模拟 Master Duel 一个中盘局面：对方回合刚结束进入我方 M1。"""
    W, H = 1280, 720
    img = Image.new("RGB", (W, H), color=(28, 18, 45))  # MD 紫底
    d = ImageDraw.Draw(img)

    # --- 顶部状态栏 ---
    big = _load_font(28, bold=True)
    small = _load_font(13)
    d.rectangle([(0, 0), (W, 50)], fill=(40, 25, 60))
    d.text((30, 12), "自己回合 · M1 阶段", fill=(255, 235, 130), font=big)
    d.text((W - 200, 16), "回合 8", fill=(220, 220, 220), font=small)

    # --- 对方区域（上方） ---
    d.rectangle([(0, 50), (W, 350)], fill=(35, 22, 55))
    # 对方 LP（左）
    d.text((30, 70), "OPPONENT", fill=(180, 180, 200), font=small)
    d.text((30, 90), "4800", fill=(255, 235, 130), font=big)
    # 对方 GY / Extra（右上）
    d.text((W - 200, 65), "墓地 3", fill=(200, 200, 200), font=small)
    d.text((W - 200, 85), "额外 5", fill=(200, 200, 200), font=small)

    # 对方怪兽区（5格）
    opp_y = 130
    slot_w = 100
    for i in range(5):
        x = W // 2 - 2 * slot_w + i * slot_w
        d.rectangle([(x, opp_y), (x + 95, opp_y + 105)], outline=(80, 60, 110))
    # 对方 2 张怪兽在场
    _card(d, (W // 2 - 2 * slot_w + 5, opp_y + 5), "Golem", atk=2500, def_=2500, pos="ATK")
    _card(d, (W // 2 - 2 * slot_w + 110, opp_y + 5), "Knight", atk=1900, def_=0, pos="ATK")
    # 对方 1 张覆盖
    _cover(d, (W // 2 - 2 * slot_w + 215, opp_y + 5), "Set?")

    # 对方手牌（5 张背面，右上）
    for i in range(5):
        cx = W - 220 + i * 30
        d.rectangle([(cx, 100), (cx + 50, 168)], fill=(45, 25, 70), outline=(20, 10, 40), width=2)

    # --- 场地中央（分割）---
    d.line([(0, 350), (W, 350)], fill=(80, 50, 110), width=2)

    # --- 我方区域（下方） ---
    d.rectangle([(0, 350), (W, H)], fill=(20, 14, 35))

    # 我方 LP（右）
    d.text((W - 200, H - 90), "PLAYER", fill=(180, 180, 200), font=small)
    d.text((W - 200, H - 70), "3200", fill=(255, 235, 130), font=big)
    # 我方 GY / Extra（左下）
    d.text((30, H - 90), "墓地 2", fill=(200, 200, 200), font=small)
    d.text((30, H - 70), "额外 3", fill=(200, 200, 200), font=small)

    # 我方怪兽区（5 格，纵向中部）
    my_y = 470
    for i in range(5):
        x = W // 2 - 2 * slot_w + i * slot_w
        d.rectangle([(x, my_y), (x + 95, my_y + 105)], outline=(80, 60, 110))
    # 我方 2 张攻击表示怪兽
    _card(d, (W // 2 - 2 * slot_w + 5, my_y + 5), "Dragon", atk=2500, def_=2000, pos="ATK", color=(200, 230, 250))
    _card(d, (W // 2 - 2 * slot_w + 110, my_y + 5), "SwordFish", atk=1800, def_=1200, pos="ATK", color=(210, 230, 220))

    # 我方魔陷区（5 格）
    st_y = 595
    for i in range(5):
        x = W // 2 - 2 * slot_w + i * slot_w
        d.rectangle([(x, st_y), (x + 95, st_y + 105)], outline=(80, 60, 110))
    # 我方 1 张覆盖陷阱
    _cover(d, (W // 2 - 2 * slot_w + 5, st_y + 5), "ST")

    # 我方手牌（5 张），中央底部扇形
    hand_y = H - 60
    hand_n = 5
    hand_color = (220, 200, 180)
    # 用扇形近似
    cx = W // 2
    for i in range(hand_n):
        offset = (i - 2) * 60
        x = cx - 35 + offset
        _card(d, (x, hand_y), "?", color=hand_color)

    # 右上角 Phase 指示（蓝/绿各 6 阶段）
    px = W - 180
    py = 360
    for i, label in enumerate(["DP", "SP", "M1", "BP", "M2", "EP"]):
        x0 = px + (i % 3) * 55
        y0 = py + (i // 3) * 40
        fill = (120, 180, 240) if i == 2 else (50, 35, 80)
        d.rectangle([(x0, y0), (x0 + 50, y0 + 32)], fill=fill, outline=(120, 100, 160))
        f = _load_font(11, bold=True)
        d.text((x0 + 14, y0 + 8), label, fill=(10, 10, 10), font=f)

    img.save(path, "PNG")
    return img


def render_text_scene(path: str = "scene_text_heavy.png") -> Image.Image:
    """更文字密集的场景（OCR 模型优势场），用于证明 OCR 版够用。"""
    img = render_battle_scene(path)
    W, H = img.size
    d = ImageDraw.Draw(img)
    # 在场地上叠更多文字标签（ATK/DEF/Status）
    big = _load_font(20, bold=True)
    small = _load_font(14)
    d.text((30, 30), "OPR LP:4800", fill=(255, 235, 130), font=big)
    d.text((W - 320, 30), "PLAYER LP:3200", fill=(255, 235, 130), font=big)
    d.text((30, 50), "TURN 8", fill=(220, 220, 220), font=small)
    d.text((30, H - 30), "PHASE: MAIN1", fill=(220, 220, 220), font=small)
    img.save(path, "PNG")
    return img


if __name__ == "__main__":
    render_battle_scene()
    render_text_scene()
    print("OK")
