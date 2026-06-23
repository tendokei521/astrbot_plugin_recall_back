"""
统一 NapCat API 封装 + 预加载机制。

预加载流程:
1. on_platform_loaded 事件触发后，自动扫描并缓存 AiocqhttpAdapter 的 bot 实例
2. 若预加载尚未完成，仍支持通过事件对象延迟加载

导入方式: from .napcat_api import napcat, NapCatAPI
"""

import asyncio
from typing import Any

from astrbot.api import logger


class NapCatAPI:
    """封装 NapCat 的独立 API 类。"""

    def __init__(self):
        self._bot_instance: Any | None = None
        self._preload_done = False
        self._preload_event = asyncio.Event()

    @property
    def bot_instance(self) -> Any | None:
        return self._bot_instance

    @property
    def is_ready(self) -> bool:
        """bot 实例是否已就绪。"""
        return self._bot_instance is not None

    def set_bot_instance(self, bot: Any):
        """由预加载机制调用，注入 bot 实例。"""
        self._bot_instance = bot
        self._preload_done = True
        self._preload_event.set()
        logger.info("[NapCat] Bot 实例已完成预加载")

    # ── 内部调用 ──────────────────────────────────────────────

    async def _call_action(self, action: str, **params) -> Any | None:
        """统一 API 调用入口，内部捕获异常，失败返回 None。"""
        if self._bot_instance is None:
            logger.error(f"[NapCat] Bot 实例未加载，无法调用 {action}")
            return None
        try:
            result = await self._bot_instance.api.call_action(action, **params)
            logger.info(f"[NapCat] API {action} 成功 {self.truncate_output(result)}")
            return result or "success"
        except Exception as e:
            logger.error(f"[NapCat] API {action} 异常: {e}")
            return None

    def truncate_output(self, obj, max_len=25):
        s = repr(obj)
        if len(s) <= max_len:
            return s
        truncate_mark = "..."
        # 确保截断标记一定在末尾
        if len(truncate_mark) >= max_len:
            return truncate_mark[:max_len]
        return s[:max_len - len(truncate_mark)] + truncate_mark

    # ── API 方法 ──────────────────────────────────────────────

    async def set_group_sign(self, group_id: int):
        """群签到。"""
        return await self._call_action("set_group_sign", group_id=group_id)

    async def send_group_msg(self, group_id: int, message) -> Any | None:
        """发送群消息。"""
        return await self._call_action(
            "send_group_msg", group_id=group_id, message=message
        )

    async def send_private_msg(self, user_id: int, message) -> Any | None:
        """发送私聊消息。"""
        return await self._call_action(
            "send_private_msg", user_id=user_id, message=message
        )

    async def send_msg(self, message_type: str, **params) -> Any | None:
        """发送消息。"""
        params["message_type"] = message_type
        return await self._call_action("send_msg", **params)

    async def get_group_list(self) -> dict | None:
        """获取群列表。"""
        return await self._call_action("get_group_list")

    async def get_friend_list(self) -> dict | None:
        """获取好友列表。"""
        return await self._call_action("get_friend_list")

    async def get_group_info(self, group_id: int) -> dict | None:
        """获取群信息。"""
        return await self._call_action("get_group_info", group_id=group_id)

    async def set_msg_emoji_like(self, message_id: int, emoji_id: int):
        """设置消息表情表态。"""
        return await self._call_action(
            "set_msg_emoji_like", message_id=message_id, emoji_id=emoji_id
        )

    async def send_poke(self, group_id: int, user_id: int):
        """发送戳一戳。"""
        return await self._call_action("send_poke", group_id=group_id, user_id=user_id)

    async def set_essence_msg(self, message_id: int):
        """设置精华消息。"""
        return await self._call_action("set_essence_msg", message_id=message_id)

    async def delete_essence_msg(self, message_id: int):
        """删除精华消息。"""
        return await self._call_action("delete_essence_msg", message_id=message_id)

    async def get_essence_msg_list(self, group_id: int) -> list:
        """获取精华消息列表。"""
        result = await self._call_action("get_essence_msg_list", group_id=group_id)
        return result.get("data", []) if isinstance(result, dict) else (result or [])

    async def get_stranger_info(self, user_id: int) -> dict:
        """获取陌生人信息。"""
        result = await self._call_action("get_stranger_info", user_id=user_id)
        return result.get("data", {}) if isinstance(result, dict) else (result or {})

    async def set_group_add_request(self, flag: str, approve: bool, reason: str = ""):
        """处理加群请求。"""
        return await self._call_action(
            "set_group_add_request", flag=flag, approve=approve, reason=reason
        )

    async def set_friend_add_request(self, flag: str, approve: bool):
        """处理好友请求。"""
        return await self._call_action(
            "set_friend_add_request", flag=flag, approve=approve
        )

    async def send_forward_msg(self, group_id: int, messages: list):
        """发送合并转发（群聊）。"""
        return await self._call_action(
            "send_group_forward_msg", group_id=group_id, messages=messages
        )

    async def send_private_forward_msg(self, user_id: int, messages: list):
        """发送合并转发（私聊）。"""
        return await self._call_action(
            "send_private_forward_msg", user_id=user_id, messages=messages
        )

    async def preload_napcat(self, context) -> Any | None:
        """预加载 NapCat bot 实例。

        通过 AstrBot 的 PlatformManager 获取 AiocqhttpAdapter 实例，
        取出其内部的 CQHttp bot 对象注入到全局 napcat 单例。

        Args:
            context: AstrBot 上下文对象

        Returns:
            bool: 是否成功预加载 bot 实例
        """
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
            AiocqhttpAdapter,
        )

        try:
            platforms = context.platform_manager.get_insts()
        except Exception as e:
            logger.warning(f"[NapCatPreload] 无法访问 PlatformManager: {e}")
            return False

        for inst in platforms:
            if isinstance(inst, AiocqhttpAdapter):
                bot = inst.bot
                if bot:
                    napcat.set_bot_instance(bot)
                    return True

        #logger.warning("[NapCatPreload] 未找到 AiocqhttpAdapter，bot 将以其他方式加载")
        return False


napcat = NapCatAPI()
