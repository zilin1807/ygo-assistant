"""训练数据导出 - SQLite → 阿里云百炼 SFT jsonl。

每条样本 = 一个完整对局的一手决策：
  user input  : 当前局面 + 候选操作
  assistant   : 用户真实选择的"操作 + 原因"

格式（ChatML jsonl，每行）：
  {"messages": [
      {"role":"system", "content":"你是游戏王对战助手..."},
      {"role":"user",   "content":"当前局面：...\\n候选：...\\n请选一个"},
      {"role":"assistant", "content":"用手中的<卡>做<事>：<理由>"}
  ]}

数据来源：
  · 本地 SQLite (data/decisions.db) — 仅本人单机
  · opt-in 上报的云端样本（如果用户开了 telemetry 并有云端 API）

用法：
  python train_export.py                          # 默认导出本地 SQLite 到 train_data.jsonl
  python train_export.py --min-rounds 10          # 只导至少打过 10 局的数据
  python train_export.py --out fancy.jsonl        # 指定输出文件
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from memory import Memory


SYSTEM_PROMPT = (
    "你是 Yu-Gi-Oh (Master Duel) 的对战助手。"
    "用户会给当前局面 + 候选操作列表，请按真实游戏逻辑选最合理的那个，"
    "并用一句话给出理由（≤25 字）。"
)


def state_to_text(state: dict) -> str:
    """把 game_state dict 序列化成中文描述。"""
    parts = []
    turn = "我方回合" if state.get("turn") == 1 else "对方回合"
    parts.append(f"回合：{turn}")
    if state.get("phase"):
        parts.append(f"阶段：{state['phase']}")
    parts.append(f"LP：{state.get('my_lp','?')} vs {state.get('opp_lp','?')}")
    hand = state.get("my_hand_count", "?")
    parts.append(f"我方手牌张数：{hand}")

    if state.get("my_field"):
        ms = ", ".join(
            f"{m.get('name','?')}({m.get('atk','?')}/{m.get('def','?')},{m.get('position','?')})"
            if isinstance(m, dict) else str(m)
            for m in state.get("my_field", [])
        )
        if ms:
            parts.append(f"我方场上：{ms}")
    if state.get("opp_field"):
        os_ = ", ".join(
            f"{m.get('name','?')}({m.get('atk','?')}/{m.get('def','?')},{m.get('position','?')})"
            if isinstance(m, dict) else str(m)
            for m in state.get("opp_field", [])
        )
        if os_:
            parts.append(f"对方场上：{os_}")
    if state.get("notes"):
        parts.append(f"备注：{state['notes']}")
    return "；".join(parts)


def suggestions_to_text(suggestions: list) -> str:
    """候选操作列表 → 中文描述。"""
    if not suggestions:
        return "（无候选）"
    lines = []
    for i, s in enumerate(suggestions):
        if not isinstance(s, dict):
            continue
        lines.append(f"#{i+1} {s.get('action','?')} → {s.get('reason','?')}")
    return "\n".join(lines)


def chosen_to_text(suggestions: list, chosen_idx: int) -> str:
    """用户采纳的操作 + 简短理由。"""
    if chosen_idx < 0 or chosen_idx >= len(suggestions):
        return "（用户选择跳过候选，使用其他方案）"
    s = suggestions[chosen_idx] if isinstance(suggestions[chosen_idx], dict) else {}
    return f"{s.get('action','?')}：{s.get('reason','?')[:25]}"


def export(
    out_path: Path,
    min_rounds: int = 5,
):
    mem = Memory()

    accepted = mem.recent(limit=10000)
    accepted = [r for r in accepted if r.get("accepted")]

    if len(accepted) < min_rounds:
        print(f"⚠ 本地只采集到 {len(accepted)} 条采纳样本。")
        print(f"  建议至少 {min_rounds}+ 条再训练（否则模型学不到东西）。")
        print(f"  你可以：多用 ygo_assistant 打几局，按 \"采纳 ✓\" 反馈即可累积。")
        print(f"  或者：调小 min_rounds（不建议，会过拟合）。")
        if len(accepted) == 0:
            return 0

    written = 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in accepted:
            try:
                gs = json.loads(row["game_state_json"])
                sugs = json.loads(row["suggestions_json"])
            except Exception:
                continue
            chosen_idx = row["chosen_idx"]
            if chosen_idx < 0:
                continue

            user_msg = (
                f"当前局面：{state_to_text(gs)}。\n"
                f"候选操作：\n{suggestions_to_text(sugs)}\n"
                f"请选最合理的一个，用一句话给理由。"
            )
            assistant_msg = chosen_to_text(sugs, chosen_idx)

            sample = {
                "messages": [
                    {"role": "system",    "content": SYSTEM_PROMPT},
                    {"role": "user",      "content": user_msg},
                    {"role": "assistant", "content": assistant_msg},
                ]
            }
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
            written += 1

    print(f"✅ 导出 {written} 条训练样本到 {out_path}")
    print(f"   下一步：python train_submit.py {out_path}")
    return written


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="train_data.jsonl")
    parser.add_argument("--min-rounds", type=int, default=5)
    args = parser.parse_args()
    export(Path(args.out), min_rounds=args.min_rounds)


if __name__ == "__main__":
    main()
