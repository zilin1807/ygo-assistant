"""PySide6 双模式悬浮窗。

两种模式：
  • alone（陪伴）  — 桌宠作为常驻桌面宠物，透明、可拖；旁边偶尔飘聊天气泡
  • analyzing      — 桌宠吸附分析对话框，显示推荐；点击桌宠可切回 alone

视觉布局（同一 widget 根据 mode 切换）：
  alone:
    ┌─────────┐
    │   🐱    │      ┌──── 聊天气泡 ────┐
    │         │ ◀──▶ │ "要开打吗？"     │
    └─────────┘      └──────────────────┘

  analyzing:
    ┌─────────┐┌──────── 对话框 ────────┐
    │   🐱    ││ ★ 游戏王 AI · 监测中  │
    │         ││ 我方 M1 · LP 3200/... │
    └─────────┘│ ⚡ 对方场…             │
               │ #1 攻击 Golem ✓ ✗    │
               │ #2 …                │
               └──────────────────────┘
"""
from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QPoint, QTimer, Signal
from PySide6.QtGui import QFont, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QFrame, QScrollArea, QSizePolicy, QMenu,
)

from config import SETTINGS
from pet_chat import next_line as chitchat_next

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
PET_PNG = ASSETS_DIR / "desktop_pet.png"


# 内置短句已被 pet_chat.STATIC_LINES 替代，
# 真正飘的话由 LLM 生成（每句都不一样）


class DraggableMixin:
    _drag_pos: Optional[QPoint] = None

    def mousePressEvent(self, ev: QMouseEvent):
        if ev.button() == Qt.LeftButton:
            child = self.childAt(ev.position().toPoint())
            # 在按钮区域不进入拖拽
            if child is not None and isinstance(child, (QPushButton,)):
                return
            self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            ev.accept()

    def mouseMoveEvent(self, ev: QMouseEvent):
        if self._drag_pos and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)
            ev.accept()

    def mouseReleaseEvent(self, ev: QMouseEvent):
        self._drag_pos = None


class SuggestionRow(QFrame):
    accepted = Signal(int)
    rejected = Signal(int)

    def __init__(self, idx: int, action: str, reason: str, parent=None):
        super().__init__(parent)
        self.idx = idx

        self.setStyleSheet("""
            QFrame { background: transparent; border: none; }
            QLabel { color: #1a1a1a; background: transparent; }
            QLabel#Action { font-size: 12px; font-weight: bold; }
            QLabel#Reason { font-size: 11px; color: #666; }
            QPushButton {
                border-radius: 6px;
                padding: 2px 8px;
                font-size: 11px;
                border: none;
                color: white;
            }
            QPushButton#YesBtn { background: #4caf50; }
            QPushButton#YesBtn:hover { background: #43a047; }
            QPushButton#NoBtn  { background: #ef5350; }
            QPushButton#NoBtn:hover { background: #e53935; }
            QPushButton:disabled { background: #bdbdbd; }
        """)

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 2, 0, 2)
        h.setSpacing(6)

        tag = QLabel(f"#{idx + 1}")
        tag.setStyleSheet("color: #fb8c00; font-weight: bold; font-size: 12px;")
        tag.setFixedWidth(20)
        h.addWidget(tag)

        col = QVBoxLayout()
        col.setSpacing(1)
        action_lbl = QLabel(action)
        action_lbl.setObjectName("Action")
        action_lbl.setWordWrap(True)
        col.addWidget(action_lbl)
        if reason:
            r = QLabel(reason)
            r.setObjectName("Reason")
            r.setWordWrap(True)
            col.addWidget(r)
        h.addLayout(col, stretch=1)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(2)
        yes_btn = QPushButton("✓")
        yes_btn.setObjectName("YesBtn")
        yes_btn.setFixedWidth(28)
        yes_btn.clicked.connect(lambda: self.accepted.emit(self.idx))
        btn_col.addWidget(yes_btn)

        no_btn = QPushButton("✗")
        no_btn.setObjectName("NoBtn")
        no_btn.setFixedWidth(28)
        no_btn.clicked.connect(lambda: self.rejected.emit(self.idx))
        btn_col.addWidget(no_btn)
        h.addLayout(btn_col)

    def disable_buttons(self):
        for b in self.findChildren(QPushButton):
            b.setEnabled(False)


