
function getCurrentScriptTag() {
  if (document.currentScript) return document.currentScript;
  const scripts = Array.from(document.getElementsByTagName("script"));
  for (let i = scripts.length - 1; i >= 0; i--) {
    const src = scripts[i].getAttribute("src") || "";
    if (src.includes("LaunchBot.js")) return scripts[i];
  }
  return null;
}

function getApiBase(scriptTag) {
  const explicitBase =
    (scriptTag && scriptTag.getAttribute("data-base-url")) ||
    window.LaunchBotBaseURL ||
    window.JnanicBaseUrl;
  if (explicitBase) return String(explicitBase).replace(/\/+$/, "");

  if (scriptTag) {
    const src = scriptTag.getAttribute("src") || "";
    if (src) {
      try {
        const parsed = new URL(src, window.location.href);
        return parsed.origin;
      } catch (_) {}
    }
  }
  return `${window.location.protocol}//${window.location.host}`;
}

function isLikelyInstanceId(value) {
  if (!value) return false;
  const v = String(value).trim();
  if (!v) return false;
  return (
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(v) ||
    /^[A-Za-z0-9_-]{16,}$/.test(v)
  );
}

function resolveInstanceId(scriptTag) {
  // All supported attribute names (data-* and legacy bare names)
  const attrNames = [
    "data-instance-id",
    "data-instance",
    "data-bot-instance",
    "instance_id",
    "instanceId",
  ];

  for (const attr of attrNames) {
    const val = scriptTag && scriptTag.getAttribute(attr);
    if (val && val.trim()) return val.trim();
  }

  // Try query-string of the script src
  if (scriptTag) {
    const src = scriptTag.getAttribute("src") || "";
    if (src) {
      try {
        const parsed = new URL(src, window.location.href);
        const fromQuery =
          parsed.searchParams.get("instance_id") ||
          parsed.searchParams.get("instanceId");
        if (fromQuery) return fromQuery.trim();
      } catch (_) {}
    }
  }

  // Global fallbacks
  if (window.JnanicInstanceId) return String(window.JnanicInstanceId).trim();
  if (window.BotInstanceId) return String(window.BotInstanceId).trim();

  // Last resort: path segment
  const fromPath = window.location.pathname.split("/").pop();
  if (isLikelyInstanceId(fromPath)) return fromPath;

  return "";
}

/**
 * Reads the API key from the script tag.
 * Supports: data-api-key, x-api-key (and their camelCase variants).
 */
function resolveApiKey(scriptTag) {
  if (!scriptTag) return "";
  const attrNames = ["data-api-key", "x-api-key", "data-x-api-key", "apikey", "api_key"];
  for (const attr of attrNames) {
    const val = scriptTag.getAttribute(attr);
    if (val && val.trim()) return val.trim();
  }
  return window.LaunchBotApiKey ? String(window.LaunchBotApiKey).trim() : "";
}

function ensureRootContainer() {
  let root = document.getElementById("chatbot-root");
  if (root) {
    root.style.position = "fixed";
    root.style.inset = "0";
    root.style.width = "0";
    root.style.height = "0";
    root.style.zIndex = "2147483647";
    root.style.pointerEvents = "none";
    root.style.isolation = "isolate";
    ensureRootInteractionStyles();
    return root;
  }

  root = document.createElement("div");
  root.id = "chatbot-root";
  root.style.position = "fixed";
  root.style.inset = "0";
  root.style.width = "0";
  root.style.height = "0";
  root.style.zIndex = "2147483647";
  root.style.pointerEvents = "none";
  root.style.isolation = "isolate";
  ensureRootInteractionStyles();

  if (document.body) {
    document.body.appendChild(root);
  } else {
    document.addEventListener(
      "DOMContentLoaded",
      () => {
        if (!document.getElementById("chatbot-root")) {
          document.body.appendChild(root);
        }
      },
      { once: true }
    );
  }
  return root;
}

function ensureRootInteractionStyles() {
  const styleId = "launchbot-root-interaction";
  if (document.getElementById(styleId)) return;
  const style = document.createElement("style");
  style.id = styleId;
  style.textContent = `
    #chatbot-root .popup-launch-bot-theme1,
    #chatbot-root .popup-launch-bot-theme2,
    #chatbot-root #chat-launcher {
      pointer-events: auto !important;
    }
  `;
  (document.head || document.documentElement).appendChild(style);
}

