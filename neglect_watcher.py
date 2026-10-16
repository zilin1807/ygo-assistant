"""学习观察员（NeglectWatcher）

触发条件：用户 ✗ 忽略 AI 推荐时启动。
工作流程：
  1. 立刻截图基线 = state_before / img_before
  2. 每 poll_interval 秒截一次屏 / 识别状态
  3. 发现状态变化（LP/怪兽/回合 等差异）→ 调用 action_analyzer 推断用户的实际操作
  4. 推断结果回写到 memory.decisions_neglected 表
  5. 通过 Signal 把结果推给 UI 显示"AI 推荐 X，但你做了 Y"

停止条件：
  - 检测到状态变化并完成推断（成功）
  - watch_seconds 用完（超时）
  - 外部 stop() 调用
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from PySide6.QtCore import QThread, Signal

from action_analyzer import infer, diff_key
from memory import Memory
from screenshot import Screenshotter
from vision import analyze_frame


class NeglectWatcher(QThread):
    # 数据返回：state_before / state_after / ai_suggestions / inferred_action
    result_ready = Signal(dict)
    fail = Signal(str)

    def __init__(
        self,
        screenshotter: Screenshotter,
        memory: Memory,
        state_before: dict,
        ai_suggestions: list,
        rejected_idx: int,
        decision_id: Optional[int],
        watch_seconds: float = 8.0,
        poll_interval: float = 1.5,
    ):
        super().__init__()
        self.ss = screenshotter
        self.memory = memory
        self.state_before = state_before
        self.ai_suggestions = ai_suggestions
        self.rejected_idx = rejected_idx
        self.decision_id = decision_id
        self.watch_seconds = watch_seconds
        self.poll_interval = max(0.5, poll_interval)
        self._running = True
        self._row_id: Optional[int] = None

    def stop(self):
        self._running = False

    def _state_changed_enough(self, a: dict, b: dict) -> bool:
        """业务级变化：LP/场上怪兽/回合/阶段/手牌数量等发生变化。"""
        keys = ("my_lp", "opp_lp", "turn", "phase",
                "my_hand_count", "my_field", "opp_field")
        for k in keys:
            if a.get(k) != b.get(k):
                return True
        return False

    def run(self):
        # Step 1: 先入库一条占位（actual_action=null，后续 UPDATE）
        try:
            self._row_id = self.memory.record_neglected(
                decision_id=self.decision_id,
                rejected_idx=self.rejected_idx,
                state_before=self.state_before,
                state_after=None,
                ai_suggestions=self.ai_suggestions,
                actual_action=None,
                confidence=0.0,
                detected_change="",
                note="watcher started",
            )
        except Exception as e:
            self.fail.emit(f"记录启动失败：{e}")
            return

        deadline = time.time() + self.watch_seconds
        last_state: Optional[dict] = None
        last_img = None

        # 第一次稍等 0.6s 让 UI 画面变化稳定
        time.sleep(0.6)

        while self._running and time.time() < deadline:
            try:
                cap = self.ss.capture()
                if cap is None:
                    time.sleep(self.poll_interval)
                    continue

                gs = analyze_frame(cap)
                if gs is None:
                    last_img = cap  # 没识别到也保留图
                    time.sleep(self.poll_interval)
                    continue

                if last_state is not None and self._state_changed_enough(last_state, gs):
                    # 检测到变化 → 进入推断分支
                    self._run_inference(last_state, gs, last_img, cap)
                    return

                last_state = gs
                last_img = cap
            except Exception as e:
                self.fail.emit(f"watcher 异常：{e}")
                return
            time.sleep(self.poll_interval)

        # 超时没变化
        try:
            if self._row_id is not None:
                self.memory.last_neglected_update_action(
                    self._row_id,
                    actual_action={"action": "未观察到变化", "reason": "watch 超时", "confidence": 0.0},
                    confidence=0.0,
                    detected_change="",
                )
        except Exception:
            pass
        self.fail.emit("超时未观察到变化")

    def _run_inference(self, state_before_change: dict, state_after_change: dict,
                        img_before: any, img_after: any):
        """检测到变化后调用 LLM 推断，并写库。"""
        try:
            action = infer(
                state_before=state_before_change,
                state_after=state_after_change,
                img_before=img_before,
                img_after=img_after,
            )
        except Exception as e:
            action = {"action": "推断异常", "reason": str(e), "confidence": 0.0}

        change_keys = diff_key(state_before_change, state_after_change)

        try:
            if self._row_id is not None:
                self.memory.last_neglected_update_action(
                    self._row_id,
                    actual_action=action,
                    confidence=action.get("confidence", 0.0),
                    detected_change=",".join(change_keys),
                )
        except Exception as e:
            self.fail.emit(f"DB 更新失败：{e}")
            return

        payload = {
            "row_id": self._row_id,
            "state_before": state_before_change,
            "state_after": state_after_change,
            "ai_suggestions": self.ai_suggestions,
            "rejected_idx": self.rejected_idx,
            "inferred_action": action,
            "change_keys": list(change_keys),
        }
        self.result_ready.emit(payload)