# ====== 主 widget ======

class FloatingWidget(DraggableMixin, QWidget):
    pause_toggled = Signal()
    quit_app = Signal()
    feedback = Signal(int, bool)
    pet_clicked = Signal()       # 在陪伴模式点击桌宠
    manual_analyze = Signal()    # 用户主动切到分析模式（带图）

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.mode = "alone"  # 当前模式
        self._last_state: Optional[Dict[str, Any]] = None
        self._last_decision: Optional[Dict[str, Any]] = None

        # === 整体水平布局：左 pet、右 chat/bubble ===
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # --- 左侧：桌宠 ---
        pet_host = QFrame()
        pet_host.setStyleSheet("background: transparent; border: none;")
        pet_host.setFixedWidth(100)
        pv = QVBoxLayout(pet_host)
        pv.setContentsMargins(0, 0, 0, 0)

        self.pet_label = ClickableLabel(self)  # 可点击的 label
        self.pet_label.setStyleSheet("background: transparent;")
        if PET_PNG.exists():
            pix = QPixmap(str(PET_PNG))
            self.pet_label.setPixmap(
                pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            self.pet_label.setText("🐱")
            self.pet_label.setStyleSheet("font-size: 64px; background: transparent;")
        self.pet_label.setAlignment(Qt.AlignCenter)
        self.pet_label.setCursor(Qt.PointingHandCursor)
        self.pet_label.clicked.connect(self.pet_clicked.emit)
        self.pet_label.setToolTip("单击切换模式 · 右键菜单")
        # 右键菜单
        self.pet_label.setContextMenuPolicy(Qt.CustomContextMenu)
        self.pet_label.customContextMenuRequested.connect(self._show_pet_menu)

        pv.addWidget(self.pet_label)
        pv.addStretch()
        root.addWidget(pet_host)

        # --- 右侧：陪伴模式气泡 / 分析模式对话框 ---
        right_host = QFrame()
        right_host.setStyleSheet("background: transparent; border: none;")
        self.rh_layout = QVBoxLayout(right_host)
        self.rh_layout.setContentsMargins(0, 0, 0, 0)

        # 气泡 1：陪伴模式的闲聊
        self.bubble_text = ChatBubble()
        self.rh_layout.addWidget(self.bubble_text)

        # 气泡 2：分析模式的对话框（默认 hidden）
        self.chat_panel = QFrame()
        self.chat_panel.setObjectName("ChatPanel")
        self.chat_panel.setStyleSheet("""
            QFrame#ChatPanel {
                background: rgba(248, 248, 250, 235);
                border: 1px solid #cccccc;
                border-radius: 12px;
            }
            QLabel { background: transparent; }
        """)
        self.chat_panel.setFixedWidth(360)
        self.chat_panel.setMinimumHeight(180)
        self.chat_panel.hide()
        self._build_chat_panel()
        self.rh_layout.addWidget(self.chat_panel)

        root.addWidget(right_host)

        # 初始模式
        self.set_mode("alone")

        # 桌宠空闲动画：每隔 15-30 秒飘一句气泡
        self.idle_timer = QTimer(self)
        self.idle_timer.timeout.connect(self._idle_speak)
        self.idle_timer.start(8000)  # 8s 起步

    # ---- 模式切换 ----

    def set_mode(self, mode: str):
        """mode ∈ {'alone', 'analyzing'}"""
        self.mode = mode
        if mode == "alone":
            self.bubble_text.show()
            self.chat_panel.hide()
            # 缩小整体高度（视觉上变成"小宠"）
            self.resize(self.sizeHint())
        else:
            self.bubble_text.hide()
            self.chat_panel.show()
        self.resize(self.sizeHint())
        self.adjustSize()

    # ---- 模式切换入口 ----

    def _show_pet_menu(self, pos):
        m = QMenu(self)
        m.addAction("❓ 强制分析当前画面", self.manual_analyze.emit)
        m.addAction("─" * 12)
        if self.mode == "alone":
            m.addAction("🎴 切换到分析模式", self._toggle_mode)
        else:
            m.addAction("🐱 切回陪伴模式", self._toggle_mode)
        m.addAction("─" * 12)
        m.addAction("❌ 退出", self.quit_app.emit)
        m.exec_(self.pet_label.mapToGlobal(pos))

    def _toggle_mode(self):
        if self.mode == "alone":
            self.set_mode("analyzing")
        else:
            self.set_mode("alone")

    # 上一句（避免重复）
    def _idle_speak(self):
        if self.mode != "alone":
            return
        # 取上一句给 LLM 让它换风格
        prev = self.bubble_text.current_text() if hasattr(self.bubble_text, "current_text") else None
        text = chitchat_next(prev)
        self.bubble_text.set_text(text)
        self.bubble_text.flash()
        # 间隔随机化 8-25 秒
        self.idle_timer.start(random.randint(8000, 25000))

    def set_status_text(self, text: str):
        """陪伴模式显示自定义文字（用于状态通知）。"""
        if self.mode == "alone":
            self.bubble_text.set_text(text)

    # ---- 分析模式的对话框 ----

    def _build_chat_panel(self):
        v = QVBoxLayout(self.chat_panel)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(6)

        title_row = QHBoxLayout()
        title_lbl = QLabel("🎴 游戏王 AI 助手")
        title_lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        self.status_lbl = QLabel("▶ 监测中")
        self.status_lbl.setStyleSheet("color: #43a047; font-size: 11px;")
        title_row.addWidget(self.status_lbl)
        v.addLayout(title_row)

        self.urgent_lbl = QLabel("")
        self.urgent_lbl.setStyleSheet(
            "color: #d32f2f; font-weight: bold; font-size: 12px;"
            "background: rgba(255,235,238,200); border-radius: 6px; padding: 4px 8px;"
        )
        self.urgent_lbl.setWordWrap(True)
        self.urgent_lbl.hide()
        v.addWidget(self.urgent_lbl)

        self.summary_lbl = QLabel("等待识别…")
        self.summary_lbl.setWordWrap(True)
        self.summary_lbl.setStyleSheet("font-size: 12px; color: #333;")
        v.addWidget(self.summary_lbl)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        self.rows_host = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_host)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(4)
        self.rows_layout.addStretch()
        self.scroll.setWidget(self.rows_host)
        self.scroll.setMaximumHeight(200)
        v.addWidget(self.scroll, stretch=1)

        ctrl = QHBoxLayout()
        self.pause_btn = QPushButton("暂停")
        self.pause_btn.setStyleSheet("""
            QPushButton { background: #eee; border: 1px solid #ccc; border-radius: 6px;
                          padding: 3px 10px; font-size: 11px; color: #333; }
            QPushButton:hover { background: #f5f5f5; }
        """)
        self.pause_btn.clicked.connect(self.pause_toggled.emit)
        ctrl.addWidget(self.pause_btn)
        ctrl.addStretch()
        self.quit_btn = QPushButton("退出")
        self.quit_btn.setStyleSheet("""
            QPushButton { background: #757575; color: white; border: none; border-radius: 6px;
                          padding: 3px 10px; font-size: 11px; }
            QPushButton:hover { background: #5e5e5e; }
        """)
        self.quit_btn.clicked.connect(self.quit_app.emit)
        ctrl.addWidget(self.quit_btn)
        v.addLayout(ctrl)

    def show_decision(self, game_state: Dict[str, Any], decision: Dict[str, Any]):
        if self.mode != "analyzing":
            return
        self._last_state = game_state
        self._last_decision = decision

        self.summary_lbl.setText(decision.get("summary") or self._format_state_summary(game_state))

        urgent = decision.get("urgent") or ""
        if urgent:
            self.urgent_lbl.setText(f"⚡ {urgent}")
            self.urgent_lbl.show()
        else:
            self.urgent_lbl.hide()

        # 清空旧推荐
        while self.rows_layout.count():
            it = self.rows_layout.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

        options = decision.get("options") or []
        if not options:
            empty = QLabel("（暂无推荐…）")
            empty.setStyleSheet("color: #888; font-size: 11px; padding: 4px;")
            self.rows_layout.addWidget(empty)
            self.rows_layout.addStretch()
            return

        for opt in options:
            row = SuggestionRow(
                idx=opt.get("idx", 0),
                action=opt.get("action", ""),
                reason=opt.get("reason", ""),
            )
            row.accepted.connect(self._on_accept)
            row.rejected.connect(self._on_reject)
            self.rows_layout.addWidget(row)
        self.rows_layout.addStretch()

    def _on_accept(self, idx: int):
        self.feedback.emit(idx, True)
        self._mark_row(idx, "#c8e6c9")

    def _on_reject(self, idx: int):
        self.feedback.emit(idx, False)
        self._mark_row(idx, "#ffcdd2")

    def _mark_row(self, idx: int, color: str):
        for i in range(self.rows_layout.count()):
            w = self.rows_layout.itemAt(i).widget()
            if isinstance(w, SuggestionRow) and w.idx == idx:
                w.setStyleSheet(f"background: {color}; border-radius: 6px;")
                w.disable_buttons()
                break

    def show_paused(self, paused: bool):
        if not hasattr(self, "status_lbl"):
            return
        self.status_lbl.setText("⏸ 已暂停" if paused else "▶ 监测中")
        self.status_lbl.setStyleSheet(
            f"color: {'#888' if paused else '#43a047'}; font-size: 11px;"
        )
        self.pause_btn.setText("继续" if paused else "暂停")

    def show_error(self, text: str):
        if self.mode != "analyzing":
            return
        if text:
            self.summary_lbl.setStyleSheet("font-size: 12px; color: #d32f2f;")
            self.summary_lbl.setText(f"⚠ {text}")
        else:
            self.summary_lbl.setStyleSheet("font-size: 12px; color: #333;")
            self.summary_lbl.setText("")

    def show_neglect_status(self, text: str, persist_seconds: float = 0.0):
        """显示一个短的"学习观察"状态标签（在紧急提示框位置复用）。"""
        if not hasattr(self, "urgent_lbl") or self.urgent_lbl is None:
            return
        self.urgent_lbl.setText(text)
        self.urgent_lbl.setStyleSheet(
            "color: #1565c0; font-weight: bold; font-size: 12px;"
            "background: rgba(227,242,253,200); border-radius: 6px; padding: 4px 8px;"
        )
        self.urgent_lbl.show()
        if persist_seconds > 0:
            QTimer.singleShot(int(persist_seconds * 1000), self._hide_neglect_status)

    def _hide_neglect_status(self):
        if hasattr(self, "urgent_lbl") and self.urgent_lbl.isVisible():
            self.urgent_lbl.hide()

    @staticmethod
    def _format_state_summary(state: Dict[str, Any]) -> str:
        if not state:
            return ""
        turn = "我方" if state.get("turn") == 1 else "对方"
        return (
            f"{turn}回合 · {state.get('phase', '?')} · "
            f"LP {state.get('my_lp', '?')}/{state.get('opp_lp', '?')} · "
            f"手牌 {state.get('my_hand_count', '?')}"
        )


