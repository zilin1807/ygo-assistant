"""屏幕截取模块
- 自动定位 Master Duel / ygopro 等游戏窗口
- 用 mss 截取该区域
- 支持手动 fallback：让用户框选区域
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional, Tuple

import mss
from PIL import Image

# Windows 专属：自动定位游戏窗口
try:
    import win32gui  # type: ignore
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

from logger import log


@dataclass
class Region:
    """屏幕选区，左上角 + 宽高"""
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def as_mss_dict(self) -> dict:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


# === 常见的游戏王客户端窗口名关键字 ===
GAME_WINDOW_KEYWORDS = [
    "master duel",
    "ygopro",
    "ygo",
    "masterduel",
    "游戏王",
]


def find_game_window() -> Optional[Region]:
    """尝试在 Windows 上找到游戏窗口位置。

    返回 None 时调用方应 fallback 到让用户手动框选。
    """
    if not WIN32_AVAILABLE or sys.platform != "win32":
        log.warning("非 Windows 环境，跳过自动窗口识别，请手动框选。")
        return None

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    # 必须显式声明 callback 类型；ctypes >= 3.12 严格模式下未标注会抛
    # "Don't know how to convert parameter 1"。
    EnumWindowsProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    found = {"hwnd": None}
    stop = {"flag": False}

    def cb(hwnd, _lparam):
        # 返回 True 继续枚举，False 停止
        if stop["flag"]:
            return False
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = (buff.value or "").lower()
            for kw in GAME_WINDOW_KEYWORDS:
                if kw in title:
                    found["hwnd"] = hwnd
                    stop["flag"] = True
                    return False
        except Exception:
            return True
        return True

    try:
        user32.EnumWindows(EnumWindowsProc(cb), None)
    except Exception as e:
        log.error("枚举窗口失败：%s", e)
        return None

    hwnd = found["hwnd"]
    if not hwnd:
        log.info("未找到游戏窗口（关键字：%s）", GAME_WINDOW_KEYWORDS)
        return None

    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    region = Region(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)

    # 边框裁剪：去掉标题栏
    title_bar = 32
    if region.height > title_bar + 200 and region.width > 400:
        region = Region(
            region.left + 8,
            region.top + title_bar,
            region.width - 16,
            region.height - title_bar - 8,
        )
    log.info("已定位游戏窗口: %s 选区 %s", region.left, region.as_mss_dict())
    return region


class Screenshotter:
    """统一截屏入口。

    用法：
        ss = Screenshotter(region=find_game_window() 或 None)
        frame = ss.capture()  # PIL.Image

    间隔相关：AnalysisWorker 自身维护 interval 字段；Screenshotter 只是个截屏器
    不负责调度。动态调整主循环频率由 main.py 在启停 watcher 时同步设置。
    """

    def __init__(self, region: Optional[Region] = None):
        self.region = region
        self._mss = mss.mss()

    def set_region(self, region: Region):
        self.region = region

    def capture(self) -> Optional[Image.Image]:
        """按当前 region 截一帧；region 为空时截全屏。

        mss 10.x：ScreenShot.rgb 是 RGB bytes（不再是 BGR 的 bgrgb），
        直接喂给 Pillow。
        """
        if self.region is None:
            monitor = self._mss.monitors[1]  # 主显示器
        else:
            monitor = self.region.as_mss_dict()
        try:
            raw = self._mss.grab(monitor)
            # raw.size 是 (width, height) 元组；raw.rgb 是 RGB 顺序的 bytes
            return Image.frombytes("RGB", raw.size, raw.rgb, "raw", "RGB")
        except Exception as e:
            log.error("截图失败：%s", e)
            return None

    def close(self):
        try:
            self._mss.close()
        except Exception:
            pass


def manual_select_region() -> Optional[Region]:
    """让用户手动框选区域（用 Tkinter，节省一个依赖，零额外安装）。"""
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        log.error("Tkinter 不可用，无法手动选区。")
        return None

    root = tk.Tk()
    root.attributes("-alpha", 0.3)
    root.attributes("-fullscreen", True)
    root.title("请框选游戏窗口区域（按 ESC 取消）")
    root.configure(bg="gray")

    rect_box: dict = {}

    canvas = tk.Canvas(root, cursor="cross", bg="gray", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    def on_press(e):
        rect_box["x0"] = e.x_root
        rect_box["y0"] = e.y_root
        canvas.delete("rect")

    def on_drag(e):
        canvas.delete("rect")
        canvas.create_rectangle(
            rect_box["x0"], rect_box["y0"], e.x_root, e.y_root,
            outline="red", width=2, tag="rect",
        )

    def on_release(e):
        rect_box["x1"] = e.x_root
        rect_box["y1"] = e.y_root
        root.destroy()

    def on_escape(e):
        rect_box.clear()
        root.destroy()

    root.bind("<Escape>", on_escape)
    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)

    root.mainloop()

    if not all(k in rect_box for k in ("x0", "y0", "x1", "y1")):
        return None
    left = min(rect_box["x0"], rect_box["x1"])
    top = min(rect_box["y0"], rect_box["y1"])
    width = abs(rect_box["x1"] - rect_box["x0"])
    height = abs(rect_box["y1"] - rect_box["y0"])
    if width < 100 or height < 100:
        return None
    return Region(left, top, width, height)