/* ─────────────────────────────────────────────────────────────
 * SECTION 2 – IP / Domain validation  (ported from JnanicChatbotJs.js)
 * ───────────────────────────────────────────────────────────── */

const DEPENDENCY_TIMEOUT = 20000;

function getHostnameFromUrl(url) {
  if (!url) return "";
  try {
    return new URL(url, window.location.href).hostname;
  } catch (_) {
    return "";
  }
}

function normalizeDomain(value) {
  if (!value) return "";
  let domain = String(value).trim().toLowerCase();
  if (!domain) return "";

  try {
    if (/^https?:\/\//i.test(domain)) {
      domain = new URL(domain).hostname;
    }
  } catch (_) {}

  return domain
    .replace(/:\d+$/, "")
    .replace(/^www\./, "");
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
    const ancestorOrigins = window.location && window.location.ancestorOrigins;
    if (ancestorOrigins && ancestorOrigins.length) {
      const ancestorHost = getHostnameFromUrl(ancestorOrigins[0]);
      if (ancestorHost) return normalizeDomain(ancestorHost);
    }

    const referrerHost = getHostnameFromUrl(document.referrer);
    if (referrerHost) return normalizeDomain(referrerHost);
  }

  return normalizeDomain(window.location.hostname);
}

function getTempTokenCacheKey(botId, domain) {
  return `launchbot_tempToken_${botId || "unknown"}_${domain || "unknown"}`;
}

/**
 * Fetches the visitor's public IP address by racing several free services.
 * Returns the IP string, or throws if all services fail.
 */
async function fetchPublicIP() {
  const ipServices = [
    { url: "https://api.ipify.org?format=json",  type: "json" },
    { url: "https://ipinfo.io/json",              type: "json" },
    { url: "https://ipv4.icanhazip.com",          type: "text" },
    { url: "https://api.myip.com",                type: "json" },
  ];

  return Promise.any(
    ipServices.map(async ({ url, type }) => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), DEPENDENCY_TIMEOUT);
      try {
        const res = await fetch(url, { cache: "no-store", signal: controller.signal });
        clearTimeout(timer);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        if (type === "text") return (await res.text()).trim();
        const data = await res.json();
        return data.ip || data.query;
      } catch (err) {
        clearTimeout(timer);
        throw err;
      }
    })
  );
}

/**
 * Calls /custom_bot_new/validate_client with the resolved bot_id, client IP,
 * and current hostname.  Stores the returned temp token in sessionStorage so
 * theme scripts (Theme 1 / Theme 2) can reuse it without re-validating.
 *
 * @param {string} apiBase   – origin of the chatbot server
 * @param {string} botId     – resolved bot_id (NOT instance_id)
 * @param {string} apiKey    – x-api-key value
 * @returns {Promise<string>} – the temp JWT token
 * @throws on network error or non-ok status
 */
async function validateClient(apiBase, botId, apiKey) {
  const domain = getClientDomain();
  if (!botId) throw new Error("Error: Bot not found.");
  if (!domain) throw new Error("Error: Unable to verify client domain.");

  // Keep the cache key scoped, but always revalidate on launcher boot so
  // restriction changes in the DB take effect immediately for script embeds.
  const cacheKey = getTempTokenCacheKey(botId, domain);

  const headers = { "Content-Type": "application/json" };
  if (apiKey) headers["X-API-Key"] = apiKey;

  const postValidation = async (ipValue) => {
    return fetch(`${apiBase}/custom_bot_new/validate_client`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        bot_id: botId,
        ip: ipValue || null,
        domain: domain,
      }),
    });
  };

  // Try once without IP first.
  // This allows bots with no restrictions to load even when public IP services are blocked.
  let res = await postValidation(null);

  // If access is denied, retry with resolved public IP (needed for IP-restricted bots).
  if (res.status === 403) {
    const ip = await fetchPublicIP();
    res = await postValidation(ip);
  }

  if (!res.ok) {
    const status = res.status;
    let msg = "Access denied by server.";
    if (status === 403) msg = "Error: Your IP or domain is not allowed to use this bot.";
    else if (status === 401) msg = "Error: Invalid API key.";
    else if (status === 404) msg = "Error: Bot not found.";
    throw Object.assign(new Error(msg), { status });
  }

  const data = await res.json();
  if (data.status !== "ok") throw new Error(data.message || "Validation failed.");

  const token = data.token;
  if (token) {
    try {
      sessionStorage.setItem(cacheKey, token);
    } catch (_) {}
  }
  return token;
}

