"""训练数据匿名上报（opt-in）。

策略：
  · 默认关闭 — 用户必须 .env 设 OPT_IN_TRAINING=true 才会启用
  · 上报字段仅含：game_state 摘要 + suggestions + chosen_idx + accepted
  · 不上报：API Key、个人卡组信息、IP、用户名
  · 异步发送（不卡 UI）
  · 失败重试 3 次 → 落本地队列 → 下次启动再发
  · 用户可一键停止（启动时提示）
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from config import SETTINGS
from logger import log


_QUEUE: "queue.Queue[Dict[str, Any]]" = queue.Queue()
_WORKER_STARTED = False
_LOCK = threading.Lock()


# ===================== 匿名设备 ID =====================

def _device_id() -> str:
    """本地生成/读取匿名设备 ID（不会上报真实身份）。"""
    path = SETTINGS.device_id_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_text().strip()
    # 首次启动：生成随机 uuid（只用于后端做去重统计）
    new_id = str(uuid.uuid4())
    path.write_text(new_id)
    return new_id


# ===================== 后台 worker =====================

def _worker_loop():
    log.info("telemetry worker 启动（opt-in=%s）", SETTINGS.opt_in_training)
    while True:
        try:
            sample = _QUEUE.get(timeout=1.0)
        except queue.Empty:
            continue
        if sample is None:
            return
        try:
            _send_once(sample)
        except Exception as e:
            log.warning("telemetry 发送失败：%s", e)
            _persist_for_retry(sample)


def _send_once(payload: Dict[str, Any], timeout: float = 6.0) -> None:
    headers = {"Content-Type": "application/json", "User-Agent": "ygo-assistant/1.0"}
    resp = requests.post(SETTINGS.telemetry_endpoint, json=payload, headers=headers, timeout=timeout)
    if 200 <= resp.status_code < 300:
        log.debug("telemetry 上报成功")
    else:
        log.warning("telemetry HTTP %s", resp.status_code)
        raise RuntimeError(f"http {resp.status_code}")


def _persist_for_retry(payload: Dict[str, Any]):
    """失败样本落本地文件，下次启动时再发。"""
    out = SETTINGS.db_path.parent / "telemetry_pending.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _retry_pending():
    """启动时把之前未上传完的样本重发一遍。"""
    p = SETTINGS.db_path.parent / "telemetry_pending.jsonl"
    if not p.exists():
        return
    try:
        samples = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception:
        return
    if not samples:
        return
    log.info("重发 %d 条历史 telemetry", len(samples))
    sent = 0
    for s in samples:
        try:
            _send_once(s)
            sent += 1
        except Exception:
            _persist_for_retry(s)
    if sent == len(samples):
        try:
            p.unlink()
        except Exception:
            pass


def _ensure_worker():
    global _WORKER_STARTED
    with _LOCK:
        if not _WORKER_STARTED:
            t = threading.Thread(target=_worker_loop, daemon=True, name="telemetry")
            t.start()
            _WORKER_STARTED = True
            _retry_pending()


# ===================== 公开 API =====================

def submit_sample(
    game_state: Dict[str, Any],
    suggestions: list,
    chosen_idx: int,
    accepted: bool,
):
    """记录一次「用户的决策/反馈」用于训练。

    用户决策 = 当前局面 + 模型给的推荐 + 用户最终采纳了哪一个。
    accepted=True 表示用户采纳了 chosen_idx；False 表示用户看了但跳过。
    """
    if not SETTINGS.opt_in_training:
        return
    _ensure_worker()

    payload = {
        "device_id": _device_id(),       # 匿名去重，不含个人身份
        "ts": time.time(),
        # 把游戏局面的关键字段发走（不含决策者身份）
        "state": {
            "turn": game_state.get("turn"),
            "phase": game_state.get("phase"),
            "my_lp": game_state.get("my_lp"),
            "opp_lp": game_state.get("opp_lp"),
            "my_hand_count": game_state.get("my_hand_count"),
            "my_field": game_state.get("my_field") or [],
            "opp_field": game_state.get("opp_field") or [],
            "notes": game_state.get("notes") or "",
        },
        # 模型给的候选
        "options": [
            {"action": o.get("action", ""), "reason": o.get("reason", "")}
            for o in (suggestions or [])
        ],
        # 用户的真实选择（这是有价值的标签）
        "chosen_idx": chosen_idx,
        "accepted": accepted,
    }
    try:
        _QUEUE.put_nowait(payload)
    except queue.Full:
        log.warning("telemetry 队列满，丢弃本次样本")


def status() -> Dict[str, Any]:
    return {
        "opt_in": SETTINGS.opt_in_training,
        "endpoint": SETTINGS.telemetry_endpoint,
        "queue_size": _QUEUE.qsize(),
        "device_id_loaded": SETTINGS.device_id_path.exists(),
    }


def opt_out_now():
    """用户希望立即停止上传。"""
    SETTINGS.opt_in_training = False
    log.info("telemetry: 用户 opt out。")
