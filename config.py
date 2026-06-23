"""
配置管理 — 线程安全的单一配置源。
"""
import asyncio
import json
import os

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_config_path

DEFAULT_CONFIG = {
    # 监听设置
    "enable_group_listen": True,
    "enable_private_listen": True,
    "enable_parse_forward": True,
    # 消息存储
    "message_retention_minutes": 10,
    "limit_mode": "session",
    "max_messages_per_session": 200,
    "max_total_messages": 5000,
    "enable_expire_delete": True,
    "enable_recalled_delete": True,
    # 转发设置
    "enable_forward_to_group": False,
    "forward_group_configs": {},
    "enable_forward_to_private": False,
    "forward_private_configs": {},
    "enable_merge_forward": True,
}

ASTRBOT_CONFIG_PATH = os.path.join(
    get_astrbot_config_path(), "astrbot_plugin_recall_back_config.json"
)


class ConfigManager:
    """插件配置的编辑与读写（asyncio.Lock 保证线程安全）。"""

    def __init__(self, config):
        self._config = config
        self._lock = asyncio.Lock()

    # ── 监听设置 ──────────────────────────────────────────────

    @property
    def enable_group_listen(self) -> bool:
        return self._config.get("enable_group_listen", True)

    @enable_group_listen.setter
    def enable_group_listen(self, value: bool):
        self._config["enable_group_listen"] = value

    @property
    def enable_private_listen(self) -> bool:
        return self._config.get("enable_private_listen", True)

    @enable_private_listen.setter
    def enable_private_listen(self, value: bool):
        self._config["enable_private_listen"] = value

    @property
    def enable_parse_forward(self) -> bool:
        return self._config.get("enable_parse_forward", True)

    @enable_parse_forward.setter
    def enable_parse_forward(self, value: bool):
        self._config["enable_parse_forward"] = value

    # ── 消息存储 ──────────────────────────────────────────────

    @property
    def message_retention_minutes(self) -> int:
        return self._config.get("message_retention_minutes", 10)

    @message_retention_minutes.setter
    def message_retention_minutes(self, value: int):
        self._config["message_retention_minutes"] = value

    @property
    def limit_mode(self) -> str:
        return self._config.get("limit_mode", "session")

    @limit_mode.setter
    def limit_mode(self, value: str):
        self._config["limit_mode"] = value

    @property
    def max_messages_per_session(self) -> int:
        return self._config.get("max_messages_per_session", 200)

    @max_messages_per_session.setter
    def max_messages_per_session(self, value: int):
        self._config["max_messages_per_session"] = value

    @property
    def max_total_messages(self) -> int:
        return self._config.get("max_total_messages", 5000)

    @max_total_messages.setter
    def max_total_messages(self, value: int):
        self._config["max_total_messages"] = value

    @property
    def enable_expire_delete(self) -> bool:
        return self._config.get("enable_expire_delete", True)

    @enable_expire_delete.setter
    def enable_expire_delete(self, value: bool):
        self._config["enable_expire_delete"] = value

    @property
    def enable_recalled_delete(self) -> bool:
        return self._config.get("enable_recalled_delete", True)

    @enable_recalled_delete.setter
    def enable_recalled_delete(self, value: bool):
        self._config["enable_recalled_delete"] = value

    # ── 转发设置 ──────────────────────────────────────────────

    @property
    def enable_forward_to_group(self) -> bool:
        return self._config.get("enable_forward_to_group", False)

    @enable_forward_to_group.setter
    def enable_forward_to_group(self, value: bool):
        self._config["enable_forward_to_group"] = value

    @property
    def forward_group_configs(self) -> dict:
        return self._config.get("forward_group_configs", {})

    @forward_group_configs.setter
    def forward_group_configs(self, value: dict):
        self._config["forward_group_configs"] = value

    @property
    def enable_forward_to_private(self) -> bool:
        return self._config.get("enable_forward_to_private", False)

    @enable_forward_to_private.setter
    def enable_forward_to_private(self, value: bool):
        self._config["enable_forward_to_private"] = value

    @property
    def forward_private_configs(self) -> dict:
        return self._config.get("forward_private_configs", {})

    @forward_private_configs.setter
    def forward_private_configs(self, value: dict):
        self._config["forward_private_configs"] = value

    @property
    def enable_merge_forward(self) -> bool:
        return self._config.get("enable_merge_forward", True)

    @enable_merge_forward.setter
    def enable_merge_forward(self, value: bool):
        self._config["enable_merge_forward"] = value

    # ── 序列化 ──────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "enable_group_listen": self.enable_group_listen,
            "enable_private_listen": self.enable_private_listen,
            "enable_parse_forward": self.enable_parse_forward,
            "message_retention_minutes": self.message_retention_minutes,
            "limit_mode": self.limit_mode,
            "max_messages_per_session": self.max_messages_per_session,
            "max_total_messages": self.max_total_messages,
            "enable_expire_delete": self.enable_expire_delete,
            "enable_recalled_delete": self.enable_recalled_delete,
            "enable_forward_to_group": self.enable_forward_to_group,
            "forward_group_configs": self.forward_group_configs,
            "enable_forward_to_private": self.enable_forward_to_private,
            "forward_private_configs": self.forward_private_configs,
            "enable_merge_forward": self.enable_merge_forward,
        }

    # ── 持久化 ──────────────────────────────────────────────

    async def save(self):
        """将当前配置写入磁盘。"""
        async with self._lock:
            if hasattr(self._config, "save_config"):
                self._config.save_config()
            else:
                logger.warning("[ConfigManager] save_config 不可用，配置未持久化")


