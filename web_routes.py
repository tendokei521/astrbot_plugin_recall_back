"""
前端配置页的后端 API 路由。
"""
from .napcat_api import napcat


class WebAPIRegistrar:
    """注册前端配置页所需的后端 API 路由。"""

    def __init__(self, config_manager):
        self._cfg = config_manager

    def register(self, context):
        from quart import jsonify, request

        # ── GET groups ─────────────────────────────────────────

        async def handle_get_groups():
            """获取群列表及每个群的转发配置。"""
            if not napcat.is_ready:
                return jsonify({"ok": False, "error": "NapCat not ready", "groups": []})

            resp = await napcat.get_group_list()
            if not resp:
                return jsonify(
                    {"ok": False, "error": "Failed to fetch group list", "groups": []}
                )

            if isinstance(resp, list):
                raw_groups = resp
            elif isinstance(resp, dict):
                raw_groups = resp.get("data", [])
                if not isinstance(raw_groups, list):
                    raw_groups = []
            else:
                raw_groups = []

            forward_cfg = self._cfg.forward_group_configs
            groups = []
            for g in raw_groups:
                gid = str(g.get("group_id", ""))
                if not gid:
                    continue
                cfg = forward_cfg.get(gid, {})
                groups.append({
                    "group_id": gid,
                    "group_name": g.get("group_name", ""),
                    "member_count": g.get("member_count", 0),
                    "max_member_count": g.get("max_member_count", 0),
                    "enabled": cfg.get("enabled", False),
                })

            return jsonify({"ok": True, "groups": groups})

        # ── GET friends ────────────────────────────────────────

        async def handle_get_friends():
            """获取好友列表及每个好友的转发配置。"""
            if not napcat.is_ready:
                return jsonify({"ok": False, "error": "NapCat not ready", "friends": []})

            resp = await napcat.get_friend_list()
            if not resp:
                return jsonify(
                    {"ok": False, "error": "Failed to fetch friend list", "friends": []}
                )

            if isinstance(resp, list):
                raw_friends = resp
            elif isinstance(resp, dict):
                raw_friends = resp.get("data", [])
                if not isinstance(raw_friends, list):
                    raw_friends = []
            else:
                raw_friends = []

            forward_cfg = self._cfg.forward_private_configs
            friends = []
            for f in raw_friends:
                uid = str(f.get("user_id", ""))
                if not uid:
                    continue
                cfg = forward_cfg.get(uid, {})
                friends.append({
                    "user_id": uid,
                    "nickname": f.get("nickname", ""),
                    "remark": f.get("remark", ""),
                    "enabled": cfg.get("enabled", False),
                })

            return jsonify({"ok": True, "friends": friends})

        # ── GET config ─────────────────────────────────────────

        async def handle_get_config():
            """获取当前插件配置。"""
            return jsonify({"ok": True, "config": self._cfg.to_dict()})

        # ── POST config ────────────────────────────────────────

        async def handle_save_config():
            """保存插件配置。"""
            try:
                data = await request.get_json()
            except Exception:
                return jsonify({"ok": False, "error": "Invalid JSON"})

            if data is None:
                return jsonify({"ok": False, "error": "Empty request body"})

            for key, setter in {
                "enable_group_listen": lambda v: setattr(self._cfg, "enable_group_listen", bool(v)),
                "enable_private_listen": lambda v: setattr(self._cfg, "enable_private_listen", bool(v)),
                "enable_parse_forward": lambda v: setattr(self._cfg, "enable_parse_forward", bool(v)),
                "message_retention_minutes": lambda v: setattr(self._cfg, "message_retention_minutes", int(v)),
                "limit_mode": lambda v: setattr(self._cfg, "limit_mode", str(v)),
                "max_messages_per_session": lambda v: setattr(self._cfg, "max_messages_per_session", int(v)),
                "max_total_messages": lambda v: setattr(self._cfg, "max_total_messages", int(v)),
                "enable_expire_delete": lambda v: setattr(self._cfg, "enable_expire_delete", bool(v)),
                "enable_recalled_delete": lambda v: setattr(self._cfg, "enable_recalled_delete", bool(v)),
                "enable_forward_to_group": lambda v: setattr(self._cfg, "enable_forward_to_group", bool(v)),
                "forward_group_configs": lambda v: setattr(self._cfg, "forward_group_configs", v),
                "enable_forward_to_private": lambda v: setattr(self._cfg, "enable_forward_to_private", bool(v)),
                "forward_private_configs": lambda v: setattr(self._cfg, "forward_private_configs", v),
                "enable_merge_forward": lambda v: setattr(self._cfg, "enable_merge_forward", bool(v)),
            }.items():
                if key in data:
                    try:
                        setter(data[key])
                    except (TypeError, ValueError):
                        pass

            await self._cfg.save()
            return jsonify({"ok": True})

        # ── 注册路由 ──────────────────────────────────────────

        context.register_web_api(
            route="astrbot_plugin_recall_back/groups",
            view_handler=handle_get_groups,
            methods=["GET"],
            desc="获取群列表及转发配置",
        )
        context.register_web_api(
            route="astrbot_plugin_recall_back/friends",
            view_handler=handle_get_friends,
            methods=["GET"],
            desc="获取好友列表及转发配置",
        )
        context.register_web_api(
            route="astrbot_plugin_recall_back/config",
            view_handler=handle_get_config,
            methods=["GET"],
            desc="获取插件配置",
        )
        context.register_web_api(
            route="astrbot_plugin_recall_back/config",
            view_handler=handle_save_config,
            methods=["POST"],
            desc="保存插件配置",
        )
