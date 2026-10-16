"""配置管理 - 读取环境变量和 .env 文件，统一暴露给其他模块。"""
from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass

from dotenv import load_dotenv

# 工程根目录 = 本文件所在目录
ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def _env(key: str, default: str = "") -> str:
    v = os.getenv(key)
    return v if v is not None else default


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    return _env(key, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # Provider
    llm_provider: str = _env("LLM_PROVIDER", "dashscope")  # dashscope | glm | openai

    # Keys
    dashscope_api_key: str = _env("DASHSCOPE_API_KEY", "")
    glm_api_key: str = _env("GLM_API_KEY", "")
    openai_api_key: str = _env("OPENAI_API_KEY", "")
    openai_base_url: str = _env("OPENAI_BASE_URL", "https://api.openai.com/v1")

    # 行为
    screenshot_interval: float = _env_float("SCREENSHOT_INTERVAL", 1.0)
    # 用户 ✗ 忽略时的"高密度观察窗口"采样频率（mss 截屏本身廉价）
    screenshot_interval_neglect: float = _env_float("SCREENSHOT_INTERVAL_NEGLECT", 0.2)
    enable_memory: bool = _env_bool("ENABLE_MEMORY", True)
    memory_top_k: int = _env_int("MEMORY_TOP_K", 3)

    # 桌宠闲聊模式：
    #   static = 内置 12 句循环（零 token 成本）
    #   llm    = LLM 实时生成（自然多样、需调用 chat 模型）
    chitchat_mode: str = _env("CHITCHAT_MODE", "static")
    # 是否在分析模式下也由 LLM 生成"战况吐槽"
    combat_chat: bool = _env_bool("COMBAT_CHAT", False)

    # ---- 训练数据上报（opt-in） ----
    # 用户主动开启才能上报决策样本；默认关闭
    opt_in_training: bool = _env_bool("OPT_IN_TRAINING", False)
    # 中央上报端点（默认占位地址，要改为你自己的后端）
    telemetry_endpoint: str = _env("TELEMETRY_ENDPOINT", "https://ygo-telemetry.example.com/v1/samples")
    # 匿名设备 ID（首次启动自动生成，存入本地）
    @property
    def device_id_path(self) -> Path:
        return ROOT / "data" / "device_id.txt"

    # 路径
    @property
    def db_path(self) -> Path:
        return ROOT / "data" / "decisions.db"


SETTINGS = Settings()


def has_api_key() -> bool:
    """检查当前 provider 是否配置了 key。"""
    if SETTINGS.llm_provider == "dashscope":
        return bool(SETTINGS.dashscope_api_key)
    if SETTINGS.llm_provider == "glm":
        return bool(SETTINGS.glm_api_key)
    if SETTINGS.llm_provider == "openai":
        return bool(SETTINGS.openai_api_key)
    return False
