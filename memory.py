"""决策记忆 - SQLite 持久化用户的采纳/忽略反馈。

表结构：
  decisions(
    id, ts,
    game_state_json,        # 局面摘要（LLM 提取的结构化 JSON）
    image_hash,             # 帧图指纹（避免完全相同帧重复入库）
    suggestions_json,       # 当时给出的若干建议
    chosen_idx,             -1 表示忽略
    accepted                bool
  )
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import SETTINGS


_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    image_hash TEXT,
    game_state_json TEXT NOT NULL,
    suggestions_json TEXT NOT NULL,
    chosen_idx INTEGER NOT NULL,
    accepted INTEGER NOT NULL,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts);

-- 用户拒绝 AI 推荐后，watcher 自动观察到的「用户实际做了什么」
CREATE TABLE IF NOT EXISTS decisions_neglected (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    decision_id INTEGER,                  -- 反向链接到 decisions 表
    rejected_idx INTEGER,                 -- 用户当时拒绝的是哪一条
    state_before_json TEXT NOT NULL,       -- 拒绝时的局面
    state_after_json TEXT,                 -- 监测到变化后的局面
    ai_suggestions_json TEXT NOT NULL,     -- AI 当时的所有候选
    actual_action_json TEXT,               -- LLM 推断「用户实际做了什么」
    confidence REAL,
    detected_change TEXT,                 -- 检测到的具体变化字段（lp/field/turn 等）
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_neglected_ts ON decisions_neglected(ts);
"""


class Memory:
    """决策记忆库（线程安全）。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or SETTINGS.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        with self._lock, self._connect() as conn:
            conn.executescript(_CREATE_SQL)

    @contextmanager
    def _tx(self):
        with self._lock:
            conn = self._connect()
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    # ============== 写入 ==============
    def record(
        self,
        image_hash: str,
        game_state: Dict[str, Any],
        suggestions: List[Dict[str, Any]],
        chosen_idx: int,
        accepted: bool,
        note: str = "",
    ) -> int:
        ts = time.time()
        with self._tx() as conn:
            cur = conn.execute(
                """INSERT INTO decisions
                   (ts, image_hash, game_state_json, suggestions_json, chosen_idx, accepted, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    ts,
                    image_hash,
                    json.dumps(game_state, ensure_ascii=False),
                    json.dumps(suggestions, ensure_ascii=False),
                    chosen_idx,
                    1 if accepted else 0,
                    note,
                ),
            )
            return cur.lastrowid

    # ============== 检索 ==============
    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM decisions ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def acceptance_stats(self) -> Dict[str, Any]:
        """统计采纳率，用来刻画用户风格画像。"""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
            accepted = conn.execute(
                "SELECT COUNT(*) FROM decisions WHERE accepted=1"
            ).fetchone()[0]
        return {
            "total": total,
            "accepted": accepted,
            "rate": (accepted / total) if total else 0.0,
        }

    def similar_states(self, game_state: Dict[str, Any], top_k: int = 3) -> List[Dict[str, Any]]:
        """最朴素的相似度：phase + turn 相同的最近几条。

        真要强大可以加 vector embedding（Phase 2）。
        这里用关键字段过滤即可减少 prompt 长度。
        """
        key_fields = {
            k: game_state.get(k)
            for k in ("turn", "phase", "my_lp", "opp_lp")
            if k in game_state
        }
        if not key_fields:
            return []

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM decisions ORDER BY ts DESC LIMIT 200"
            ).fetchall()

        def score(row: Dict[str, Any]) -> int:
            try:
                gs = json.loads(row["game_state_json"])
            except Exception:
                return -1
            s = 0
            for k, v in key_fields.items():
                if gs.get(k) == v:
                    s += 1
            return s

        scored = [(score(dict(r)), dict(r)) for r in rows]
        scored = [x for x in scored if x[0] >= 0]
        scored.sort(key=lambda x: (-x[0], -x[1]["ts"]))
        return [r for _, r in scored[:top_k]]

    # ============== 负样本（用户拒绝后的实际行为）==============

    def record_neglected(
        self,
        decision_id: Optional[int],
        rejected_idx: int,
        state_before: Dict[str, Any],
        state_after: Optional[Dict[str, Any]],
        ai_suggestions: List[Dict[str, Any]],
        actual_action: Optional[Dict[str, Any]],
        confidence: float = 0.0,
        detected_change: str = "",
        note: str = "",
    ) -> int:
        ts = time.time()
        with self._tx() as conn:
            cur = conn.execute(
                """INSERT INTO decisions_neglected
                   (ts, decision_id, rejected_idx, state_before_json, state_after_json,
                    ai_suggestions_json, actual_action_json, confidence, detected_change, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ts,
                    decision_id,
                    rejected_idx,
                    json.dumps(state_before, ensure_ascii=False),
                    json.dumps(state_after, ensure_ascii=False) if state_after else None,
                    json.dumps(ai_suggestions, ensure_ascii=False),
                    json.dumps(actual_action, ensure_ascii=False) if actual_action else None,
                    confidence,
                    detected_change,
                    note,
                ),
            )
            return cur.lastrowid

    def recent_neglected(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM decisions_neglected ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def last_neglected_update_action(self, row_id: int, actual_action: Dict[str, Any],
                                      confidence: float, detected_change: str) -> None:
        """异步回调：watcher 推断完成后回填结果。"""
        with self._tx() as conn:
            conn.execute(
                """UPDATE decisions_neglected
                   SET actual_action_json=?, confidence=?, detected_change=?
                   WHERE id=?""",
                (
                    json.dumps(actual_action, ensure_ascii=False),
                    confidence,
                    detected_change,
                    row_id,
                ),
            )
