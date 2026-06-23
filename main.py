"""
防撤回插件 — 入口。

架构:
  main.py          — 入口：组装模块，注册框架钩子
  napcat_api.py    — NapCat API 封装 + 实例捕获
  main_handler.py  — 防撤回业务逻辑（存储、撤回检测、转发）
  web_routes.py    — 前端配置页的后端 API 路由
  config.py        — 线程安全配置读写
  recall_db.py     — 本地消息存储（JSON + TTL 清理）

功能:
  1. 监听群聊/私聊消息 → 存入本地 JSON
  2. 接收撤回事件 → 按 message_id 查找原消息
  3. 构建转发消息体 → 发送到配置的目标群/私聊
"""
import os

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.utils.astrbot_path import get_astrbot_config_path

from .config import DEFAULT_CONFIG, AstrPluginConfig, ConfigManager
from .main_handler import RecallBackHandler
from .napcat_api import napcat
from .web_routes import WebAPIRegistrar


class RecallBack(Star):
    """防撤回插件。"""

    def __init__(self, context: Context):
        super().__init__(context)

        self._cfg = ConfigManager(AstrPluginConfig(
            os.path.join(get_astrbot_config_path(), "astrbot_plugin_recall_back_config.json"),
            DEFAULT_CONFIG,
            True,
        ))
        self._handler = RecallBackHandler(config_manager=self._cfg)
        self._web_api = WebAPIRegistrar(config_manager=self._cfg)
        self._web_api.register(self.context)

    # ── 生命周期 ─────────────────────────────────────────────

    async def _ensure_napcat(self):
        """调用napcat方法，加载平台实例"""
        if napcat.is_ready:
            return
        try:
            await napcat.preload_napcat(self.context)
        except Exception as e:
            logger.warning(f"[RecallBack] NapCat实例加载失败: {e}")

    @filter.on_platform_loaded()
    async def on_platform_loaded(self):
        await self._ensure_napcat()

    @filter.on_plugin_error()
    async def on_plugin_error(self):
        logger.debug(f"[RecallBack] 未知的插件错误，napcat:{napcat.is_ready}")

    async def initialize(self):
        await self._ensure_napcat()
        await self._handler.start_cleanup()

    async def terminate(self):
        await self._handler.stop_cleanup()
        await self._cfg.save()

    # ── 消息处理 ─────────────────────────────────────────────

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_event(self, event: AstrMessageEvent):
        """自动监听所有消息/撤回事件。"""
        await self._handler.handle_event(event)
