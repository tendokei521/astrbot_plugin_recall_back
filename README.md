# 防撤回插件

自动备份群聊/私聊消息，在消息被撤回时恢复并转发到指定位置。

## 功能

- **消息监听** — 监听群聊和私聊消息，记录到本地 JSON 数据库
- **撤回检测** — 检测撤回事件，按 message_id 查找原消息
- **转发恢复** — 将撤回的消息（含合并转发消息体）发送到配置的目标群/好友
- **合并转发** — 支持撤回通知 + 消息体合并在同一个合并转发中
- **上限管理** — 支持按会话 / 按总条数的消息缓存上限，自动淘汰最旧消息
- **定时清理** — 到期自动清理过期消息，清理归零的会话键

## 架构

```
main.py          — 入口，注册生命周期钩子
main_handler.py  — 核心业务（消息存储 / 撤回检测 / 转发分发）
recall_db.py     — 本地 JSON 存储 + 内存计数器（会话/全局上限 + TTL 淘汰）
napcat_api.py    — NapCat API 封装（群/私聊消息、合并转发）
config.py        — 线程安全配置读写
web_routes.py    — 前端配置页 API 路由
pages/settings/  — WebUI 配置页
```

## 配置项

### 监听设置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enable_group_listen` | bool | true | 是否监听群聊消息 |
| `enable_private_listen` | bool | true | 是否监听私聊消息 |
| `enable_parse_forward` | bool | true | 是否展开合并转发消息中的嵌套内容 |

### 消息存储

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `message_retention_minutes` | int | 10 | 消息记录时长（分钟） |
| `limit_mode` | str | `"session"` | 上限模式：`disabled` / `session` / `total` |
| `max_messages_per_session` | int | 200 | 单会话（群/私聊）最大缓存条数 |
| `max_total_messages` | int | 5000 | 全局最大缓存条数 |
| `enable_expire_delete` | bool | true | 消息过期时是否自动删除 |
| `enable_recalled_delete` | bool | true | 撤回恢复后是否从本地删除 |

### 转发设置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enable_forward_to_group` | bool | false | 是否转发到群聊 |
| `forward_group_configs` | dict | `{}` | 转发目标群列表（勾选模式） |
| `enable_forward_to_private` | bool | false | 是否转发到私聊 |
| `forward_private_configs` | dict | `{}` | 转发目标好友列表（勾选模式） |
| `enable_merge_forward` | bool | true | 是否使用合并转发（撤回通知+消息体在同一合并转发中） |

## 数据流

```
消息事件 → on_event(ALL)
  ├─ post_type="message"  → _on_message  → recall_db.store()
  │                           ├─ 会话上限检查 → 淘汰最旧
  │                           └─ 全局上限检查 → 淘汰最旧
  └─ post_type="notice"
       └─ notice_type="group_recall" | "friend_recall"
            → _on_notice
              ├─ recall_db.get(message_id) → 命中
              ├─ _build_recall_tip() + _build_message_nodes() → 构建转发节点
              └─ _dispatch_forward() → 群/私聊目标
                   ├─ merge: 合并转发
                   └─ separate: 文本通知 + 合并转发消息体
```

## 依赖

- AstrBot ≥ 4.16
- aiocqhttp (NapCat / LLOneBot)

## 安装

将插件目录放入 `data/plugins/` 下，重启 AstrBot 即可。

```bash
cd data/plugins
git clone https://github.com/TendoKei/astrbot_plugin_recall_back
```

## 许可证

MIT
