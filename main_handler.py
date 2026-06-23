"""
防撤回 — 核心处理逻辑。

流程:
  1. 收到消息事件 → 存入本地 recall_db
  2. 收到撤回事件 → 从 recall_db 按 message_id 查找原消息
  3. 构建转发消息节点 → 发送到目标群聊/私聊
"""
import asyncio

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from .config import ConfigManager
from .napcat_api import napcat
from .recall_db import recall_db


class RecallBackHandler:
    """防撤回核心处理类。"""

    def __init__(self, config_manager: ConfigManager):
        self._cfg = config_manager
        self._cleanup_task: asyncio.Task | None = None

    # ── 生命周期 ──────────────────────────────────────────────

    async def start_cleanup(self):
        """启动定时清理任务（每60秒检查一次）。"""
        if self._cleanup_task:
            return
        self._cleanup_task = asyncio.create_task(self.cleanup_loop())

    async def stop_cleanup(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None

    async def cleanup_loop(self):
        while True:
            try:
                await asyncio.sleep(60)
                if self._cfg.enable_expire_delete:
                    await recall_db.cleanup_expired(
                        self._cfg.message_retention_minutes
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[RecallBack] 清理循环异常: {e}")

    # ── 主入口 ──────────────────────────────────────────────

    async def handle_event(self, event: AstrMessageEvent):
        """根据事件类型分发到存储或撤回处理。"""
        msg_obj = event.message_obj
        raw = getattr(msg_obj, "raw_message", None)
        print(event.message_obj.raw_message)
        if raw is None:
            return
        post_type = raw.post_type

        if post_type == "message":
            await self._on_message(event, raw)
        elif post_type == "notice":
            if raw.notice_type in ("group_recall", "friend_recall"):
                await self._on_notice(event, raw)

    # ── 消息存储 ──────────────────────────────────────────────

    async def _on_message(self, _event: AstrMessageEvent, raw: dict):
        """收到普通消息 → 存入本地数据库。"""
        msg_type = raw.get("message_type", "")

        # 过滤：群聊 / 私聊
        if msg_type == "group" and not self._cfg.enable_group_listen:
            return
        if msg_type == "private" and not self._cfg.enable_private_listen:
            return

        message_id = raw.get("message_id")
        if not message_id:
            return

        # 不存储自己发送的消息
        self_id = raw.get("self_id")
        user_id = raw.get("user_id")
        if str(self_id) == str(user_id):
            return

        # 解析消息内容
        message_chain = raw.get("message", [])
        is_forward = self._is_forward_message(message_chain)
        user_name = self._get_sender_name(raw)

        if is_forward and self._cfg.enable_parse_forward:
            message_chain = self._unpack_forward_content(message_chain)

        mode = self._cfg.limit_mode
        await recall_db.store(
            str(message_id),
            {
                "group_id": raw.get("group_id"),
                "user_id": user_id,
                "user_name": user_name,
                "message": message_chain,
                "raw_text": raw.get("raw_message", ""),
                "is_forward": is_forward,
                "event_type": f"message_{msg_type}",
            },
            max_per_session=self._cfg.max_messages_per_session if mode == "session" else 0,
            max_total=self._cfg.max_total_messages if mode == "total" else 0,
        )

    # ── 撤回处理 ──────────────────────────────────────────────

    async def _on_notice(self, _event: AstrMessageEvent, raw: dict):
        """收到通知事件 → 如果是撤回则查找原消息并转发。"""
        notice_type = raw.get("notice_type", "")

        if notice_type not in ("group_recall", "friend_recall"):
            return

        message_id = str(raw.get("message_id", ""))
        if not message_id:
            return

        stored = await recall_db.get(message_id)
        if not stored:
            logger.debug(f"[RecallBack] 消息 {message_id} 未缓存，无法恢复")
            return

        logger.info(f"[RecallBack] 检测到撤回事件 message_id={message_id}")

        # 构建转发消息节点
        recall_tip = self._build_recall_tip(raw, stored)
        msg_nodes = self._build_message_nodes(stored)
        forward_nodes = [recall_tip] + msg_nodes

        # 发送到目标位置
        await self._dispatch_forward(forward_nodes)

        # 撤回后删除
        if self._cfg.enable_recalled_delete:
            await recall_db.delete(message_id)

    # ── 转发分发 ──────────────────────────────────────────────

    async def _dispatch_forward(self, nodes: list):
        """将构建好的转发消息分发到配置的目标群/私聊。"""
        if self._cfg.enable_merge_forward:
            # 合并转发：撤回通知 + 消息体在同一个合并转发中
            if self._cfg.enable_forward_to_group:
                for gid, cfg in self._cfg.forward_group_configs.items():
                    if cfg.get("enabled", False):
                        await napcat.send_forward_msg(int(gid), nodes)
            if self._cfg.enable_forward_to_private:
                for uid, cfg in self._cfg.forward_private_configs.items():
                    if cfg.get("enabled", False):
                        await napcat.send_private_forward_msg(int(uid), nodes)
        else:
            # 分开发送：撤回通知为文本，消息体为合并转发
            tip_node = nodes[0]
            msg_nodes = nodes[1:]

            tip_text = tip_node["data"]["content"]

            if self._cfg.enable_forward_to_group:
                for gid, cfg in self._cfg.forward_group_configs.items():
                    if not cfg.get("enabled", False):
                        continue
                    if tip_text:
                        await napcat.send_group_msg(int(gid), tip_text)
                    if msg_nodes:
                        await napcat.send_forward_msg(int(gid), msg_nodes)

            if self._cfg.enable_forward_to_private:
                for uid, cfg in self._cfg.forward_private_configs.items():
                    if not cfg.get("enabled", False):
                        continue
                    if tip_text:
                        await napcat.send_private_msg(int(uid), tip_text)
                    if msg_nodes:
                        await napcat.send_private_forward_msg(int(uid), msg_nodes)

    # ── 消息节点构建 ──────────────────────────────────────────

    def _build_recall_tip(self, raw_recall: dict, stored: dict) -> dict:
        """构建撤回提示节点。"""
        group_id = raw_recall.get("group_id", "")
        operator_id = str(raw_recall.get("operator_id", ""))
        stored_uid = str(stored.get("user_id", ""))

        if not group_id:
            content = f"{operator_id}撤回了一条私信消息"
        elif operator_id == stored_uid:
            content = f"群{group_id}的{operator_id}撤回了一条消息："
        else:
            content = f"群{group_id}的{operator_id}撤回了{stored_uid}的一条消息："

        return {
            "type": "node",
            "data": {
                "name": "撤回通知",
                "uin": 10000,
                "content": content,
            }
        }

    def _build_message_nodes(self, stored: dict) -> list[dict]:
        """根据存储的消息数据构建转发节点列表。"""
        user_name = stored.get("user_name", "")
        user_id = stored.get("user_id", "")
        message = stored.get("message", [])
        is_forward = stored.get("is_forward", False)

        if not is_forward:
            return [{
                "type": "node",
                "data": {
                    "name": user_name,
                    "uin": int(user_id) if user_id else 10000,
                    "content": message if message else stored.get("raw_text", ""),
                }
            }]
        else:
            # 合并转发消息体直接作为嵌套节点
            return [{
                "type": "node",
                "data": {
                    "name": user_name,
                    "uin": int(user_id) if user_id else 10000,
                    "content": message,
                }
            }]

    # ── 辅助方法 ──────────────────────────────────────────────

    @staticmethod
    def _get_sender_name(raw: dict) -> str:
        """从原始消息中提取发送者名称。"""
        sender = raw.get("sender", {})
        return sender.get("card") or sender.get("nickname", "")

    @staticmethod
    def _is_forward_message(message_chain: list) -> bool:
        """判断消息链是否包含合并转发。"""
        for seg in message_chain:
            if isinstance(seg, dict) and seg.get("type") == "forward":
                return True
        return False

    def _unpack_forward_content(self, message_chain: list) -> list:
        """递归展开合并转发消息内容为嵌套节点。"""
        result = []
        for seg in message_chain:
            if isinstance(seg, dict) and seg.get("type") == "forward":
                forward_data = seg.get("data", {}).get("content", [])
                result.extend(self._convert_forward_nodes(forward_data))
            else:
                result.append(seg)
        return result

    def _convert_forward_nodes(self, forward_data: list) -> list[dict]:
        """将 NapCat 合并转发内部节点转为转发消息节点格式。"""
        nodes = []
        for msg in forward_data:
            sender = msg.get("sender", {})
            user_name = sender.get("card") or sender.get("nickname", "")
            user_id = sender.get("user_id", "")
            sub_messages = msg.get("message", [])

            # 检查是否嵌套了进一步的合并转发
            has_nested = any(
                isinstance(s, dict) and s.get("type") == "forward"
                for s in sub_messages
            )

            if has_nested:
                nested_nodes = []
                for s in sub_messages:
                    if isinstance(s, dict) and s.get("type") == "forward":
                        nested = s.get("data", {}).get("content", [])
                        nested_nodes.extend(self._convert_forward_nodes(nested))
                nodes.append({
                    "type": "node",
                    "data": {
                        "name": user_name,
                        "uin": int(user_id) if user_id else 10000,
                        "content": nested_nodes,
                    }
                })
            else:
                nodes.append({
                    "type": "node",
                    "data": {
                        "name": user_name,
                        "uin": int(user_id) if user_id else 10000,
                        "content": sub_messages,
                    }
                })
        return nodes
