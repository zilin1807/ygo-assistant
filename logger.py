"""统一日志输出 - 便于调试 & 教学回放。"""
import logging
import sys
from pathlib import Path

from config import ROOT

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)


def get_logger(name: str = "ygo") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # 控制台
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    # 文件（每次启动一个文件）
    fh = logging.FileHandler(LOG_DIR / "runtime.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


log = get_logger()