# ====== 陪伴模式聊天气泡 ======

class ChatBubble(QWidget):
    """轻量聊天气泡：圆角背景 + 文字 + 三角指向桌宠。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.inner = QLabel("…")
        self.inner.setWordWrap(True)
        self.inner.setStyleSheet("""
            QLabel {
                background: rgba(255, 255, 255, 230);
                color: #1a1a1a;
                font-size: 12px;
                border: 1px solid #d6d6d6;
                border-radius: 10px;
                padding: 6px 12px;
            }
        """)
        v.addWidget(self.inner)
        self.setFixedWidth(180)

    def set_text(self, text: str):
        self._last_text = text
        self.inner.setText(text)

    def current_text(self) -> Optional[str]:
        return getattr(self, "_last_text", None)

    def flash(self):
        """气泡闪一下，强调闲置说话。"""
        self.inner.setStyleSheet("""
            QLabel {
                background: rgba(255, 247, 200, 235);
                color: #1a1a1a;
                font-size: 12px;
                border: 1px solid #e5d28a;
                border-radius: 10px;
                padding: 6px 12px;
            }
        """)
        QTimer.singleShot(700, self._unflash)

    def _unflash(self):
        self.inner.setStyleSheet("""
            QLabel {
                background: rgba(255, 255, 255, 230);
                color: #1a1a1a;
                font-size: 12px;
                border: 1px solid #d6d6d6;
                border-radius: 10px;
                padding: 6px 12px;
            }
        """)


# ====== 可点击的 QLabel ======

class ClickableLabel(QLabel):
    clicked = Signal()
    def mousePressEvent(self, ev: QMouseEvent):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)
