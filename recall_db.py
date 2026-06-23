"""
本地消息存储 — 基于 JSON 文件 + 内存计数器的双层结构。

JSON 结构:
  {
    "data": {
      "total": 123,                       # 总消息数（内存常驻）
      "sessions": {                       # 每会话消息数（内存常驻）
        "group_123456": 50,
        "private_789012": 10
      }
    },
    "<message_id>": {
      "stored_at": 1719123456.789,
      "session_key": "group_123456",       # 用于回源定位会话
      "group_id": "123456",
      "user_id": "789012",
      "user_name": "用户昵称",
      "message": [...],
      "raw_text": "...",
      "is_forward": false,
      "event_type": "message_group"
    }
  }

性能:
  - data 字段始终常驻内存，store/get/delete 无需遍历全量
  - 消息超限时按 stored_at 淘汰最旧消息（会话级 + 全局级）
  - 写操作通过 asyncio.Lock 序列化
"""
import asyncio
import json
import os
import time

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

DB_PATH = os.path.join(
    get_astrbot_plugin_data_path(), "astrbot_plugin_recall_back_db.json"
)


class RecallDB:
    """本地 JSON 消息存储，支持会话/全局上限与 TTL 过期。"""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._db: dict = {}
        self._loaded = False

    # ── 内部：加载与持久化 ──────────────────────────────────────

    def _ensure_loaded(self):
        """首次访问时加载 JSON，拆分 data 与消息。"""
        if self._loaded:
            return

        if os.path.exists(DB_PATH):
            try:
                with open(DB_PATH, "r", encoding="utf-8") as f:
                    self._db = json.load(f)
            except Exception as e:
                logger.error(f"[RecallDB] 加载数据库失败: {e}")
                self._db = {}

        # 确保 data 结构存在
        if "data" not in self._db:
            self._db["data"] = {"total": 0, "sessions": {}}
            # 从已有消息重建计数
            for mid, v in self._db.items():
                if mid == "data":
                    continue
                sk = v.get("session_key", "")
                if sk:
                    self._db["data"]["sessions"][sk] = (
                        self._db["data"]["sessions"].get(sk, 0) + 1
                    )
            self._db["data"]["total"] = sum(
                self._db["data"]["sessions"].values()
            )
            self._save_nolock()

        self._loaded = True

    def _save_nolock(self):
        """无锁写入磁盘（调用方需持有 _lock）。"""
        try:
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            with open(DB_PATH, "w", encoding="utf-8") as f:
                json.dump(self._db, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[RecallDB] 保存数据库失败: {e}")

    async def _save(self):
        """异步安全写入。"""
        async with self._lock:
            self._save_nolock()

    # ── 辅助 ────────────────────────────────────────────────────

    @staticmethod
    def _session_key(data: dict) -> str:
        """从消息数据推导会话键。"""
        gid = data.get("group_id")
        if gid:
            return f"group_{gid}"
        uid = data.get("user_id", "")
        return f"private_{uid}"

    # ── 计数查询（仅读内存，零 IO） ──────────────────────────────

    @property
    def total(self) -> int:
        self._ensure_loaded()
        return self._db["data"]["total"]

    def session_count(self, session_key: str) -> int:
        self._ensure_loaded()
        return self._db["data"]["sessions"].get(session_key, 0)

    # ── CRUD ────────────────────────────────────────────────────

    async def store(
        self,
        message_id: str,
        data: dict,
        *,
        max_per_session: int = 0,
        max_total: int = 0,
    ) -> None:
        """存储一条消息，自动处理超限淘汰。

        Args:
            message_id: 消息 ID
            data: 消息数据
            max_per_session: 单会话上限，0 表示不限
            max_total: 全局上限，0 表示不限
        """
        self._ensure_loaded()
        session_key = self._session_key(data)
        data["session_key"] = session_key
        data["stored_at"] = time.time()

        async with self._lock:
            # 已在缓存中 → 跳过
            if message_id in self._db:
                return

            # 会话上限淘汰
            if max_per_session > 0:
                while self._db["data"]["sessions"].get(session_key, 0) >= max_per_session:
                    if not self._evict_one(session_key=session_key):
                        break

            # 全局上限淘汰
            if max_total > 0:
                while self._db["data"]["total"] >= max_total:
                    if not self._evict_one():
                        break

            # 写入
            self._db[message_id] = data
            self._db["data"]["total"] += 1
            self._db["data"]["sessions"][session_key] = (
                self._db["data"]["sessions"].get(session_key, 0) + 1
            )
            self._save_nolock()

    async def get(self, message_id: str) -> dict | None:
        """获取已存储的消息。"""
        self._ensure_loaded()
        async with self._lock:
            v = self._db.get(message_id)
            if v is not None and v != "data":  # 排除 data 元字段误匹配
                return v
        return None

    async def delete(self, message_id: str) -> bool:
        """删除一条消息，同步更新计数器。"""
        self._ensure_loaded()
        async with self._lock:
            v = self._db.get(message_id)
            if v is None or message_id == "data":
                return False

            session_key = v.get("session_key", "")
            del self._db[message_id]

            self._db["data"]["total"] = max(0, self._db["data"]["total"] - 1)
            if session_key and session_key in self._db["data"]["sessions"]:
                self._db["data"]["sessions"][session_key] = max(
                    0, self._db["data"]["sessions"][session_key] - 1
                )

            self._save_nolock()
            return True

    # ── 淘汰 ────────────────────────────────────────────────────

    def _evict_one(self, session_key: str | None = None) -> bool:
        """淘汰一条最旧消息（调用方需持有 _lock）。

        Args:
            session_key: 若指定则仅在该会话内淘汰，否则全局淘汰

        Returns:
            是否成功淘汰
        """
        oldest_id = None
        oldest_time = float("inf")

        for mid, v in self._db.items():
            if mid == "data":
                continue
            if session_key and v.get("session_key") != session_key:
                continue
            if v.get("stored_at", 0) < oldest_time:
                oldest_time = v["stored_at"]
                oldest_id = mid

        if not oldest_id:
            return False

        v = self._db.pop(oldest_id)
        sk = v.get("session_key", "")
        self._db["data"]["total"] = max(0, self._db["data"]["total"] - 1)
        if sk and sk in self._db["data"]["sessions"]:
            self._db["data"]["sessions"][sk] = max(
                0, self._db["data"]["sessions"][sk] - 1
            )
        return True

    # ── 过期清理 ────────────────────────────────────────────────

    async def cleanup_expired(self, retention_minutes: int) -> int:
        """清理过期消息，返回清理数量。

        同时清理 data.sessions 中归零的会话键。
        """
        self._ensure_loaded()
        now = time.time()
        cutoff = now - retention_minutes * 60

        async with self._lock:
            expired_ids = [
                mid for mid, v in self._db.items()
                if mid != "data" and v.get("stored_at", 0) < cutoff
            ]
            for mid in expired_ids:
                v = self._db.pop(mid)
                sk = v.get("session_key", "")
                if sk and sk in self._db["data"]["sessions"]:
                    self._db["data"]["sessions"][sk] = max(
                        0, self._db["data"]["sessions"][sk] - 1
                    )
            self._db["data"]["total"] = max(
                0, self._db["data"]["total"] - len(expired_ids)
            )

            # 清理归零的会话键
            zero_sessions = [
                k for k, c in self._db["data"]["sessions"].items() if c <= 0
            ]
            for k in zero_sessions:
                del self._db["data"]["sessions"][k]

            if expired_ids:
                self._save_nolock()
                logger.info(f"[RecallDB] 清理了 {len(expired_ids)} 条过期消息")

        return len(expired_ids)

    # ── 统计（调试用） ──────────────────────────────────────────

    def stats(self) -> dict:
        """返回当前存储统计。"""
        self._ensure_loaded()
        return {
            "total": self._db["data"]["total"],
            "sessions": dict(self._db["data"]["sessions"]),
        }


recall_db = RecallDB()