class AstrPluginConfig(dict):
    """从配置文件中加载的配置，支持直接通过点号操作符访问根配置项。
    - 修改自AstrBotConfig
    - 初始化时会将传入的 default_config 与配置文件进行比对，如果配置文件中缺少配置项则会自动插入默认值并进行一次写入操作
    - 如果配置文件路径对应的文件不存在，则会自动创建并写入默认配置。
    """

    config_path: str
    default_config: dict
    ignore_default: bool = False

    def __init__(
        self,
        config_path: str = ASTRBOT_CONFIG_PATH,
        default_config: dict = DEFAULT_CONFIG,
        ignore_default: bool = True,
    ) -> None:
        super().__init__()

        object.__setattr__(self, "config_path", config_path)
        object.__setattr__(self, "default_config", default_config)
        object.__setattr__(self, "ignore_default", ignore_default)

        if not self.check_exist():
            with open(config_path, "w", encoding="utf-8-sig") as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
                object.__setattr__(self, "first_deploy", True)

        with open(config_path, encoding="utf-8-sig") as f:
            conf_str = f.read()
            if conf_str.startswith("﻿"):
                conf_str = conf_str[1:]
            conf = json.loads(conf_str)

        has_new = self.check_config_integrity(default_config, conf)
        self.update(conf)
        if has_new:
            self.save_config()

        self.update(conf)

    def check_config_integrity(self, refer_conf: dict, conf: dict, path=""):
        """检查配置完整性，如果有新的配置项或顺序不一致则返回 True"""
        has_new = False
        new_conf = {}

        for key, value in refer_conf.items():
            if key not in conf:
                logger.info("Config key missing; added default.")
                new_conf[key] = value
                has_new = True
            elif conf[key] is None:
                new_conf[key] = value
                has_new = True
            elif isinstance(value, dict):
                if not isinstance(conf[key], dict):
                    new_conf[key] = value
                    has_new = True
                elif not value:
                    new_conf[key] = conf[key]
                    has_new = True
                else:
                    child_has_new = self.check_config_integrity(
                        value, conf[key],
                        path + "." + key if path else key,
                    )
                    new_conf[key] = conf[key]
                    has_new |= child_has_new
            else:
                new_conf[key] = conf[key]

        for key in list(conf.keys()):
            if key not in refer_conf:
                logger.info("Config key removed: %s", path + "." + key if path else key)
                has_new = True

        if list(conf.keys()) != list(new_conf.keys()):
            logger.info("Config key order fixed: %s" % (path or "root"))
            has_new = True

        conf.clear()
        conf.update(new_conf)
        return has_new

    def save_config(self, replace_config: dict | None = None) -> None:
        if replace_config:
            self.update(replace_config)
        with open(self.config_path, "w", encoding="utf-8-sig") as f:
            json.dump(self, f, indent=2, ensure_ascii=False)

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            return None

    def __delattr__(self, key) -> None:
        try:
            del self[key]
            self.save_config()
        except KeyError:
            raise AttributeError(f"没有找到 Key: '{key}'")

    def __setattr__(self, key, value) -> None:
        self[key] = value

    def check_exist(self) -> bool:
        if not self.config_path:
            return False
        return os.path.exists(self.config_path)
