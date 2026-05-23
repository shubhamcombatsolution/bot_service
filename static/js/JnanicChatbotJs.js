

document.addEventListener('DOMContentLoaded', () => {
  // Configuration
  let DEFAULT_AVATAR = '';
  const DEPENDENCY_TIMEOUT = 20000;
  const MAX_RETRIES = 3; // Maximum retry attempts for message sending
  const TOKEN_REFRESH_INTERVAL = 12 * 60 * 1000; // 12 minutes
  const DEFAULT_GREETING = "Hello! I'm your friendly assistant. How can I help you today?";

  // Extract instance_id, x-api-key, and domain from script tag
  let instanceId = null;
  let apiKey = null;
  let BASE_URL = null;
  let botId = null;
  const scripts = document.getElementsByTagName('script');
  for (let script of scripts) {
    if (script.src.includes('JnanicChatbotJs.js')) {
      instanceId = script.getAttribute('instance_id');
      apiKey = script.getAttribute('x-api-key');
      try {
        const url = new URL(script.src);
        BASE_URL = `${url.protocol}//${url.host}`;
      } catch (error) {
        console.error('Error parsing script src URL:', error.message);
      }
      console.log('Script found:', { src: script.src, instance_id: instanceId, api_key: apiKey, BASE_URL });
      break;
    }
  }

  // Fallback to window.location if BASE_URL is not set
  if (!BASE_URL) {
    console.warn('Could not extract domain from script src, falling back to window.location');
    BASE_URL = `${window.location.protocol}//${window.location.host}`;
  }

  // Always resolve default assets against the chatbot script host
  DEFAULT_AVATAR = `${BASE_URL}/custom_bot_new/uploads/avatars/chatbot_img.png`;

  if (!instanceId || !apiKey) {
    console.error('Error: Missing instance_id or x-api-key in script tag.');
    document.body.innerHTML += '<p style="color: red; text-align: center;">Error: Chatbot failed to load. Missing instance_id or x-api-key.</p>';
    return;
  }

  if (BASE_URL.startsWith('file://')) {
    console.error('Error: Cannot run chatbot from file:// protocol. Please host the HTML on a server.');
    document.body.innerHTML += '<p style="color: red; text-align: center;">Error: Chatbot cannot run from local file system. Please host on a server.</p>';
    return;
  }

  // Load external CSS
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = `${BASE_URL}/custom_bot_new/JnanicChatbotCss.css`;
  link.onerror = () => console.error('Failed to load JnanicChatbotCss.css');
  document.head.appendChild(link);

  // Load axios dependency
  const loadDependencies = () => {
    return new Promise((resolve, reject) => {
      if (window.axios) {
        console.log('Axios already loaded');
        resolve();
        return;
      }
      const script = document.createElement('script');
      script.src = 'https://cdn.jsdelivr.net/npm/axios/dist/axios.min.js';
      script.async = false;
      script.onload = () => {
        console.log('Axios loaded successfully');
        resolve();
      };
      script.onerror = () => {
        console.error('Failed to load axios');
        reject(new Error('Failed to load axios'));
      };
      document.head.appendChild(script);
    });
  };

  // Inject chatbot HTML
  const chatbotWrapper = document.createElement('div');
  chatbotWrapper.id = 'jnanic-chatbot-wrapper';
  document.body.appendChild(chatbotWrapper);
  const chatbotHTML = `
    <div id="chatbot-container" class="chatbot-container minimized">
      <div class="wave-container">
        <div class="chat-header">
          <span class="header-title">
            <img id="bot-icon" src="${DEFAULT_AVATAR}" alt="Bot Icon" class="header-icon">
            <span id="bot-name">Chatbot</span>
          </span>
          <div class="header-buttons">
            <div class="button-group">
              <button id="chatmenu-btn" aria-label="Open menu" title="Open menu">...</button>
              <button id="chatclose-btn" aria-label="Close chat" title="Close chat">×</button>
            </div>
            <nav id="chatmenu" class="chatmenu">
              <ul>
                <li><button id="download-btn" aria-label="Download chat" title="Download chat">⭳</button></li>
                <li><button id="clear-chat-btn" aria-label="Clear chat history" title="Clear chat history">↻</button></li>
                <li><button id="load-history-btn" aria-label="Load chat history" title="Load chat history">⟳</button></li>
              </ul>
            </nav>
          </div>
        </div>
        <svg viewBox="0 0 1440 320" preserveAspectRatio="xMidYMid meet">
          <path fill="none" stroke="#ffffff" stroke-width="20" d="M0,192 C480,320 960,64 1440,192 L1440,320 L0,320 Z"></path>
        </svg>
      </div>
      <div class="chatbot-body">
        <div id="chatbot-messagebody" class="chatbot-messagebody">
          <div id="messages" class="messages"></div>
        </div>
        <form id="input-form" class="input-form">
          <input type="text" id="chat-input" placeholder="Type your message...">
          <button type="submit">Send</button>
        </form>
        <div class="trademark-section">
          <a href="#" target="_blank" id="trademark-text">© 2025 Tata Realty. All rights reserved.</a>
        </div>
      </div>
      <div id="minimized-content" class="minimized-content">
        <img id="minimized-icon" src="${DEFAULT_AVATAR}" alt="Chatbot Icon" class="chatbot-icon">
      </div>
    </div>
  `;
  chatbotWrapper.innerHTML = chatbotHTML;

  // Initialize after dependencies are loaded
  loadDependencies()
    .then(() => {
      console.log('Dependencies loaded, initializing chatbot');
      initialize();
    })
    .catch(error => {
      console.error('Error loading dependencies:', error);
      chatbotWrapper.innerHTML = '<p style="color: red; text-align: center;">Error: Chatbot dependencies failed to load.</p>';
    });

  async function initialize() {
    // State
    let isMinimized = true;
    let isMenuOpen = false;
    let messages = [];
    let history = [];
    let hasFetchedGreeting = false;
    let botDetails = null;
    let isVerified = false;
    let sendRetryCount = 0;
    let isSending = false;

    // DOM Elements
    const chatbotContainer = document.getElementById('chatbot-container');
    const botIcon = document.getElementById('bot-icon');
    const botName = document.getElementById('bot-name');
    const messagesContainer = document.getElementById('messages');
    const inputForm = document.getElementById('input-form');
    const chatInput = document.getElementById('chat-input');
    const messageBody = document.getElementById('chatbot-messagebody');
    const trademarkText = document.getElementById('trademark-text');
    const minimizedContent = document.getElementById('minimized-content');
    const minimizedIcon = document.getElementById('minimized-icon');
    const chatMenuBtn = document.getElementById('chatmenu-btn');
    const chatCloseBtn = document.getElementById('chatclose-btn');
    const chatMenu = document.getElementById('chatmenu');
    const downloadBtn = document.getElementById('download-btn');
    const clearChatBtn = document.getElementById('clear-chat-btn');
    const loadHistoryBtn = document.getElementById('load-history-btn');

    if (!chatbotContainer) {
      console.error('Chatbot container not found in DOM');
      chatbotWrapper.innerHTML = '<p style="color: red; text-align: center;">Error: Chatbot container failed to initialize.</p>';
      return;
    }

    // Axios instance with x-api-key
    const axiosInstance = axios.create({
      baseURL: BASE_URL,
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': apiKey
      },
      timeout: DEPENDENCY_TIMEOUT
    });

    // Client info and token retrieval
    async function getClientInfo() {
      const ipServices = [
        { url: "https://api.ipify.org?format=json", type: "json" },
        { url: "https://ipinfo.io/json", type: "json" },
        { url: "https://ipv4.icanhazip.com", type: "text" },
        { url: "https://api.myip.com", type: "json" }
      ];

      let ip = null;
      try {
        const results = await Promise.any(
          ipServices.map(async (service) => {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), DEPENDENCY_TIMEOUT);
            const res = await fetch(service.url, {
              cache: "no-store",
              signal: controller.signal
            });
            clearTimeout(timeoutId);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            if (service.type === "text") return (await res.text()).trim();
            const data = await res.json();
            return data.ip || data.query;
          })
        );
        ip = results;
      } catch (err) {
        console.error("All IP services failed:", err);
        messages = [...messages.slice(0, -1), { text: "Error: Unable to fetch client IP. Please try again later.", sender: "bot" }];
        renderMessages();
        return false;
      }

      let domain = null;
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), DEPENDENCY_TIMEOUT);
        const dnsRes = await fetch(
          `https://dns.google/resolve?name=${ip}.in-addr.arpa&type=PTR`,
          { signal: controller.signal }
        );
        clearTimeout(timeoutId);
        const dnsData = await dnsRes.json();
        if (dnsData.Answer?.length > 0) {
          domain = dnsData.Answer[0].data.replace(/\.$/, "");
        }
      } catch (err) {
        console.warn("Reverse DNS lookup failed", err);
      }

      try {
        await resolveInstanceId(); // Ensure botId is resolved
        const validationRes = await axiosInstance.post(
          "/custom_bot_new/validate_client",
          {
            bot_id: botId,
            ip: ip,
            domain: window.location.hostname
          },
          {
            headers: { 'X-API-Key': apiKey }
          }
        );

        if (validationRes.data.status === "ok") {
          isVerified = true;
          const tempToken = validationRes.data.token;
          sessionStorage.setItem("tempToken", tempToken);
          axiosInstance.defaults.headers.common["Authorization"] = `Bearer ${tempToken}`;
          return true;
        }
      } catch (err) {
        isVerified = false;
        console.error("Error sending client info to backend:", err);
        let errorMessage = "Error: Chatbot service not available. Please try again later.";
        if (err.response?.status === 404) {
          errorMessage = "Error: Chatbot service not found. Please contact support.";
        } else if (err.response?.status === 403) {
          errorMessage = "Error: Access denied. Your IP or Domain is not allowed.";
        } else if (err.response?.status === 401) {
          errorMessage = "Error: Authentication failed. Please check your API key.";
        }
        messages = [...messages.slice(0, -1), { text: errorMessage, sender: "bot" }];
        renderMessages();
        return false;
      }
      return false;
    }

    // Resolve instance_id to bot_id
    async function resolveInstanceId() {
      try {
        console.log('Resolving instance_id:', instanceId);
        const response = await axiosInstance.get(`/custom_bot_new/resolve-instance/${instanceId}`);
        console.log('Resolve Instance API Response:', response.data);
        botId = response.data.data.bot_id;
        console.log('Resolved bot_id:', botId);
        return botId;
      } catch (error) {
        console.error('Error resolving instance_id:', {
          message: error.message,
          status: error.response?.status,
          data: error.response?.data
        });
        let errorMessage = "Error: Failed to resolve instance ID.";
        if (error.response?.status === 404) {
          errorMessage = `Bot not found for instance ID: ${instanceId}.`;
        } else if (error.response?.status === 400) {
          errorMessage = "Invalid request. Instance ID or API key may be missing.";
        } else if (error.response?.status === 401) {
          errorMessage = "Unauthorized. Please check your API key.";
        }
        messages = [{ text: errorMessage, sender: 'bot' }];
        renderMessages();
        throw error;
      }
    }

    // Apply colors
    function applyColors(colors) {
      if (colors && typeof colors === 'object') {
        const root = document.documentElement;
        Object.entries(colors).forEach(([key, value]) => {
          if (typeof value === 'string' && value.match(/^#[0-9A-Fa-f]{6}$|^rgb\(\d+,\s*\d+,\s*\d+\)$/)) {
            root.style.setProperty(`--${key}`, value);
          } else if (Array.isArray(value)) {
            const gradient = `linear-gradient(to right, ${value.join(', ')})`;
            root.style.setProperty(`--${key}-gradient`, gradient);
          }
        });
      }
    }

    // Update DOM with bot details
    function updateBotDetails() {
      botName.textContent = botDetails.chatbotName;
      botIcon.src = botDetails.avatar;
      minimizedIcon.src = botDetails.avatar;
      trademarkText.textContent = botDetails.disclaimerText;
      messageBody.style.backgroundImage = botDetails.backgroundImage ? `url(${botDetails.backgroundImage})` : '';
      applyColors(botDetails.colors);
    }

    // Fetch bot details
    async function fetchBotDetails() {
      if (sessionStorage.getItem("botDetails")) {
        botDetails = JSON.parse(sessionStorage.getItem("botDetails"));
        updateBotDetails();
        return;
      }

      try {
        await resolveInstanceId();
        if (!botId) {
          throw new Error('Failed to resolve bot_id');
        }

        console.log('Fetching bot details for instanceId:', instanceId);
        const token = sessionStorage.getItem("tempToken");
        const headers = { 'Content-Type': 'application/json', 'X-API-Key': apiKey };
        if (token) headers['Authorization'] = `Bearer ${token}`;
        const response = await axiosInstance.get(`/custom_bot_new/get-customize/${instanceId}`, { headers });
        console.log('Bot Details API Response:', response.data);
        const data = response.data.data || {};
        botDetails = {
          botId: data.bot_id,
          chatbotName: data.chatbot_name || 'Chatbot',
          disclaimerText: data.disclaimer_text || `© 2025 ${data.chatbot_name || 'Chatbot'}. All rights reserved.`,
          greetingType: data.greeting_type || 'dynamic',
          greetingMessage: data.greeting_type === 'static' ? data.greeting_message : null,
          avatar: data.avatar || DEFAULT_AVATAR,
          colors: data.colors || {
            primary: '#264C68',
            secondary: '#F9F4F8',
            tertiary: '#264C68',
            set1: ['#b54b30', '#cd7b3c', '#4b6eaf'],
            set2: ['#e0b79a', '#e193b9', '#77928b'],
            set3: ['#00c6ff', '#0072ff', '#4b0082']
          },
          backgroundImage: data.background_image || ''
        };
        console.log('Parsed Bot Details:', botDetails);
        sessionStorage.setItem("botDetails", JSON.stringify(botDetails));
        updateBotDetails();
      } catch (error) {
        console.error('Error fetching bot details:', {
          message: error.message,
          status: error.response?.status,
          data: error.response?.data
        });
        botDetails = {
          botId: null,
          chatbotName: 'Chatbot',
          disclaimerText: '© 2025 Tata Realty. All rights reserved.',
          greetingType: 'dynamic',
          greetingMessage: null,
          avatar: DEFAULT_AVATAR,
          colors: {
            primary: '#264C68',
            secondary: '#F9F4F8',
            tertiary: '#264C68',
            set1: ['#b54b30', '#cd7b3c', '#4b6eaf'],
            set2: ['#e0b79a', '#e193b9', '#77928b'],
            set3: ['#00c6ff', '#0072ff', '#4b0082']
          },
          backgroundImage: ''
        };
        updateBotDetails();
        let errorMessage = 'Failed to load bot details. Please try again later.';
        if (error.response?.status === 404) {
          errorMessage = `Bot not found for instance ID: ${instanceId}. Please ensure the instance ID and API key are correct.`;
        } else if (error.response?.status === 400) {
          errorMessage = 'Invalid request. Instance ID or API key may be missing.';
        } else if (error.response?.status === 401) {
          errorMessage = 'Unauthorized. Please check your API key.';
        }
        messages = [{ text: errorMessage, sender: 'bot' }];
        renderMessages();
      }
    }

    // Initialize chat
    async function initializeChat() {
      if (hasFetchedGreeting) return;
      hasFetchedGreeting = true;

      messages = [{ type: 'loading', sender: 'bot' }];
      renderMessages();

      try {
        await fetchBotDetails();
        if (!botDetails.botId) {
          messages = [{ text: 'Unable to initialize bot. Please check the instance ID and API key.', sender: 'bot' }];
          renderMessages();
          return;
        }

        if (botDetails.greetingType === 'static' && botDetails.greetingMessage) {
          messages = [{ text: botDetails.greetingMessage, sender: 'bot' }];
          renderMessages();
          return;
        }

        let historyMessages = [];
        let historyData = [];
        try {
          const token = sessionStorage.getItem("tempToken");
          const headers = token ? { Authorization: `Bearer ${token}`, 'X-API-Key': apiKey } : { 'X-API-Key': apiKey };
          const historyResponse = await axiosInstance.get(`/custom_bot_new/chat-history/${instanceId}`, { headers });
          console.log('Chat History API Response:', historyResponse.data);
          historyData = historyResponse.data.data?.history || [];
          historyMessages = historyData.map(entry => ({
            text: entry.response,
            sender: entry.query === 'static_greeting' ? 'bot' : entry.query === 'user' ? 'user' : 'bot'
          }));
          history = historyMessages;
        } catch (error) {
          console.error('Error fetching chat history:', {
            message: error.message,
            status: error.response?.status,
            data: error.response?.data
          });
          if (error.response?.status === 404) {
            console.log('No chat history found for instanceId:', instanceId);
            history = [];
            historyData = [];
          } else {
            history = [];
            historyData = [];
          }
        }

        let recentGreeting = historyMessages.find(
          msg =>
            msg.sender === 'bot' &&
            historyData.some(
              entry =>
                entry.response === msg.text &&
                entry.query === 'hello' &&
                new Date(entry.created_at) > new Date(Date.now() - 5 * 60 * 1000)
            )
        );

        if (recentGreeting) {
          messages = [{ text: recentGreeting.text, sender: 'bot' }];
        } else {
          messages = [{ text: DEFAULT_GREETING, sender: 'bot' }];
        }
      } catch (error) {
        console.error('Error initializing greeting:', {
          message: error.message,
          status: error.response?.status,
          data: error.response?.data
        });
        messages = [{ text: DEFAULT_GREETING, sender: 'bot' }];
      }
      renderMessages();
    }

    // Render messages
    function renderMessages() {
      messagesContainer.innerHTML = '';
      messages.forEach((msg, index) => {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${msg.sender === 'user' ? 'user-message' : 'robot-message'}`;
        if (msg.type === 'loading') {
          const spinnerDiv = document.createElement('div');
          spinnerDiv.className = 'message-spinner';
          const spinner = document.createElement('div');
          spinner.className = 'spinner';
          spinnerDiv.appendChild(spinner);
          messageDiv.appendChild(spinnerDiv);
        } else {
          messageDiv.textContent = msg.text;
        }
        messagesContainer.appendChild(messageDiv);
      });
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    // Send message
    async function sendMessage(e) {
      e.preventDefault();
      if (!chatInput.value.trim() || isSending) return;
      isSending = true;

      if (sendRetryCount >= MAX_RETRIES) {
        messages = [
          ...messages.slice(0, -1),
          { text: "Failed to send message after multiple attempts.", sender: "bot" }
        ];
        renderMessages();
        isSending = false;
        sendRetryCount = 0;
        return;
      }

      const userMessage = { text: chatInput.value, sender: 'user' };
      messages.push(userMessage, { type: 'loading', sender: 'bot' });
      renderMessages();
      chatInput.value = '';

      try {
        if (!isVerified) {
          const verified = await getClientInfo();
          if (!verified) {
            isSending = false;
            return; // Error message already added in getClientInfo, spinner removed
          }
        }

        const token = sessionStorage.getItem("tempToken");
        if (!token) {
          messages = [
            ...messages.slice(0, -1),
            { text: "Error: Authentication token missing. Please try again.", sender: "bot" }
          ];
          renderMessages();
          isSending = false;
          return;
        }

        const response = await axiosInstance.post(
          '/multi_agents/get_chat',
          {
            query: userMessage.text,
            bot_id: botDetails.botId,
            history: messages
              .filter(msg => msg.type !== 'loading')
              .map(msg => ({
                query: msg.sender === 'user' ? msg.text : '',
                response: msg.sender === 'bot' ? msg.text : ''
              }))
          },
          {
            timeout: DEPENDENCY_TIMEOUT,
            headers: { Authorization: `Bearer ${token}`, 'X-API-Key': apiKey }
          }
        );
        console.log('Message API Response:', response.data);
        let botResponse = response.data.response || 'No response from bot';
        botResponse = botResponse.replace(/^"(.*)"$/, '$1');
        messages = [...messages.slice(0, -1), { text: botResponse, sender: 'bot' }];
        sendRetryCount = 0;
      } catch (error) {
        console.error('Error sending message:', {
          message: error.message,
          status: error.response?.status,
          data: error.response?.data
        });
        let errorMessage = 'Error: Failed to process your message. Please try again.';
        if (error.response?.status === 403) {
          errorMessage = 'Error: Access denied. Please check your permissions.';
        } else if (error.response?.status === 404) {
          errorMessage = 'Error: Chat service not found. Please contact support.';
        } else if (error.response?.status === 400) {
          errorMessage = 'Invalid request. Instance ID or API key may be missing.';
        } else if (error.response?.status === 401) {
          errorMessage = 'Error: Authentication failed. Please try again.';
        }
        messages = [...messages.slice(0, -1), { text: errorMessage, sender: 'bot' }];
        sendRetryCount++;
      }
      renderMessages();
      isSending = false;
    }

    // Toggle minimize
    function toggleMinimize() {
      isMinimized = !isMinimized;
      chatbotContainer.classList.toggle('minimized', isMinimized);
      if (isMenuOpen) {
        isMenuOpen = false;
        chatMenu.classList.remove('active');
      }
    }

    // Toggle menu
    function toggleMenu() {
      isMenuOpen = !isMenuOpen;
      chatMenu.classList.toggle('active', isMenuOpen);
    }

    // Clear chat
    function clearChat() {
      const greetingMessage =
        botDetails?.greetingType === 'static' && botDetails?.greetingMessage
          ? botDetails.greetingMessage
          : DEFAULT_GREETING;
      messages = [{ text: greetingMessage, sender: 'bot' }];
      renderMessages();
      toggleMenu();
    }

    // Download chat
    function downloadChat() {
      const chatContent = messages
        .filter(msg => msg.type !== 'loading')
        .map(msg => `${msg.sender}: ${msg.text}`)
        .join('\n');
      const blob = new Blob([chatContent], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'chat_history.txt';
      a.click();
      URL.revokeObjectURL(url);
      toggleMenu();
    }

    // Load chat history
    async function loadHistory() {
      try {
        // const token = sessionStorage.getItem("tempToken");
        // if (!token) {
        //   messages = [
        //     ...messages,
        //     { text: "Error: Authentication token missing. Please send a message to authenticate.", sender: "bot" }
        //   ];
        //   renderMessages();
        //   return;
        // }
        const historyResponse = await axiosInstance.get(`/custom_bot_new/chat-history/${instanceId}`, {
          // headers: { Authorization: `Bearer ${token}`, 'X-API-Key': apiKey }
          headers: {'X-API-Key': apiKey }
        });
        console.log('Load History API Response:', historyResponse.data);
        const historyData = historyResponse.data.data?.history || [];
        const historyMessages = historyData.map(entry => ({
          text: entry.response,
          sender: entry.query === 'static_greeting' ? 'bot' : entry.query === 'user' ? 'user' : 'bot'
        }));
        history = historyMessages;
        messages = [
          ...historyMessages,
          ...messages.filter(
            msg => msg.sender === 'user' || !historyMessages.some(h => h.text === msg.text)
          )
        ];
      } catch (error) {
        console.error('Error loading chat history:', {
          message: error.message,
          status: error.response?.status,
          data: error.response?.data
        });
        let errorMessage =
          error.response?.status === 404
            ? 'No chat history available.'
            : error.response?.status === 400
            ? 'Invalid request. Instance ID or API key may be missing.'
            : error.response?.status === 401
            ? 'Unauthorized. Please check your API key.'
            : error.response?.status === 403
            ? 'Access denied. Unable to load chat history.'
            : 'Failed to load chat history.';
        messages = [...messages, { text: errorMessage, sender: 'bot' }];
      }
      renderMessages();
      toggleMenu();
    }

    // Event listeners
    inputForm.addEventListener('submit', sendMessage);
    chatCloseBtn.addEventListener('click', toggleMinimize);
    chatMenuBtn.addEventListener('click', toggleMenu);
    minimizedContent.addEventListener('click', toggleMinimize);
    clearChatBtn.addEventListener('click', clearChat);
    downloadBtn.addEventListener('click', downloadChat);
    loadHistoryBtn.addEventListener('click', loadHistory);

    // Initialize
    initializeChat();

    // Refresh token periodically if verified
    setInterval(async () => {
      if (isVerified) {
        console.log("Refreshing token...");
        await getClientInfo();
      }
    }, TOKEN_REFRESH_INTERVAL);
  }
});
