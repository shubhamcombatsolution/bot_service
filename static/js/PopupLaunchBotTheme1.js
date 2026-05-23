/**
 * PopupLaunchBotTheme1.js
 *
 * Renders the Theme-1 popup chatbot UI.
 * Expects window.botConfig to be populated by LaunchBot.js before this runs.
 *
 * IP / domain validation:
 *   • If LaunchBot already validated the client it will have stored the token at
 *     window.botConfig._authToken  AND  sessionStorage["launchbot_tempToken"].
 *   • If for any reason the token is missing (e.g. script loaded standalone),
 *     this file will run the full validate_client flow itself before enabling chat.
 */

function initBot() {
  /* ─────────────────────────────────────────────────────────────
   * CONFIG
   * ───────────────────────────────────────────────────────────── */
  const bot         = window.botConfig || {};
  const baseUrl     = bot.base_url || `${window.location.protocol}//${window.location.host}`;
  const apiKey      = bot.api_key || bot.x_api_key || "";
  const instanceId  = bot.instance_id || "";
  const botId       = bot.bot_id || instanceId;

  const FALLBACK_AVATAR    = "https://cdn-icons-png.flaticon.com/512/4712/4712109.png";
  const DEPENDENCY_TIMEOUT = 20000;
  const API_CHAT           = `${baseUrl}/multi_agents/get_chat`;

  /* ─────────────────────────────────────────────────────────────
   * AVATAR URL RESOLUTION
   * ───────────────────────────────────────────────────────────── */
  function normalizeAvatarUrl(rawAvatar) {
    if (!rawAvatar) return FALLBACK_AVATAR;
    const avatar = String(rawAvatar).trim();
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
      } catch (_) { return FALLBACK_AVATAR; }
    }

    if (avatar.startsWith("/custom_bot_new/uploads/avatars/")) return `${baseUrl}${avatar}`;
    if (avatar.startsWith("/api/uploads/avatars/"))            return toAvatarPath(avatar);
    if (avatar.startsWith("/uploads/avatars/"))                return `${baseUrl}/custom_bot_new${avatar}`;
    if (avatar.startsWith("uploads/avatars/"))                 return `${baseUrl}/custom_bot_new/${avatar}`;

    return toAvatarPath(avatar);
  }

  const resolvedAvatar = normalizeAvatarUrl(bot.avatar);
  const launcherAvatarId = "launchbot-theme1-launcher-avatar";

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

  function getTempTokenCacheKey(domain) {
    return `launchbot_tempToken_${botId || "unknown"}_${domain || "unknown"}`;
  }

  /* ─────────────────────────────────────────────────────────────
   * ROOT
   * ───────────────────────────────────────────────────────────── */
  const root = document.getElementById("chatbot-root");
  if (!root) {
    console.error("[Theme1] #chatbot-root not found");
    return;
  }

  function hideBotUi() {
    try {
      root.innerHTML = "";
      root.style.display = "none";
    } catch (_) {}
  }

  /* ─────────────────────────────────────────────────────────────
   * IP / DOMAIN VALIDATION  (mirrors JnanicChatbotJs.js logic)
   * Skipped if LaunchBot already did it and stored the token.
   * ───────────────────────────────────────────────────────────── */

  /** Fetch the visitor's public IP by racing several free services */
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
   * Validate client with the server.
   * Returns the temp token on success, or throws with a user-friendly message.
   */