/**
 * Shows a small, non-intrusive error banner inside #chatbot-root.
 */
function showValidationError(message) {
  const root = document.getElementById("chatbot-root");
  if (!root) return;
  root.innerHTML = `
    <div style="
      font-family: sans-serif;
      font-size: 13px;
      color: #b00020;
      background: #fff3f3;
      border: 1px solid #f5c6c6;
      border-radius: 8px;
      padding: 14px 18px;
      max-width: 340px;
      margin: 20px auto;
      text-align: center;
    ">${message}</div>`;
}

/* ─────────────────────────────────────────────────────────────
 * SECTION 3 – CSS / JS asset loaders
 * ───────────────────────────────────────────────────────────── */

function loadCSS(url, forceReload = false) {
  return new Promise((resolve) => {
    const href = new URL(url, window.location.href).href;
    if (forceReload) {
      Array.from(document.querySelectorAll("link[rel='stylesheet']")).forEach((l) => {
        if (l.href === href || l.href.startsWith(href.split("?")[0])) l.remove();
      });
    } else {
      const already = Array.from(document.querySelectorAll("link[rel='stylesheet']"))
        .some((l) => l.href === href);
      if (already) { resolve(); return; }
    }

    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    link.onload  = () => resolve();
    link.onerror = () => { console.error("[LaunchBot] CSS load failed:", url); resolve(); };
    (document.head || document.documentElement).appendChild(link);
  });
}

function loadScript(url, forceReload = false) {
  return new Promise((resolve, reject) => {
    const src = new URL(url, window.location.href).href;
    if (forceReload) {
      Array.from(document.querySelectorAll("script[src]")).forEach((s) => {
        if (s.src === src || s.src.startsWith(src.split("?")[0])) s.remove();
      });
    } else {
      const already = Array.from(document.querySelectorAll("script[src]"))
        .some((s) => s.src === src);
      if (already) { resolve(); return; }
    }

    const script = document.createElement("script");
    script.src = src;
    script.defer = true;
    script.onload  = () => resolve();
    script.onerror = () => reject(new Error(`[LaunchBot] Script load failed: ${url}`));
    (document.body || document.head || document.documentElement).appendChild(script);
  });
}

function cleanupLegacyBotUi(root) {
  try {
    const idsToRemove = ["chat-launcher", "jnanic-chatbot-wrapper", "chatbot-container"];
    idsToRemove.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.remove();
    });

    if (root) root.innerHTML = "";
  } catch (_) {}
}

function removeBotUiCompletely() {
  try {
    const selectorsToRemove = [
      "#chat-launcher",
      "#jnanic-chatbot-wrapper",
      "#chatbot-container",
      ".popup-launch-bot-theme1",
      ".popup-launch-bot-theme2",
      ".chat-launcher",
      ".chatbot-launcher",
    ];

    selectorsToRemove.forEach((selector) => {
      document.querySelectorAll(selector).forEach((el) => el.remove());
    });

    const root = document.getElementById("chatbot-root");
    if (root) root.remove();
  } catch (_) {}
}

/* ─────────────────────────────────────────────────────────────
 * SECTION 4 – Main boot sequence
 * ───────────────────────────────────────────────────────────── */

