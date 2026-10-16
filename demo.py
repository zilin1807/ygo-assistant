"""完整桌面精灵效果演示：跑视觉识别 + 决策推理 + 把"悬浮窗输出"以彩色控制台形态呈现。

不需要 GUI 依赖，能完整模拟「桌面精灵在你游戏窗口前显示什么」。

输出三段：
  1. 当前局面摘要（高仿真版 MD 截图识别结果）
  2. 推荐的 N 个操作（带采纳/忽略的标注）
  3. 历史决策统计（如果有）

用法：
  python demo.py                          # 用内置仿真图
  python demo.py path/to/your/screen.png # 用你的真实截图（需你自己截）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image
from config import SETTINGS, has_api_key
from logger import get_logger

log = get_logger("demo")

# ANSI 颜色
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    CYAN   = "\033[36m"
    YELLOW = "\033[33m"
    GREEN  = "\033[32m"
    RED    = "\033[31m"
    BLUE   = "\033[34m"
    MAGENTA= "\033[35m"
    GRAY   = "\033[90m"


def banner(title: str, color: str = C.CYAN) -> None:
    line = "═" * (len(title) + 4)
    print(f"\n{color}{C.BOLD}{line}\n  {title}  \n{line}{C.RESET}\n")


def simulate_window(state: Dict[str, Any], decision: Dict[str, Any]) -> None:
    """在终端里模拟「桌面精灵悬浮窗」显示效果。"""
    # 窗口外框
    width = 70
    print(f"{C.MAGENTA}┌{'─' * (width - 2)}┐{C.RESET}")
    print(f"{C.MAGENTA}│{C.BOLD} 🎴 游戏王 AI 助手 · 实时建议{'':>25}{C.RESET}{C.MAGENTA} │{C.RESET}")
    print(f"{C.MAGENTA}├{'─' * (width - 2)}┤{C.RESET}")

    # 局面摘要
    turn = "我方" if state.get("turn") == 1 else "对方"
    summary = (
        f"📍 {turn}回合 · {state.get('phase', '?')}  "
        f"💛 LP {state.get('my_lp', '?')}/{state.get('opp_lp', '?')}  "
        f"🃏 手 {state.get('my_hand_count', '?')}"
    )
    print(f"{C.MAGENTA}│{C.RESET} {summary:<{width - 4}} {C.MAGENTA}│{C.RESET}")

    notes = state.get("notes") or decision.get("summary") or ""
    if notes:
        print(f"{C.MAGENTA}│{C.RESET} {C.GRAY}{notes[:width - 6]}{C.RESET}{'':>{width - 4 - min(len(notes), width - 6)}} {C.MAGENTA}│{C.RESET}")

    # 紧急提示
    urgent = decision.get("urgent") or ""
    if urgent:
        print(f"{C.MAGENTA}│{C.RESET} {C.RED}{C.BOLD}⚡ {urgent[:width - 8]}{C.RESET}{'':>{width - 4 - min(len(urgent), width - 8)}} {C.MAGENTA}│{C.RESET}")

    print(f"{C.MAGENTA}├{'─' * (width - 2)}┤{C.RESET}")

    # 候选操作
    options = decision.get("options") or []
    for i, opt in enumerate(options):
        print(f"{C.MAGENTA}│{C.RESET}")
        idx_line = f"  #{i + 1}  {opt.get('action', '')}"
        print(f"{C.MAGENTA}│{C.RESET} {C.YELLOW}{C.BOLD}{idx_line[:width - 4]}{C.RESET}{'':>{width - 4 - min(len(idx_line), width - 4)}} {C.MAGENTA}│{C.RESET}")

        reason = opt.get("reason", "")
        if reason:
            r = f"       理由：{reason}"
            print(f"{C.MAGENTA}│{C.RESET} {C.GRAY}{r[:width - 4]}{C.RESET}{'':>{width - 4 - min(len(r), width - 4)}} {C.MAGENTA}│{C.RESET}")

        # 按钮行
        btns = "       [ ✅ 采纳 ]   [ ❌ 忽略 ]   [ 🔄 再分析 ]"
        print(f"{C.MAGENTA}│{C.RESET} {C.GRAY}{btns[:width - 4]}{C.RESET}{'':>{width - 4 - min(len(btns), width - 4)}} {C.MAGENTA}│{C.RESET}")

    if not options:
        print(f"{C.MAGENTA}│{C.RESET} {C.GRAY}  （暂无推荐，观察中…）{C.RESET}{'':>{width - 16}} {C.MAGENTA}│{C.RESET}")

    print(f"{C.MAGENTA}├{'─' * (width - 2)}┤{C.RESET}")

    # 底部状态栏
    stats_line = f"  📊 历史采纳率：暂无足够数据"
    print(f"{C.MAGENTA}│{C.RESET} {C.DIM}{stats_line:<{width - 4}}{C.RESET} {C.MAGENTA}│{C.RESET}")

    print(f"{C.MAGENTA}└{'─' * (width - 2)}┘{C.RESET}")


def run(image_path: Optional[str] = None) -> int:
    banner("🎴 游戏王 AI 桌面精灵 · 端到端演示", C.CYAN)

    if not has_api_key():
        print(f"{C.RED}⚠ 未配置 API Key，请先在 .env 填入 DASHSCOPE_API_KEY{C.RESET}")
        return 1

    # 1. 准备图片
    if image_path:
        img = Image.open(image_path).convert("RGB")
        print(f"{C.GRAY}📷 加载图片：{image_path}  {img.size}{C.RESET}")
    else:
        from scene_factory import render_battle_scene
        scene_path = "scene_battle.png"
        img = render_battle_scene(scene_path)
        print(f"{C.GRAY}📷 用内置高仿真测试图：{scene_path}  {img.size}{C.RESET}")
    print()

    # 2. 视觉识别
    print(f"{C.CYAN}▸ 正在调视觉模型 qwen-vl-ocr-2025-11-20 识别画面…{C.RESET}")
    from vision import analyze_frame
    state = analyze_frame(img)
    if not state:
        print(f"{C.RED}✗ 视觉识别失败{C.RESET}")
        return 1

    banner("当前识别结果（局面）", C.BLUE)
    # 关键字段摘要
    summary_keys = ["turn", "phase", "my_lp", "opp_lp", "my_hand_count"]
    for k in summary_keys:
        print(f"  {C.GRAY}{k:<18}{C.RESET}= {C.YELLOW}{state.get(k, '?')}{C.RESET}")
    for collection, label in [("my_field", "我方场上"), ("opp_field", "对方场上"),
                                ("my_grave", "我方墓地"), ("opp_grave", "对方墓地")]:
        items = state.get(collection) or []
        if items:
            print(f"\n  {C.MAGENTA}{label} ({len(items)} 张)：{C.RESET}")
            for it in items[:6]:
                if isinstance(it, dict):
                    name = it.get("name", "?")
                    atk = it.get("atk", "?")
                    pos = it.get("position", "?")
                    print(f"    · {name:<22} ATK {atk}  {C.GRAY}({pos}){C.RESET}")
                else:
                    print(f"    · {it}")
    if state.get("notes"):
        print(f"\n  {C.GRAY}备注：{state['notes']}{C.RESET}")

    # 3. 决策推理
    print()
    print(f"{C.CYAN}▸ 正在调 qwen-max 做决策推理…{C.RESET}")
    from memory import Memory
    from decision import reason
    mem = Memory()
    stats = mem.acceptance_stats() if SETTINGS.enable_memory else {"total": 0, "rate": 0}
    similar = mem.similar_states(state, SETTINGS.memory_top_k) if SETTINGS.enable_memory else []
    decision_obj = reason(state, stats, similar)
    if not decision_obj:
        print(f"{C.RED}✗ 决策推理失败{C.RESET}")
        return 1

    # 4. 显示「桌面精灵悬浮窗」效果
    simulate_window(state, decision_obj)

    print()
    banner("演示完成", C.GREEN)
    print(f"  {C.GRAY}数据流：C:/Users/EDY/WorkBuddy/.../ygo_assistant/{C.RESET}")
    print(f"  {C.GRAY}接入 Master Duel 真窗口：python main.py（需安装 GUI 依赖）{C.RESET}")
    return 0


if __name__ == "__main__":
    img_path = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(run(img_path))
