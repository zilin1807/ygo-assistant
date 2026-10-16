"""主程序入口 — 双模式桌面精灵。

行为：
  1. 启动后桌宠立即可见（屏幕左上透明背景），处于「陪伴模式」
  2. 后台每 5 秒检测 Master Duel 窗口是否在线
     · 不在线  → 桌宠闲晃、偶尔说话，等待用户
     · 在线    → 桌宠自动切到「分析模式」，弹对话框，1s/次识别画面给推荐
  3. 用户关游戏 → 自动退回陪伴模式
  4. 右键桌宠：强制分析 / 切模式 / 退出

运行：python main.py
"""
from __future__ import annotations

import hashlib
import sys
import threading
import time
from typing import Any, Dict, Optional

from PIL import Image

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from config import SETTINGS, has_api_key
from logger import log
from screenshot import Screenshotter, find_game_window, Region
from memory import Memory
import vision
import decision
from floating_widget import FloatingWidget


# =========================
#   AnalysisWorker（同上）
# =========================

class AnalysisWorker(QThread):
    state_ready = Signal(dict, dict)
    error = Signal(str)
    paused_changed = Signal(bool)

    def __init__(self, screenshotter: Screenshotter, memory: Memory, interval: float):
        super().__init__()
        self.screenshotter = screenshotter
        self.memory = memory
        self.interval = max(0.2, interval)  # 0.2 秒最低（用户希望的快采样）
        self._paused = True
        self._lock = threading.Lock()
        self._running = True
        self._last_hash: Optional[str] = None

    def set_interval(self, interval: float):
        """动态调整分析频率（用于 watcher 启动时压缩采样）。

        即刻生效，下一轮 _sleep_to_interval 用新值。
        """
        with self._lock:
            self.interval = max(0.2, interval)
        log.info("AnalysisWorker 间隔 → %.2fs", self.interval)

    def set_paused(self, paused: bool):
        with self._lock:
            self._paused = paused
        self.paused_changed.emit(paused)

    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    def stop(self):
        self._running = False

    @staticmethod
    def _hash_image_bytes(img_bytes: bytes) -> str:
        return hashlib.md5(img_bytes).hexdigest()[:16]

    def run(self):
        log.info("Worker 已启动")
        while self._running:
            try:
                if self.is_paused():
                    time.sleep(0.2)
                    continue

                t0 = time.time()
                image = self.screenshotter.capture()
                if image is None:
                    self.error.emit("截图失败")
                    self._sleep_to_interval(t0)
                    continue

                img_bytes = image.tobytes()
                img_hash = self._hash_image_bytes(img_bytes)
                if img_hash == self._last_hash:
                    self._sleep_to_interval(t0)
                    continue
                self._last_hash = img_hash

                if not has_api_key():
                    self.error.emit("未配置 API Key（请设置 .env）")
                    self.set_paused(True)
                    self._sleep_to_interval(t0)
                    continue

                game_state = vision.analyze_frame(image)
                if not game_state:
                    self.error.emit("视觉识别失败")
                    self._sleep_to_interval(t0)
                    continue

                stats = self.memory.acceptance_stats() if SETTINGS.enable_memory else {"total": 0}
                similar = self.memory.similar_states(game_state, SETTINGS.memory_top_k) if SETTINGS.enable_memory else []
                obj = decision.reason(game_state, stats, similar)
                if not obj:
                    self.error.emit("决策推理失败")
                    self._sleep_to_interval(t0)
                    continue

                game_state["_image_hash"] = img_hash
                self.state_ready.emit(game_state, obj)
                self._sleep_to_interval(t0)
            except Exception as e:
                log.exception("Worker 异常：%s", e)
                self.error.emit(f"未知异常：{e}")
                time.sleep(1.0)
        log.info("Worker 已停止。")

    def _sleep_to_interval(self, t0: float):
        dt = time.time() - t0
        time.sleep(max(0.2, self.interval - dt))


# =========================
#   GameMonitorThread
# =========================

class GameMonitorThread(QThread):
    """每 5 秒检测一次 Master Duel 窗口是否存在。"""
    game_detected = Signal(object)  # Region
    game_lost = Signal()

    def __init__(self, poll_interval: float = 5.0):
        super().__init__()
        self.poll_interval = poll_interval
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        log.info("GameMonitorThread 启动，每 %.1fs 轮询", self.poll_interval)
        last = False
        while self._running:
            try:
                region = find_game_window()
                present = region is not None
                if present and not last:
                    log.info("检测到 Master Duel 窗口")
                    self.game_detected.emit(region)
                elif not present and last:
                    log.info("Master Duel 窗口已消失")
                    self.game_lost.emit()
                last = present
            except Exception as e:
                log.warning("game monitor tick failed: %s", e)
            time.sleep(self.poll_interval)
        log.info("GameMonitorThread 停止")


