/**
 * 防撤回 — WebUI 配置页脚本
 */
(function () {
  "use strict";

  const bridge = window.AstrBotPluginPage;

  const $  = function (sel) { return document.querySelector(sel); };
  const $$ = function (sel) { return document.querySelectorAll(sel); };

  // ═══════════════════════════════════════════════════════════
  // 全局状态
  // ═══════════════════════════════════════════════════════════

  const state = {
    config:  {},
    groups:  [],
    friends: [],
  };

  // ═══════════════════════════════════════════════════════════
  // DOM 引用
  // ═══════════════════════════════════════════════════════════

  const dom = {
    loading:  $("#loading"),
    error:    $("#error"),
    mainForm: $("#mainForm"),

    // 卡片1：监听设置
    enableGroupListen:   $("#enableGroupListen"),
    enablePrivateListen: $("#enablePrivateListen"),
    enableParseForward:  $("#enableParseForward"),

    // 卡片2：消息存储
    messageRetentionMinutes: $("#messageRetentionMinutes"),
    limitMode:              $("#limitMode"),
    sessionLimitGroup:      $("#sessionLimitGroup"),
    totalLimitGroup:        $("#totalLimitGroup"),
    maxMessagesPerSession:  $("#maxMessagesPerSession"),
    maxTotalMessages:       $("#maxTotalMessages"),
    enableExpireDelete:      $("#enableExpireDelete"),
    enableRecalledDelete:    $("#enableRecalledDelete"),

    // 卡片3：转发到群聊
    enableForwardToGroup:  $("#enableForwardToGroup"),
    groupList:             $("#groupList"),
    groupListContainer:    $("#groupListContainer"),
    recallGroupCollapseBtn: $("#recallGroupCollapseBtn"),
    refreshBtn:            $("#refreshBtn"),

    // 卡片4：转发到私聊
    enableForwardToPrivate:  $("#enableForwardToPrivate"),
    friendList:              $("#friendList"),
    friendListContainer:     $("#friendListContainer"),
    recallFriendCollapseBtn: $("#recallFriendCollapseBtn"),
    refreshFriendsBtn:       $("#refreshFriendsBtn"),

    // 卡片5：合并转发
    enableMergeForward: $("#enableMergeForward"),

    // 保存
    saveBtn:    $("#saveBtn"),
    saveStatus: $("#saveStatus"),
  };

  // ═══════════════════════════════════════════════════════════
  // 初始化
  // ═══════════════════════════════════════════════════════════

  async function init() {
    try {
      await bridge.ready();
      dom.loading.textContent = "正在加载配置...";
      await loadConfig();
      await loadGroups();
      await loadFriends();
      dom.loading.style.display = "none";
      dom.mainForm.style.display = "block";
      renderAll();
      bindAllEvents();
    } catch (err) {
      console.error("[RecallBack Page] 初始化失败:", err);
      dom.loading.style.display = "none";
      showError("页面初始化失败: " + (err.message || "未知错误"));
    }
  }

  function showError(msg) {
    dom.error.style.display = "block";
    dom.error.textContent = "⚠ " + msg;
  }

  function hideError() {
    dom.error.style.display = "none";
  }

  // ═══════════════════════════════════════════════════════════
  // 数据加载
  // ═══════════════════════════════════════════════════════════

  async function loadConfig() {
    try {
      const resp = await bridge.apiGet("config", {});
      if (!resp || !resp.ok) return;
      state.config = resp.config || {};

      dom.enableGroupListen.checked    = state.config.enable_group_listen !== false;
      dom.enablePrivateListen.checked  = state.config.enable_private_listen !== false;
      dom.enableParseForward.checked   = state.config.enable_parse_forward !== false;
      dom.messageRetentionMinutes.value = state.config.message_retention_minutes || 10;
      dom.limitMode.value             = state.config.limit_mode || "session";
      dom.maxMessagesPerSession.value  = state.config.max_messages_per_session ?? 200;
      dom.maxTotalMessages.value       = state.config.max_total_messages ?? 5000;
      updateLimitModeUI();
      dom.enableExpireDelete.checked   = state.config.enable_expire_delete !== false;
      dom.enableRecalledDelete.checked = state.config.enable_recalled_delete !== false;
      dom.enableForwardToGroup.checked   = state.config.enable_forward_to_group === true;
      dom.enableForwardToPrivate.checked = state.config.enable_forward_to_private === true;
      dom.enableMergeForward.checked     = state.config.enable_merge_forward !== false;
    } catch (err) {
      console.error("[RecallBack Page] 加载配置失败:", err);
    }
  }

  async function loadGroups() {
    try {
      const resp = await bridge.apiGet("groups", {});
      if (resp && resp.ok) {
        state.groups = (resp.groups || []).map(function (g) {
          return {
            group_id:       g.group_id,
            group_name:     g.group_name,
            member_count:   g.member_count,
            max_member_count: g.max_member_count,
            enabled: g.enabled === true,
          };
        });
      } else {
        showError("获取群列表失败: " + ((resp && resp.error) || "未知错误"));
      }
    } catch (err) {
      console.error("[RecallBack Page] 加载群列表失败:", err);
      showError("获取群列表失败，请确认 NapCat 已连接。");
    }
  }

  async function loadFriends() {
    try {
      const resp = await bridge.apiGet("friends", {});
      if (resp && resp.ok) {
        state.friends = (resp.friends || []).map(function (f) {
          return {
            user_id:  f.user_id,
            nickname: f.nickname,
            remark:   f.remark,
            enabled: f.enabled === true,
          };
        });
      } else {
        state.friends = [];
      }
    } catch (err) {
      console.error("[RecallBack Page] 加载好友列表失败:", err);
      state.friends = [];
    }
  }

  // ═══════════════════════════════════════════════════════════
  // 上限模式联动
  // ═══════════════════════════════════════════════════════════

  function updateLimitModeUI() {
    var mode = dom.limitMode.value;
    dom.sessionLimitGroup.style.display = (mode === "session") ? "block" : "none";
    dom.totalLimitGroup.style.display  = (mode === "total")  ? "block" : "none";
  }

  // ═══════════════════════════════════════════════════════════
  // 群列表渲染（纯勾选框，无下拉框，无排序）
  // ═══════════════════════════════════════════════════════════

  function renderGroupList() {
    const body = dom.groupList;
    body.innerHTML = "";

    if (state.groups.length === 0) {
      body.innerHTML = '<div class="group-empty">暂无群数据，请点击"刷新列表"获取</div>';
      return;
    }

    state.groups.forEach(function (g, idx) {
      body.appendChild(createCheckRow(g, idx, "group_id", "group_name", "group"));
    });
  }

  // ═══════════════════════════════════════════════════════════
  // 好友列表渲染（纯勾选框，无下拉框，无排序）
  // ═══════════════════════════════════════════════════════════

  function renderFriendList() {
    const body = dom.friendList;
    body.innerHTML = "";

    if (state.friends.length === 0) {
      body.innerHTML = '<div class="group-empty">暂无好友数据，请点击刷新</div>';
      return;
    }

    state.friends.forEach(function (f, idx) {
      body.appendChild(createCheckRow(f, idx, "user_id", "display_name", "friend"));
    });
  }

  // ═══════════════════════════════════════════════════════════
  // 通用：创建可勾选的行
  // ═══════════════════════════════════════════════════════════

  function createCheckRow(item, idx, idKey, nameKey, type) {
    const row = document.createElement("div");
    row.className = "group-row";

    // 序号
    const idxSpan = document.createElement("span");
    idxSpan.className = "row-index";
    idxSpan.textContent = idx + 1;
    row.appendChild(idxSpan);

    // 信息
    const info = document.createElement("div");
    info.className = "row-info";
    const nameEl = document.createElement("div");
    nameEl.className = "group-name";

    if (type === "friend") {
      nameEl.textContent = item.remark || item.nickname || item[idKey];
      nameEl.title = nameEl.textContent;
    } else {
      nameEl.textContent = item[nameKey] || item[idKey];
      nameEl.title = nameEl.textContent;
    }
    info.appendChild(nameEl);

    const meta = document.createElement("div");
    meta.className = "group-meta";
    if (type === "group") {
      meta.innerHTML =
        "<span>ID: " + item[idKey] + "</span>" +
        "<span>成员: " + (item.member_count || 0) + "/" + (item.max_member_count || 0) + "</span>";
    } else {
      meta.textContent = "ID: " + item[idKey] +
        (item.nickname && item.remark ? "  昵称: " + item.nickname : "");
    }
    info.appendChild(meta);
    row.appendChild(info);

    // 勾选框
    const toggleWrap = document.createElement("span");
    toggleWrap.className = "row-toggle";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "checkbox-custom";
    cb.checked = item.enabled;
    cb.addEventListener("change", function () {
      item.enabled = cb.checked;
    });
    toggleWrap.appendChild(cb);
    row.appendChild(toggleWrap);

    return row;
  }

  // ═══════════════════════════════════════════════════════════
  // 事件绑定
  // ═══════════════════════════════════════════════════════════

  function bindAllEvents() {
    // 折叠/展开
    dom.recallGroupCollapseBtn.addEventListener("click", function () {
      dom.groupListContainer.classList.toggle("collapsed");
      dom.recallGroupCollapseBtn.classList.toggle("collapsed");
    });
    dom.recallFriendCollapseBtn.addEventListener("click", function () {
      dom.friendListContainer.classList.toggle("collapsed");
      dom.recallFriendCollapseBtn.classList.toggle("collapsed");
    });

    // 刷新群列表
    dom.refreshBtn.addEventListener("click", async function () {
      dom.refreshBtn.disabled = true;
      dom.refreshBtn.textContent = "刷新中...";
      hideError();
      try {
        await loadGroups();
        renderGroupList();
      } catch (e) {
        showError("刷新失败: " + (e.message || ""));
      } finally {
        dom.refreshBtn.disabled = false;
        dom.refreshBtn.innerHTML =
          '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>刷新列表';
      }
    });

    // 刷新好友列表
    dom.refreshFriendsBtn.addEventListener("click", async function () {
      dom.refreshFriendsBtn.disabled = true;
      dom.refreshFriendsBtn.textContent = "刷新中...";
      hideError();
      try {
        await loadFriends();
        renderFriendList();
      } catch (e) {
        showError("刷新失败: " + (e.message || ""));
      } finally {
        dom.refreshFriendsBtn.disabled = false;
        dom.refreshFriendsBtn.innerHTML =
          '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>刷新列表';
      }
    });

    // 上限模式切换
    dom.limitMode.addEventListener("change", updateLimitModeUI);

    // 保存
    dom.saveBtn.addEventListener("click", onSave);
    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        onSave();
      }
    });
  }

  // ═══════════════════════════════════════════════════════════
  // 保存
  // ═══════════════════════════════════════════════════════════

  async function onSave() {
    dom.saveBtn.disabled = true;
    dom.saveBtn.textContent = "保存中...";
    dom.saveStatus.textContent = "";
    dom.saveStatus.className = "save-status";
    hideError();

    const forwardGroupConfigs = {};
    state.groups.forEach(function (g) {
      forwardGroupConfigs[g.group_id] = { enabled: g.enabled };
    });

    const forwardPrivateConfigs = {};
    state.friends.forEach(function (f) {
      forwardPrivateConfigs[f.user_id] = { enabled: f.enabled };
    });

    const payload = {
      enable_group_listen:      dom.enableGroupListen.checked,
      enable_private_listen:    dom.enablePrivateListen.checked,
      enable_parse_forward:     dom.enableParseForward.checked,
      message_retention_minutes: parseInt(dom.messageRetentionMinutes.value, 10) || 10,
      limit_mode:               dom.limitMode.value,
      max_messages_per_session: parseInt(dom.maxMessagesPerSession.value, 10) ?? 200,
      max_total_messages:       parseInt(dom.maxTotalMessages.value, 10) ?? 5000,
      enable_expire_delete:     dom.enableExpireDelete.checked,
      enable_recalled_delete:   dom.enableRecalledDelete.checked,
      enable_forward_to_group:  dom.enableForwardToGroup.checked,
      forward_group_configs:    forwardGroupConfigs,
      enable_forward_to_private: dom.enableForwardToPrivate.checked,
      forward_private_configs:   forwardPrivateConfigs,
      enable_merge_forward:     dom.enableMergeForward.checked,
    };

    try {
      const resp = await bridge.apiPost("config", payload);
      if (resp && resp.ok) {
        dom.saveStatus.textContent = "✓ 配置已保存";
        dom.saveStatus.className = "save-status success";
        setTimeout(function () {
          dom.saveStatus.textContent = "";
          dom.saveStatus.className = "save-status";
        }, 3000);
      } else {
        throw new Error((resp && resp.error) || "保存失败");
      }
    } catch (err) {
      console.error("[RecallBack Page] 保存失败:", err);
      dom.saveStatus.textContent = "✗ " + (err.message || "保存失败");
      dom.saveStatus.className = "save-status error";
    } finally {
      dom.saveBtn.disabled = false;
      dom.saveBtn.innerHTML =
        '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>保存配置';
    }
  }

  // ═══════════════════════════════════════════════════════════
  // 汇总
  // ═══════════════════════════════════════════════════════════

  function renderAll() {
    renderGroupList();
    renderFriendList();
  }

  // ═══════════════════════════════════════════════════════════
  // 启动
  // ═══════════════════════════════════════════════════════════

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

})();