async function validateClient() {
  const domain = getClientDomain();

  const headers = {
    "Content-Type": "application/json"
  };

  if (apiKey) headers["X-API-Key"] = apiKey;

  const postValidation = async (ipValue) => {
    return fetch(`${baseUrl}/custom_bot_new/validate_client`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        bot_id: botId,
        ip: ipValue || null,
        domain: domain
      })
    });
  };

  // Try without IP first so unrestricted bots can load even if IP services fail.
  let res = await postValidation(null);
  if (res.status === 403) {
    const ip = await fetchPublicIP();
    res = await postValidation(ip);
  }

  const data = await res.json(); // ✅ ONLY ONCE

  if (!res.ok) {
    const status = res.status;
    let msg = "Access denied by server.";
    if (status === 403) msg = "Error: Your IP or domain is not allowed.";
    else if (status === 401) msg = "Error: Invalid API key.";
    else if (status === 404) msg = "Error: Bot not found.";
    throw Object.assign(new Error(msg), { status });
  }

  if (data.status !== "ok") {
    throw new Error(data.message || "Validation failed.");
  }

  const token = data.token;

  if (token) {
    try {
      sessionStorage.setItem(getTempTokenCacheKey(domain), token);
    } catch (_) {}
  }

  return token;
}

  /* ─────────────────────────────────────────────────────────────
   * SESSION
   * ───────────────────────────────────────────────────────────── */
  const sessionKey = `bot_session_${botId || "default"}`;
  let session_id = (() => { try { return localStorage.getItem(sessionKey); } catch (_) { return null; } })();
  if (!session_id) {
    session_id = (typeof crypto !== "undefined" && crypto.randomUUID)
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2);
    try { localStorage.setItem(sessionKey, session_id); } catch (_) {}
  }

  /* ─────────────────────────────────────────────────────────────
   * COLORS / STYLES
   * ───────────────────────────────────────────────────────────── */
  const colors      = bot.colors || {};
  const defaultSet  = ["#264c68", "#355c7d", "#6c5b7b"];
  const set1        = Array.isArray(colors.set1) ? colors.set1 : defaultSet;
  const set2        = Array.isArray(colors.set2) ? colors.set2 : [];

  function firstColor(value) {
    if (Array.isArray(value)) return value.find(Boolean) || "";
    if (typeof value === "string") return value.trim();
    return "";
  }

  const bgColor =
    firstColor(bot.background_color) ||
    firstColor(bot.backgroundColor) ||
    firstColor(bot.background) ||
    firstColor(colors.background_color) ||
    firstColor(colors.backgroundColor) ||
    firstColor(colors.secondary) ||
    firstColor(set2) ||
    "#ffffff";

  /* ─────────────────────────────────────────────────────────────
   * BUILD UI
   * ───────────────────────────────────────────────────────────── */
  root.innerHTML = `
<button type="button" id="chat-launcher" aria-label="Open chat">
  <img id="${launcherAvatarId}" src="${resolvedAvatar}" class="launcher-avatar" alt="Bot Avatar"/>
  <span class="launcher-x" aria-hidden="true">×</span>
</button>

<div class="popup-launch-bot-theme1">

  <!-- HEADER -->
  <div class="popup-header">
    <img src="${resolvedAvatar}" class="bot-logo" alt="Bot Avatar"/>
    <span class="bot-name">${bot.chatbot_name || "Assistant"}</span>

    <button type="button" class="chat-minimize-btn" id="chat-minimize-btn" aria-label="Minimize chat">
      <span></span>
    </button>

    <div class="menu-wrapper">
      <div class="menu-dots" id="menu-dots">
        <span></span><span></span><span></span>
      </div>
      <div class="dropdown-menu" id="dropdown-menu">
        <div class="menu-item" id="menu-download">Download</div>
        <div class="menu-item" id="menu-load">Load</div>
        <div class="menu-item" id="menu-clear">Clear</div>
      </div>
    </div>
  </div>

  <!-- CHAT BODY -->
  <div class="chat-body" id="messages"></div>

  <!-- INPUT -->
  <form id="chat-form">
    <input id="chat-input" placeholder="Ask me anything..." autocomplete="off"/>
    <button type="submit" class="send-btn">
      <span class="send-icon">➤</span>
    </button>
  </form>

</div>`;

  /* Apply CSS custom properties */
  const chatContainer = root.querySelector(".popup-launch-bot-theme1");
  if (chatContainer) {
    root.style.setProperty(
      "--primary-gradient",
      `linear-gradient(135deg, ${set1.join(",")})`
    );
    root.style.setProperty("--bot-avatar", `url(${resolvedAvatar})`);
    chatContainer.style.setProperty(
      "--primary-gradient",
      `linear-gradient(135deg, ${set1.join(",")})`
    );
    chatContainer.style.setProperty("--bot-avatar", `url(${resolvedAvatar})`);
    chatContainer.style.setProperty(
      "--chat-bg",
      bot.background_image ? `url(${bot.background_image})` : bgColor
    );
    chatContainer.style.setProperty("--chat-bg-color", bgColor);
    chatContainer.style.setProperty(
      "--input-bg",
      firstColor(set2) || bgColor
    );
  }

  /* Avatar error fallback */
  const headerLogo = root.querySelector(".bot-logo");
  const launcherAvatar = root.querySelector(`#${launcherAvatarId}`);
  [headerLogo, launcherAvatar].forEach((img) => {
    if (!img) return;
    img.loading = "eager";
    img.decoding = "sync";
    img.onerror = function () {
      this.onerror = null;
      this.src = FALLBACK_AVATAR;
    };
  });

  /* Position */
  applyChatPosition(bot.position || "bottom_right");
  applyLauncherPosition(bot.position || "bottom_right");
  setChatOpen(false);

  /* ─────────────────────────────────────────────────────────────
   * DOM REFS
   * ───────────────────────────────────────────────────────────── */
  const form         = document.getElementById("chat-form");
  const input        = document.getElementById("chat-input");
  const messages     = document.getElementById("messages");
  const menuDots     = document.getElementById("menu-dots");
  const dropdownMenu = document.getElementById("dropdown-menu");
  const menuDownload = document.getElementById("menu-download");
  const menuLoad     = document.getElementById("menu-load");
  const menuClear    = document.getElementById("menu-clear");
  const launcher     = document.getElementById("chat-launcher");
  const minimizeBtn  = document.getElementById("chat-minimize-btn");

  /* ─────────────────────────────────────────────────────────────
   * STATE
   * ───────────────────────────────────────────────────────────── */
  let history    = [];
  let authToken  = null;
  let isVerified = false;

  /* ─────────────────────────────────────────────────────────────
   * GREETING  (shown immediately; chat enabled after validation)
   * ───────────────────────────────────────────────────────────── */
  const greet = bot.greeting_message || "Hello! How can I help you?";
  appendMessage(greet, "bot");
  history.push({ query: "", response: greet });

  /* Disable input while validating */
  input.disabled = true;
  input.placeholder = "Verifying access…";
  const domain = getClientDomain();
  const cachedToken = sessionStorage.getItem(getTempTokenCacheKey(domain));

  if (cachedToken) {
    authToken = cachedToken;
    isVerified = true;
    input.disabled = false;
    input.placeholder = "Ask me anything...";
  } else {
    validateClient()
      .then((token) => {
        authToken  = token;
        isVerified = true;
        input.disabled = false;
        input.placeholder = "Ask me anything...";
      })
      .catch((err) => {
        console.error("[Theme1] Validation failed:", err.message);
        if (err && err.status === 403) {
          hideBotUi();
          return;
        }
        appendMessage(err.message || "Access denied.", "bot");
        input.placeholder = "Access denied.";
      });
  }


  /* ─────────────────────────────────────────────────────────────
   * THREE-DOTS MENU
   * ───────────────────────────────────────────────────────────── */
  menuDots.addEventListener("click", (e) => {
    e.stopPropagation();
    dropdownMenu.classList.toggle("open");
  });

  launcher.addEventListener("click", () => {
    setChatOpen(!launcher.classList.contains("is-open"));
  });

  minimizeBtn.addEventListener("click", () => {
    dropdownMenu.classList.remove("open");
    setChatOpen(false);
  });

  document.addEventListener("click", () => {
    dropdownMenu.classList.remove("open");
  });

  dropdownMenu.addEventListener("click", (e) => {
    e.stopPropagation();
  });

  menuDownload.addEventListener("click", () => {
    const content = history
      .filter((h) => h.query || h.response)
      .map((h) => {
        let str = "";
        if (h.query)    str += `User: ${h.query}\n`;
        if (h.response) str += `Bot: ${h.response}`;
        return str;
      })
      .join("\n\n");

    const blob = new Blob([content], { type: "text/plain" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = "chat_history.txt";
    a.click();
    URL.revokeObjectURL(url);
    dropdownMenu.classList.remove("open");
  });

  menuLoad.addEventListener("click", () => {
    messages.innerHTML = "";
    history.forEach((h) => {
      if (h.query)    appendMessage(h.query,    "user");
      if (h.response) appendMessage(h.response, "bot");
    });
    dropdownMenu.classList.remove("open");
  });

  menuClear.addEventListener("click", () => {
    history = [];
    messages.innerHTML = "";
    const g = bot.greeting_message || "Hello! How can I help you?";
    appendMessage(g, "bot");
    history.push({ query: "", response: g });
    dropdownMenu.classList.remove("open");
  });

  /* ─────────────────────────────────────────────────────────────
   * SEND MESSAGE
   * ───────────────────────────────────────────────────────────── */
  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const text = input.value.trim();
    if (!text) return;
    if (!isVerified) {
      appendMessage("Please wait – verifying access…", "bot");
      return;
    }

    appendMessage(text, "user");
    input.value = "";

    /* Typing indicator */
    const typingDiv       = document.createElement("div");
    typingDiv.className   = "message bot";
    typingDiv.innerHTML   = `
      <div class="bubble typing">
        <span></span><span></span><span></span>
      </div>`;
    messages.appendChild(typingDiv);
    messages.scrollTop = messages.scrollHeight;

    try {
      const headers = { "Content-Type": "application/json" };
      if (apiKey)     headers["X-API-Key"]     = apiKey;
      if (authToken)  headers["Authorization"] = `Bearer ${authToken}`;
      console.log("VALIDATE TOKEN:", authToken);
      const payload = {
        query:      text,
        bot_id:     botId,
        history:    history.map((h) => ({
          query:    h.query    || "",
          response: h.response || "",
        })),
        session_id: session_id,
      };

      const res  = await fetch(API_CHAT, {
        method:  "POST",
        headers,
        body:    JSON.stringify(payload),
      });

      const data = await res.json();
      typingDiv.remove();

      const reply =
        typeof data.response === "string"
          ? data.response
          : data.response?.response || data.response?.text || "No response";

      appendMessage(reply, "bot");
      history.push({ query: text, response: reply });
    } catch (err) {
      typingDiv.remove();
      appendMessage("Server error. Please try again.", "bot");
    }
  });

  /* ─────────────────────────────────────────────────────────────
   * HELPERS
   * ───────────────────────────────────────────────────────────── */
  function appendMessage(text, type) {
    const div    = document.createElement("div");
    div.className = `message ${type}`;

    const bubble   = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text || "";

    div.appendChild(bubble);
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
  }

  function applyChatPosition(position) {
    const chat = document.querySelector(".popup-launch-bot-theme1");
    if (!chat) return;

    chat.style.top    = "";
    chat.style.bottom = "";
    chat.style.left   = "";
    chat.style.right  = "";

    switch (position) {
      case "bottom_left":
        chat.style.bottom = "90px";
        chat.style.left   = "20px";
        break;
      case "top_right":
        chat.style.top   = "90px";
        chat.style.right = "20px";
        break;
      case "top_left":
        chat.style.top  = "90px";
        chat.style.left = "20px";
        break;
      default: // bottom_right
        chat.style.bottom = "90px";
        chat.style.right  = "20px";
    }
  }

  function applyLauncherPosition(position) {
    const launcherEl = document.getElementById("chat-launcher");
    if (!launcherEl) return;

    launcherEl.style.top    = "";
    launcherEl.style.bottom = "";
    launcherEl.style.left   = "";
    launcherEl.style.right  = "";

    switch (position) {
      case "bottom_left":
        launcherEl.style.bottom = "20px";
        launcherEl.style.left   = "20px";
        break;
      case "top_right":
        launcherEl.style.top   = "20px";
        launcherEl.style.right = "20px";
        break;
      case "top_left":
        launcherEl.style.top  = "20px";
        launcherEl.style.left = "20px";
        break;
      default:
        launcherEl.style.bottom = "20px";
        launcherEl.style.right  = "20px";
    }
  }

  function setChatOpen(open) {
    const chat = document.querySelector(".popup-launch-bot-theme1");
    const launcherEl = document.getElementById("chat-launcher");
    if (chat) chat.style.display = open ? "flex" : "none";
    if (launcherEl) {
      launcherEl.style.display = "flex";
      launcherEl.classList.toggle("is-open", open);
      launcherEl.classList.toggle("is-closed", !open);
      launcherEl.setAttribute("aria-label", open ? "Minimize chat" : "Open chat");
    }
  }
}

initBot();
