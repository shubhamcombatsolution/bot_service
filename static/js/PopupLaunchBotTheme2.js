/**
 * PopupLaunchBotTheme2.js
 * Vanilla JS port of the React PopupLaunchBotTheme2 component.
 *
 * IP / domain validation:
 *   • If LaunchBot.js already validated the client it will have stored the token at
 *     window.botConfig._authToken AND sessionStorage["launchbot_tempToken"].
 *   • If the token is missing (standalone use) this script runs the full
 *     validate_client flow before enabling chat.
 *
 * Usage – window.botConfig must be set before this script loads:
 * window.botConfig = {
 *   chatbot_name     : "My Bot",
 *   avatar           : "filename.png",
 *   greeting_message : "Hello!",
 *   greeting_type    : "static" | "dynamic",
 *   bot_id           : "abc123",
 *   instance_id      : "abc123",
 *   background_image : "url-or-path",
 *   api_key          : "...",
 *   _authToken       : "...",   // injected by LaunchBot.js
 *   colors: {
 *     set1: ["#57b167","#94d26e"],
 *     set2: ["#6ddda5","#4abdda"],
 *     set3: ["#b4e568","#44aa61"],
 *   }
 * }
 *
 * The host page must contain: <div id="chatbot-root"></div>
 */

(function () {
  "use strict";

  /* ─────────────────────────────────────────────────────────────
   * CONSTANTS
   * ───────────────────────────────────────────────────────────── */
  const DEPENDENCY_TIMEOUT = 20000;

  const DEFAULT_COLORS = {
    set1: ["#57b167", "#94d26e"],
    set2: ["#6ddda5", "#4abdda"],
    set3: ["#b4e568", "#44aa61"],
  };
  const FALLBACK_AVATAR = "https://cdn-icons-png.flaticon.com/512/4712/4712109.png";

  /* ─────────────────────────────────────────────────────────────
   * UTILITIES
   * ───────────────────────────────────────────────────────────── */
  function resolveAvatarUrl(icon, baseUrl) {
    if (!icon) return FALLBACK_AVATAR;
    const avatar = String(icon).trim();
    if (!avatar) return FALLBACK_AVATAR;
    if (avatar.startsWith("blob:") || avatar.startsWith("data:")) return avatar;

    const toAvatarPath = (value) => {
      const filename = value.split("/").filter(Boolean).pop();
      return filename
        ? `${baseUrl}/custom_bot_new/uploads/avatars/${filename}`
        : FALLBACK_AVATAR;
    };

    if (/^https?:\/\//i.test(avatar)) {
      try {
        const parsed = new URL(avatar);
        if (parsed.pathname.includes("/custom_bot_new/uploads/avatars/")) return avatar;
        if (parsed.pathname.includes("/uploads/avatars/")) return toAvatarPath(parsed.pathname);
        return avatar;
      } catch (_) {
        return FALLBACK_AVATAR;
      }
    }

    if (avatar.startsWith("/custom_bot_new/uploads/avatars/")) return `${baseUrl}${avatar}`;
    if (avatar.startsWith("/api/uploads/avatars/")) return toAvatarPath(avatar);
    if (avatar.startsWith("/uploads/avatars/")) return `${baseUrl}/custom_bot_new${avatar}`;
    if (avatar.startsWith("uploads/avatars/")) return `${baseUrl}/custom_bot_new/${avatar}`;

    return toAvatarPath(avatar);
  }

  function firstColor(value) {
    if (Array.isArray(value)) return value.find(Boolean) || "";
    if (typeof value === "string") return value.trim();
    return "";
  }

  function generateUUID() {
    if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
    });
  }

  function parseAgentResponse(agentResponse) {
    if (!agentResponse) return { text: "No response from bot", isError: false };
    if (agentResponse.error) return { text: String(agentResponse.error), isError: true };

    if (typeof agentResponse.response === "string" && agentResponse.response.trim())
      return { text: agentResponse.response.replace(/^"(.*)"$/, "$1"), isError: false };

    if (agentResponse.response && typeof agentResponse.response === "object") {
      const text =
        agentResponse.response.response ||
        agentResponse.response.text ||
        agentResponse.response.message ||
        JSON.stringify(agentResponse.output);
      return { text: String(text).replace(/^"(.*)"$/, "$1"), isError: false };
    }

    if (agentResponse.input)
      return { text: String(agentResponse.input).replace(/^"(.*)"$/, "$1"), isError: false };

    return { text: "No response from bot", isError: false };
  }

  function getHostnameFromUrl(url) {
    if (!url) return "";
    try {
      return new URL(url, window.location.href).hostname;
    } catch (_) {
      return "";
    }
  }

  function getClientDomain() {
    let isFramed = false;
    try {
      isFramed = !!(window.top && window.top !== window);
      if (isFramed && window.top.location) {
        const topHost = window.top.location.hostname;
        if (topHost) return topHost;
      }
    } catch (_) {
      isFramed = true;
    }

    if (isFramed) {
      const referrerHost = getHostnameFromUrl(document.referrer);
      if (referrerHost) return referrerHost;
    }

    return window.location.hostname;
  }

  function getTempTokenCacheKey(botId, domain) {
    return `launchbot_tempToken_${botId || "unknown"}_${domain || "unknown"}`;
  }

  /* ─────────────────────────────────────────────────────────────
   * IP / DOMAIN VALIDATION
   * ───────────────────────────────────────────────────────────── */

  async function fetchPublicIP() {
    const ipServices = [
      { url: "https://api.ipify.org?format=json", type: "json" },
      { url: "https://ipinfo.io/json",             type: "json" },
      { url: "https://ipv4.icanhazip.com",          type: "text" },
      { url: "https://api.myip.com",                type: "json" },
    ];

    return Promise.any(
      ipServices.map(async ({ url, type }) => {
        const ctrl  = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), DEPENDENCY_TIMEOUT);
        try {
          const res = await fetch(url, { cache: "no-store", signal: ctrl.signal });
          clearTimeout(timer);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          if (type === "text") return (await res.text()).trim();
          const d = await res.json();
          return d.ip || d.query;
        } catch (e) { clearTimeout(timer); throw e; }
      })
    );
  }

  /**
   * Run IP/domain validation against /custom_bot_new/validate_client.
   * Returns the temp token string on success.
   * Throws a user-friendly Error on failure.
   */
  async function validateClient(baseUrl, botId, apiKey) {
    const domain = getClientDomain();

    const headers = { "Content-Type": "application/json" };
    if (apiKey) headers["X-API-Key"] = apiKey;

    const postValidation = async (ipValue) => {
      return fetch(`${baseUrl}/custom_bot_new/validate_client`, {
        method: "POST",
        headers,
        body: JSON.stringify({ bot_id: botId, ip: ipValue || null, domain }),
      });
    };

    // Try without IP first so unrestricted bots can load even if IP services fail.
    let res = await postValidation(null);
    if (res.status === 403) {
      const ip = await fetchPublicIP();
      res = await postValidation(ip);
    }

    if (!res.ok) {
      const s = res.status;
      let msg = "Access denied by server.";
      if (s === 403) msg = "Error: Your IP or domain is not allowed to use this bot.";
      else if (s === 401) msg = "Error: Invalid API key.";
      else if (s === 404) msg = "Error: Bot not found.";
      throw Object.assign(new Error(msg), { status: s });
    }

    const data = await res.json();
    if (data.status !== "ok") throw new Error(data.message || "Validation failed.");

    const token = data.token;
    if (token) {
      try {
        sessionStorage.setItem(getTempTokenCacheKey(botId, domain), token);
      } catch (_) {}
    }
    return token;
  }

  /* ─────────────────────────────────────────────────────────────
   * MAIN INIT
   * ───────────────────────────────────────────────────────────── */
  function initBot() {
    const bot = window.botConfig || {};

    const root = document.getElementById("chatbot-root");
    if (!root) {
      console.error("[Theme2] #chatbot-root not found");
      return;
    }

    function hideBotUi() {
      try {
        root.innerHTML = "";
        root.style.display = "none";
      } catch (_) {}
    }

    /* ── resolve config ── */
    const BASE_URL     = bot.base_url || `${window.location.protocol}//${window.location.host}`;
    const API_CHAT     = `${BASE_URL}/multi_agents/get_chat`;
    const apiKey       = bot.api_key || bot.x_api_key || "";
    const BotId        = bot.bot_id || bot.instance_id || "";
    const InstanceId   = bot.instance_id || "";
    const botName      = bot.chatbot_name || bot.bot_name || "Assistant";
    const greetingType = bot.greeting_type || "dynamic";
    const staticGreeting = bot.greeting_message || "Hello! How can I help you today?";
    const botIconUrl   = resolveAvatarUrl(bot.avatar || "", BASE_URL);
    const backgroundImage = bot.background_image || "";

    const colors = bot.colors || {};
    const set1 = Array.isArray(colors.set1) ? colors.set1 : DEFAULT_COLORS.set1;
    const set2 = Array.isArray(colors.set2) ? colors.set2 : DEFAULT_COLORS.set2;
    const set3 = Array.isArray(colors.set3) ? colors.set3 : DEFAULT_COLORS.set3;
    const bgColor =
      firstColor(bot.background_color) ||
      firstColor(bot.backgroundColor) ||
      firstColor(bot.background) ||
      firstColor(colors.background_color) ||
      firstColor(colors.backgroundColor) ||
      firstColor(colors.secondary) ||
      firstColor(set2) ||
      "#ffffff";

    /* ── session ── */
    const sessionKey = `bot_session_${BotId}`;
    let sessionId = (() => {
      try { return localStorage.getItem(sessionKey); } catch (_) { return null; }
    })();
    function ensureSession() {
      if (sessionId) return sessionId;
      const id = generateUUID();
      try { localStorage.setItem(sessionKey, id); } catch (_) {}
      sessionId = id;
      return id;
    }
    ensureSession();

    /* ── state ── */
    let msgList      = []; // { text, sender:'user'|'bot', error?:bool, loading?:bool }
    let history      = [];
    const domain = getClientDomain();
    const cachedToken = (() => {
      try { return sessionStorage.getItem(getTempTokenCacheKey(BotId, domain)); } catch (_) { return null; }
    })();

    let authToken = bot._authToken || cachedToken || null;
    let isVerified = !!authToken;

    /* ── build DOM ── */
    root.innerHTML = buildHTML(botName, botIconUrl, backgroundImage);

    const chatContainer = root.querySelector(".popup-launch-bot-theme2");
    if (chatContainer) {
      chatContainer.style.setProperty(
        "--chat-bg",
        backgroundImage ? `url(${backgroundImage})` : bgColor
      );
      chatContainer.style.setProperty("--chat-bg-color", bgColor);
      chatContainer.style.setProperty("--input-bg", firstColor(set2) || bgColor);
      root.style.setProperty("--primary-color",   `linear-gradient(90deg, ${set1.join(", ")})`);
      root.style.setProperty("--secondary-color", `linear-gradient(90deg, ${set2.join(", ")})`);
      root.style.setProperty("--accent-color",    `linear-gradient(90deg, ${set3.join(", ")})`);
      root.style.setProperty("--bot-avatar",      `url(${botIconUrl})`);
      applyColorVars(chatContainer, set1, set2, set3, botIconUrl);
    }

    const overlay = root.querySelector(".bg-overlay");
    if (overlay) overlay.style.display = backgroundImage ? "block" : "none";

    root.querySelectorAll(".bot-logo-theme2, .launcher-avatar").forEach((img) => {
      img.loading = "eager";
      img.decoding = "sync";
      img.onerror = function () {
        this.onerror = null;
        this.src = FALLBACK_AVATAR;
      };
    });

    applyChatPosition(bot.position || "bottom_right");
    applyLauncherPosition(bot.position || "bottom_right");
    setChatOpen(false);
    const messagesEl  = root.querySelector("#t2-messages");
    const chatInput   = root.querySelector("#t2-input");
    const chatForm    = root.querySelector("#t2-form");
    const dotsBtn     = root.querySelector("#t2-dots-btn");
    const dropdown    = root.querySelector("#t2-dropdown");
    const dlBtn       = root.querySelector("#t2-menu-download");
    const ldBtn       = root.querySelector("#t2-menu-load");
    const clrBtn      = root.querySelector("#t2-menu-clear");
    const launcher    = root.querySelector("#chat-launcher");
    const minimizeBtn = root.querySelector("#t2-minimize-btn");

    /* ── disable input until validated ── */
    chatInput.disabled     = true;
    chatInput.placeholder  = "Verifying access…";

    /* ── run validation (or reuse cached token) ── */
    if (isVerified) {
      // Already validated by LaunchBot
      enableChat();
    } else {
      validateClient(BASE_URL, BotId, apiKey)
        .then((token) => {
          authToken  = token;
          isVerified = true;
          enableChat();
        })
        .catch((err) => {
          console.error("[Theme2] Validation failed:", err.message);
          if (err && err.status === 403) {
            hideBotUi();
            return;
          }
          addMessage({ text: err.message || "Access denied.", sender: "bot", error: true });
          chatInput.placeholder = "Access denied.";
          // input stays disabled
        });
    }

    function enableChat() {
      chatInput.disabled    = false;
      chatInput.placeholder = "Ask me anything...";
      initGreeting();
    }

    /* ── greeting ── */
    async function initGreeting() {
      if (greetingType === "static") {
        addMessage({ text: staticGreeting, sender: "bot" });
        return;
      }

      const sid = ensureSession();
      const loadingIdx = addMessage({ sender: "bot", loading: true });

      try {
        let historyData = [];
        try {
          const headers = {};
          if (apiKey) headers["X-API-Key"] = apiKey;
          if (authToken) headers["Authorization"] = `Bearer ${authToken}`;

          const historyUrl = InstanceId
            ? `${BASE_URL}/api/custom_bot_new/chat-history/${InstanceId}`
            : `${BASE_URL}/api/chat_history/${BotId}`;

          const histRes = await fetch(historyUrl, { headers });
          if (histRes.ok) {
            const histJson = await histRes.json();
            historyData = histJson?.data?.history || histJson?.history || [];
            history = historyData.map((entry) => ({ text: entry.response, sender: "bot" }));

            const recentGreeting = historyData.find(
              (entry) =>
                entry.query === "hello" &&
                new Date(entry.created_at) > new Date(Date.now() - 5 * 60 * 1000)
            );
            if (recentGreeting) {
              replaceLoading(loadingIdx, { text: recentGreeting.response, sender: "bot" });
              return;
            }
          }
        } catch (_) { history = []; }

        const headers = { "Content-Type": "application/json" };
        if (apiKey)    headers["X-API-Key"]     = apiKey;
        if (authToken) headers["Authorization"] = `Bearer ${authToken}`;

        const res = await fetch(API_CHAT, {
          method: "POST",
          headers,
          body: JSON.stringify({ query: "hello", bot_id: BotId, history: [], session_id: sid }),
        });
        const data = await res.json();
        const { text, isError } = parseAgentResponse(data);
        replaceLoading(loadingIdx, { text, sender: "bot", error: isError });
      } catch (err) {
        const fallback =
          err?.response?.data?.msg === "Token has expired"
            ? "Your session has expired. Please log in."
            : "Welcome! I'm here to assist you.";
        replaceLoading(loadingIdx, { text: fallback, sender: "bot" });
      }
    }

    /* ── send message ── */
    chatForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const text = chatInput.value.trim();
      if (!text) return;
      if (!isVerified) {
        addMessage({ text: "Please wait – verifying access…", sender: "bot" });
        return;
      }

      addMessage({ text, sender: "user" });
      chatInput.value = "";

      const loadingIdx = addMessage({ sender: "bot", loading: true });
      const sid = ensureSession();

      try {
        const headers = { "Content-Type": "application/json" };
        if (apiKey)    headers["X-API-Key"]     = apiKey;
        if (authToken) headers["Authorization"] = `Bearer ${authToken}`;

        const res = await fetch(API_CHAT, {
          method: "POST",
          headers,
          body: JSON.stringify({
            query:      text,
            bot_id:     BotId,
            history:    msgList.map((m) => ({
              query:    m.sender === "user" ? m.text : "",
              response: m.sender === "bot"  ? m.text : "",
            })),
            session_id: sid,
          }),
        });
        const data = await res.json();
        const { text: reply, isError } = parseAgentResponse(data);
        replaceLoading(loadingIdx, { text: reply, sender: "bot", error: isError });
      } catch (err) {
        const errText = err.message || "Error reaching AI service.";
        replaceLoading(loadingIdx, { text: errText, sender: "bot", error: true });
      }
    });

    /* ── three-dots menu ── */
    if (dotsBtn && dropdown) {
      dotsBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        dropdown.classList.toggle("open");
      });
      dropdown.addEventListener("click", (e) => {
        e.stopPropagation();
      });
      document.addEventListener("click", () => dropdown.classList.remove("open"));
    }

    const params = new URLSearchParams(window.location.search);
    if (params.get("openBot") === "true") {
      setChatOpen(true);
    }

    if (launcher) {
      launcher.addEventListener("click", () => {
        setChatOpen(!launcher.classList.contains("is-open"));
      });
    }

    if (minimizeBtn) {
      minimizeBtn.addEventListener("click", () => {
        if (dropdown) dropdown.classList.remove("open");
        setChatOpen(false);
      });
    }


    if (dlBtn) dlBtn.addEventListener("click",  () => { downloadChat();   if (dropdown) dropdown.classList.remove("open"); });
    if (ldBtn) ldBtn.addEventListener("click",  () => { loadChatHistory(); if (dropdown) dropdown.classList.remove("open"); });
    if (clrBtn) clrBtn.addEventListener("click", () => { clearChat();       if (dropdown) dropdown.classList.remove("open"); });

    /* ── menu actions ── */
    function downloadChat() {
      const content = msgList
        .filter((m) => !m.loading)
        .map((m) => `${m.sender}: ${m.text}`)
        .join("\n");
      const blob = new Blob([content], { type: "text/plain" });
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href = url; a.download = "chat_history.txt"; a.click();
      URL.revokeObjectURL(url);
    }

    function loadChatHistory() {
      const existing = new Set(msgList.map((m) => m.text));
      history.filter((h) => !existing.has(h.text)).forEach((h) => addMessage(h));
    }

    function clearChat() {
      msgList = [];
      messagesEl.innerHTML = "";
      const g = greetingType === "static" && staticGreeting
        ? staticGreeting
        : "Welcome! I'm here to assist you.";
      addMessage({ text: g, sender: "bot" });
    }

    /* ─────────────────────────────────────────────────────────────
     * DOM HELPERS
     * ───────────────────────────────────────────────────────────── */
    function addMessage(msg) {
      msgList.push(msg);
      const idx = msgList.length - 1;
      renderMessage(msg, idx);
      scrollToBottom();
      return idx;
    }

    function replaceLoading(idx, msg) {
      msgList[idx] = msg;
      const existing = messagesEl.querySelector(`[data-msg-idx="${idx}"]`);
      if (existing) {
        messagesEl.replaceChild(createMessageEl(msg, idx), existing);
      } else {
        renderMessage(msg, idx);
      }
      scrollToBottom();
    }

    function renderMessage(msg, idx) {
      messagesEl.appendChild(createMessageEl(msg, idx));
    }

    function createMessageEl(msg, idx) {
      const wrap = document.createElement("div");
      wrap.className = `message-theme2 ${msg.sender}${msg.error ? " error-message" : ""}`;
      wrap.dataset.msgIdx = idx;

      if (msg.loading) {
        wrap.innerHTML = `
          <div class="typing-indicator">
            <span></span><span></span><span></span>
          </div>`;
      } else {
        const span = document.createElement("span");
        span.textContent = msg.text;
        wrap.appendChild(span);
      }
      return wrap;
    }

    function scrollToBottom() {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function applyChatPosition(position) {
      const chat = document.querySelector(".popup-launch-bot-theme2");
      if (!chat) return;
      chat.style.top = chat.style.bottom = chat.style.left = chat.style.right = "";
      switch (position) {
        case "bottom_left": chat.style.bottom = "90px"; chat.style.left  = "20px"; break;
        case "top_right":   chat.style.top    = "90px"; chat.style.right = "20px"; break;
        case "top_left":    chat.style.top    = "90px"; chat.style.left  = "20px"; break;
        default:            chat.style.bottom = "90px"; chat.style.right = "20px";
      }
    }

    function applyLauncherPosition(position) {
      const launcherEl = document.getElementById("chat-launcher");
      if (!launcherEl) return;
      launcherEl.style.top = launcherEl.style.bottom = launcherEl.style.left = launcherEl.style.right = "";
      switch (position) {
        case "bottom_left": launcherEl.style.bottom = "20px"; launcherEl.style.left  = "20px"; break;
        case "top_right":   launcherEl.style.top    = "20px"; launcherEl.style.right = "20px"; break;
        case "top_left":    launcherEl.style.top    = "20px"; launcherEl.style.left  = "20px"; break;
        default:            launcherEl.style.bottom = "20px"; launcherEl.style.right = "20px";
      }
    }

    function setChatOpen(open) {
      const chat = document.querySelector(".popup-launch-bot-theme2");
      const launcherEl = document.getElementById("chat-launcher");
      if (chat) chat.style.display = open ? "flex" : "none";
      if (launcherEl) {
        launcherEl.style.display = open ? "none" : "flex";
        launcherEl.classList.toggle("is-open", open);
        launcherEl.classList.toggle("is-closed", !open);
        launcherEl.setAttribute("aria-label", open ? "Minimize chat" : "Open chat");
      }
    }
  }

  /* ─────────────────────────────────────────────────────────────
   * BUILD HTML
   * ───────────────────────────────────────────────────────────── */
  function buildHTML(botName, botIconUrl, backgroundImage) {
    const launcherAvatarId = "launchbot-theme2-launcher-avatar";
    const avatarImg = `<img src="${botIconUrl || FALLBACK_AVATAR}" alt="Bot Logo" class="bot-logo-theme2" />`;

    return `
<button type="button" id="chat-launcher" aria-label="Open chat">
  <img id="${launcherAvatarId}" src="${botIconUrl || FALLBACK_AVATAR}" class="launcher-avatar" alt="Bot Avatar" />
  <span class="launcher-x" aria-hidden="true">×</span>
</button>

<div class="popup-launch-bot-theme2">
  <div class="bg-overlay"></div>

  <!-- HEADER -->
  <div class="popup-header-theme2">
    <div class="header-left-theme2">${avatarImg}</div>
    <div class="header-center-theme2"><span class="bot-name">${botName}</span></div>
    <div class="header-right-theme2">
      <button type="button" class="chat-minimize-btn-theme2" id="t2-minimize-btn" aria-label="Minimize chat">
        <span></span>
      </button>
      <button type="button" class="three-dots-theme2" id="t2-dots-btn"
              aria-label="Menu" aria-expanded="false">
        <span></span><span></span><span></span>
      </button>
      <div class="dropdown-menu-theme2" id="t2-dropdown">
        <button type="button" class="menu-item-theme2" id="t2-menu-download">Download</button>
        <button type="button" class="menu-item-theme2" id="t2-menu-load">Load</button>
        <button type="button" class="menu-item-theme2" id="t2-menu-clear">Clear</button>
      </div>
    </div>
  </div>

  <!-- CHAT BODY -->
  <div class="chat-body-theme2">
    <div class="messages-container-theme2" id="t2-messages"></div>
  </div>

  <!-- INPUT -->
  <form class="chat-input-container-theme2" id="t2-form">
    <input
      type="text"
      id="t2-input"
      class="chat-input-theme2"
      placeholder="Ask me anything..."
      autocomplete="off"
    />
    <button type="submit" class="send-button-theme2" aria-label="Send message">
      <span class="send-icon">➤</span>
    </button>
  </form>
</div>`;
  }

  /* ─────────────────────────────────────────────────────────────
   * CSS VARS
   * ───────────────────────────────────────────────────────────── */
  function applyColorVars(container, set1, set2, set3, botIconUrl) {
    if (!container) return;
    container.style.setProperty("--primary-color",   `linear-gradient(90deg, ${set1.join(", ")})`);
    container.style.setProperty("--secondary-color", `linear-gradient(90deg, ${set2.join(", ")})`);
    container.style.setProperty("--accent-color",    `linear-gradient(90deg, ${set3.join(", ")})`);
    container.style.setProperty("--bot-avatar",      `url(${botIconUrl})`);
  }

  /* ─────────────────────────────────────────────────────────────
   * BOOT
   * ───────────────────────────────────────────────────────────── */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initBot);
  } else {
    initBot();
  }
})();