# =========================
#   主程序
# =========================

class YGOAssistantApp:
    def __init__(self):
        self.qt_app = QApplication.instance() or QApplication(sys.argv)

        if not has_api_key():
            QMessageBox.warning(
                None, "未配置 API Key",
                f"当前 Provider = {SETTINGS.llm_provider}\n请在 .env 中填入 Key 后重启。",
            )

        # 桌宠 widget 立刻起来
        self.widget = FloatingWidget()
        self.widget.move(60, 60)
        self.widget.show()
        self.widget.set_status_text("桌宠已就绪 · 等 Master Duel 启动")
        self.widget.quit_app.connect(self._quit)
        self.widget.pet_clicked.connect(self._on_pet_click)
        self.widget.feedback.connect(self._on_feedback)
        self.widget.pause_toggled.connect(self._toggle_pause)
        self.widget.manual_analyze.connect(self._manual_analyze)

        # 监测 MD 启动
        self.monitor = GameMonitorThread(poll_interval=5.0)
        self.monitor.game_detected.connect(self._on_game_detected)
        self.monitor.game_lost.connect(self._on_game_lost)
        self.monitor.start()

        # 运行时变状态
        self.screenshotter: Optional[Screenshotter] = None
        self.worker: Optional[AnalysisWorker] = None
        self.memory = Memory()
        self._last_decision_payload: Optional[Dict[str, Any]] = None
        self._game_present = False

    # ---------- 模式切换 ----------

    def _on_pet_click(self):
        """点击桌宠：在 alone/analyzing 间切换。"""
        if self.widget.mode == "alone":
            if not self._game_present:
                self.widget.set_status_text("暂时还没检测到 Master Duel")
                return
            self.widget.set_mode("analyzing")
        else:
            self.widget.set_mode("alone")

    def _manual_analyze(self):
        """用户右键 → 强制分析一次（用当前屏幕截屏）。"""
        log.info("用户强制分析…")
        if not has_api_key():
            QMessageBox.warning(None, "未配置 API Key", "先在 .env 填入 DASHSCOPE_API_KEY")
            return
        try:
            ss = self.screenshotter or Screenshotter()
            img = ss.capture()
            if img is None:
                QMessageBox.warning(None, "截图失败", "没抓到画面，确认 Master Duel 在屏")
                return
            from vision import analyze_frame
            from decision import reason
            gs = analyze_frame(img)
            if not gs:
                QMessageBox.warning(None, "识别失败", "画面不够清晰")
                return
            obj = reason(gs, {"total": 0}, [])
            if not obj:
                QMessageBox.warning(None, "决策失败", "LLM 调用异常")
                return
            self.widget.set_mode("analyzing")
            self.widget.show_decision(gs, obj)
        except Exception as e:
            log.exception("manual_analyze 异常：%s", e)
            QMessageBox.warning(None, "异常", str(e))

    # ---------- MD 启动 / 退出事件 ----------

    def _on_game_detected(self, region):
        if self._game_present:
            return
        self._game_present = True

        # 设置截图区域
        if self.screenshotter is None:
            self.screenshotter = Screenshotter(region)
        else:
            self.screenshotter.set_region(region)

        # 启动分析 worker
        self.worker = AnalysisWorker(self.screenshotter, self.memory, SETTINGS.screenshot_interval)
        self.worker.state_ready.connect(self._on_state_ready)
        self.worker.error.connect(self.widget.show_error)
        self.worker.paused_changed.connect(self.widget.show_paused)
        self.worker.start()
        self.worker.set_paused(False)

        self.widget.set_mode("analyzing")
        log.info("进入分析模式")

    def _on_game_lost(self):
        if not self._game_present:
            return
        self._game_present = False

        if self.worker is not None:
            self.worker.stop()
            self.worker.wait(2000)
            self.worker = None

        self.widget.set_mode("alone")
        self.widget.set_status_text("MD 退出了 · 我回去摸鱼了")
        log.info("退回陪伴模式")

    # ---------- 数据流 ----------

    def _on_state_ready(self, game_state, decision_obj):
        self._last_decision_payload = {"game_state": game_state, "decision": decision_obj}
        self.widget.show_decision(game_state, decision_obj)

    def _on_feedback(self, idx: int, accepted: bool):
        if not self._last_decision_payload or not SETTINGS.enable_memory:
            return
        gs = self._last_decision_payload["game_state"]
        obj = self._last_decision_payload["decision"]
        options = obj.get("options") or []
        row_id = self.memory.record(
            image_hash=gs.get("_image_hash", ""),
            game_state=gs,
            suggestions=options,
            chosen_idx=idx if accepted else -1,
            accepted=accepted,
        )
        log.info("反馈 #%d accepted=%s", row_id, accepted)

        # 如果用户 ✗ 忽略（不是采纳某条），启动观察员追踪用户实际操作
        if not accepted:
            log.info("用户忽略候选 → 启动 NeglectWatcher")
            self._start_neglect_watcher(gs, options, rejected_idx=idx, parent_decision_id=row_id)

        # opt-in 上报到中央训练池（默认关闭）
        try:
            import telemetry
            telemetry.submit_sample(
                game_state=gs,
                suggestions=options,
                chosen_idx=idx if accepted else -1,
                accepted=accepted,
            )
        except Exception as e:
            log.debug("telemetry 异常（不影响主流程）：%s", e)

    def _toggle_pause(self):
        if self.worker is None:
            return
        self.worker.set_paused(not self.worker.is_paused())

    # ---- Neglect Watcher ----

    def _start_neglect_watcher(self, gs: dict, options: list,
                                rejected_idx: int, parent_decision_id: int):
        """用户 ✗ 忽略某条推荐 → 启动后台观察员。

        观察 8 秒内游戏画面变化 → 推断用户实际做了什么。
        高密度采样窗口：worker.interval 临时设为 0.2s（默认 1.0s），
        完成后自动恢复，hash 去重让 LLM 调用不会爆增。
        """
        if self.screenshotter is None:
            log.warning("没有 screenshotter，跳过 watcher")
            return

        # 单例模式：避免多个 watcher 并跑
        if getattr(self, "_neglect_watcher", None) is not None and self._neglect_watcher.isRunning():
            log.info("已有 watcher 在跑，先 stop 旧的一个")
            self._neglect_watcher.stop()
            self._neglect_watcher.wait(1500)

        # 临时提高主循环的采样密度
        if self.worker is not None:
            self.worker.set_interval(SETTINGS.screenshot_interval_neglect)

        from neglect_watcher import NeglectWatcher
        self._neglect_watcher = NeglectWatcher(
            screenshotter=self.screenshotter,
            memory=self.memory,
            state_before=gs,
            ai_suggestions=options,
            rejected_idx=rejected_idx,
            decision_id=parent_decision_id,
            watch_seconds=8.0,
            poll_interval=SETTINGS.screenshot_interval_neglect,  # 0.2s 同步
        )
        self._neglect_watcher.result_ready.connect(self._on_neglect_done)
        self._neglect_watcher.result_ready.connect(self._on_neglect_result)
        self._neglect_watcher.fail.connect(self._on_neglect_done)
        self._neglect_watcher.fail.connect(self._on_neglect_fail)
        self._neglect_watcher.start()
        log.info("NeglectWatcher 已启动，监听 8s（采样 %.2fs）", SETTINGS.screenshot_interval_neglect)
        if hasattr(self.widget, "show_neglect_status"):
            self.widget.show_neglect_status("🔍 学习中…（正在观察你的下一步）")

    def _on_neglect_done(self, *args):
        """watcher 完成（不论成功/失败/超时）→ 恢复主循环频率。"""
        log.info("NeglectWatcher 退出，恢复主循环到 %.2fs", SETTINGS.screenshot_interval)
        if self.worker is not None:
            self.worker.set_interval(SETTINGS.screenshot_interval)

        msg = args[0] if args else ""
        if hasattr(self.widget, "show_neglect_status") and isinstance(msg, str):
            if "超时" in msg or "未观察到" in msg:
                self.widget.show_neglect_status("⏸ 没观察到操作（可能你没动）", persist_seconds=3.0)
            return

    def _on_neglect_result(self, payload: dict):
        action = payload.get("inferred_action", {})
        text = action.get("action", "未能推断")
        conf = action.get("confidence", 0.0)
        log.info("推断完成：%s (置信 %.2f)", text, conf)
        if hasattr(self.widget, "show_neglect_status"):
            self.widget.show_neglect_status(
                f"已学到：你刚才做了「{text}」",
                persist_seconds=6.0,
            )

    def _quit(self):
        log.info("退出中…")
        try:
            if self.worker is not None:
                self.worker.stop()
                self.worker.wait(2000)
            self.monitor.stop()
            self.monitor.wait(2000)
            if self.screenshotter:
                self.screenshotter.close()
        finally:
            self.qt_app.quit()

    # ---------- 启动 ----------

    def run(self):
        return self.qt_app.exec()


def main():
    import traceback

    def _excepthook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        print(text, file=sys.stderr)
        try:
            log.error("未捕获异常：\n%s", text)
        except Exception:
            pass

    sys.excepthook = _excepthook

    try:
        app = YGOAssistantApp()
        sys.exit(app.run())
    except SystemExit:
        raise
    except KeyboardInterrupt:
        log.info("用户中断退出。")
        sys.exit(0)
    except Exception:
        log.exception("启动异常：\n%s", traceback.format_exc())
        try:
            print("\n[CRASH] 程序启动失败，详情请看 logs/runtime.log")
            input("\n按回车退出…")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