async function loadBot() {
  try {
    const scriptTag  = getCurrentScriptTag();
    const apiBase    = getApiBase(scriptTag);
    const instanceId = resolveInstanceId(scriptTag);
    const apiKey     = resolveApiKey(scriptTag);

    console.log("[LaunchBot] Instance ID:", instanceId);
    console.log("[LaunchBot] API base:", apiBase);

    if (!instanceId) {
      console.error(
        "[LaunchBot] No instance ID found. " +
        "Pass one via data-instance-id attribute or ?instance_id= query param."
      );
      return;
    }

    const root = ensureRootContainer();
    cleanupLegacyBotUi(root);

    /* ── 1. Fetch bot configuration ── */
    const configUrl = `${apiBase}/custom_bot_new/get-customize/${encodeURIComponent(instanceId)}`;
    const configHeaders = {};
    if (apiKey) configHeaders["x-api-key"] = apiKey;

    const res = await fetch(configUrl, { headers: configHeaders });
    if (!res.ok) {
      console.error("[LaunchBot] Failed to fetch bot config:", res.status, res.statusText);
      // showValidationError("Failed to load chatbot configuration. Please try again later.");
      return;
    }

    const data = await res.json();
    const bot  = data.data || {};

    /* ── 2. Resolve bot_id (needed for validation) ── */
    // The config endpoint may return bot_id directly; fall back to resolving via API
    let botId = bot.bot_id || data.bot_id || data?.data?.botId || "";
    if (!botId) {
      try {
        const resolveHeaders = { "Content-Type": "application/json" };
        if (apiKey) resolveHeaders["X-API-Key"] = apiKey;

        const rRes = await fetch(
          `${apiBase}/custom_bot_new/resolve-instance/${encodeURIComponent(instanceId)}`,
          { headers: resolveHeaders }
        );
        if (rRes.ok) {
          const rData = await rRes.json();
          botId = rData?.data?.bot_id || "";
        }
      } catch (rErr) {
        console.warn("[LaunchBot] Could not resolve bot_id:", rErr);
      }
    }

    /* ── 3. IP / Domain validation ── */
    if (!botId) {
      console.error("[LaunchBot] bot_id could not be resolved – blocking chatbot load.");
      showValidationError("Error: Bot not found.");
      return;
    }

    try {
      const token = await validateClient(apiBase, botId, apiKey);
      // Make token available to theme scripts
      window.__LaunchBotToken = token;
      console.log("[LaunchBot] Client validated ✓", {
        bot_id: botId,
        domain: getClientDomain(),
      });
    } catch (validationErr) {
      console.error("[LaunchBot] Validation failed:", validationErr.message);
      removeBotUiCompletely();
      // For explicit allowlist restrictions, fail silently with no launcher/error bubble.
      if (validationErr && validationErr.status === 403) return;
      ensureRootContainer();
      showValidationError(validationErr.message || "Access denied.");
      return; // Stop – do NOT load the theme
    }

    /* ── 4. Store full config globally so theme scripts can read it ── */
    window.botConfig = {
      ...bot,
      instance_id: instanceId,
      base_url:    apiBase,
      api_key:     apiKey,
      bot_id:      botId || bot.bot_id || instanceId,
      // Pass the validated token so theme scripts don't need to re-validate
      _authToken:  window.__LaunchBotToken || null,
    };

    console.log("[LaunchBot] Bot config loaded:", window.botConfig);

    /* ── 5. Pick theme files ── */
    const isTheme2 =
      bot.theme === "Theme 2" ||
      bot.theme === "theme2" ||
      bot.theme === "emerald";

    const assetVersion = String(Date.now());
    const cssPath = isTheme2
      ? `${apiBase}/static/css/PopupLaunchBotTheme2.css?v=${assetVersion}`
      : `${apiBase}/static/css/PopupLaunchBotTheme1.css?v=${assetVersion}`;

    const jsPath = isTheme2
      ? `${apiBase}/static/js/PopupLaunchBotTheme2.js?v=${assetVersion}`
      : `${apiBase}/static/js/PopupLaunchBotTheme1.js?v=${assetVersion}`;

    /* ── 6. Load CSS first, then JS ── */
    await loadCSS(cssPath, true);
    await loadScript(jsPath, true);

    console.log("[LaunchBot] Theme loaded:", isTheme2 ? "Theme 2" : "Theme 1");
  } catch (err) {
    console.error("[LaunchBot] Unexpected error:", err);
  }
}

/* ── Boot ── */
if (!window.__LaunchBotBooted) {
  window.__LaunchBotBooted = true;
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadBot, { once: true });
  } else {
    loadBot();
  }
}
