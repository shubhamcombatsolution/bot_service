// Ensure BASE_URL and botId are defined (injected via chatbot.html)
if (typeof BASE_URL === 'undefined' || typeof botId === 'undefined') {
  console.error('BASE_URL or botId not defined');
}

// Configuration
const ACCESS_TOKEN = localStorage.getItem('access_token') || '';

// Initialize Draggabilly
const chatbotContainer = document.getElementById('chatbot-container');
const draggie = new Draggabilly(chatbotContainer, {
  containment: 'body'
});

// State
let isMinimized = false;
let isMenuOpen = false;
let messages = [];

// DOM Elements
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

// Fetch bot details
async function fetchBotDetails() {
  try {
    const response = await axios.get(`${BASE_URL}/custom-bot/get-customize/${botId}`);
    const botData = response.data.data;
    botName.textContent = botData.chatbot_name || 'Chatbot';
    botIcon.src = botData.avatar || '/chatbot/media/images/chatbot_img.png';
    minimizedIcon.src = botData.avatar || '/chatbot/media/images/chatbot_img.png';
    messageBody.style.backgroundImage = botData.background_image ? `url(${botData.background_image})` : '';
    trademarkText.textContent = botData.disclaimer_text || '© 2024 Tata Reality. All rights reserved.';
    // Set CSS custom properties for colors
    if (botData.colors && botData.colors.set1 && botData.colors.set2 && botData.colors.set3) {
      document.documentElement.style.setProperty('--primary-color', botData.colors.set1[0] || '#264C68');
      document.documentElement.style.setProperty('--secondary-color', botData.colors.set2[0] || '#F9F4F8');
      document.documentElement.style.setProperty('--tertiary-color', botData.colors.set3[0] || '#264C68');
    }
  } catch (error) {
    console.error('Error fetching bot details:', error);
    botName.textContent = 'Chatbot';
    botIcon.src = '/chatbot/media/images/chatbot_img.png';
    minimizedIcon.src = '/chatbot/media/images/chatbot_img.png';
  }
}

// Send greeting message
async function sendGreetingMessage() {
  try {
    const response = await axios.post(
      `${BASE_URL}/multi_agents/get_chat`,
      {
        query: 'hello',
        bot_id: botId,
        history: []
      },
      {
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${ACCESS_TOKEN}`
        },
        timeout: 20000
      }
    );
    let botResponse = response.data.response || 'No response from bot';
    botResponse = botResponse.replace(/^"(.*)"$/, '$1');
    messages = [{ text: botResponse, sender: 'bot' }];
    renderMessages();
  } catch (error) {
    console.error('Error fetching greeting:', error);
    messages = [{ text: 'Error reaching AI service', sender: 'bot' }];
    renderMessages();
  }
}

// Render messages
function renderMessages() {
  messagesContainer.innerHTML = '';
  messages.forEach((msg, index) => {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${msg.sender === 'user' ? 'user-message' : 'robot-message'}`;
    messageDiv.textContent = msg.text;
    messagesContainer.appendChild(messageDiv);
  });
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Send message
async function sendMessage(e) {
  e.preventDefault();
  if (!chatInput.value.trim()) return;
  messages.push({ text: chatInput.value, sender: 'user' });
  renderMessages();
  try {
    const response = await axios.post(
      `${BASE_URL}/multi_agents/get_chat`,
      {
        query: chatInput.value,
        bot_id: botId,
        history: []
      },
      {
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${ACCESS_TOKEN}`
        },
        timeout: 20000
      }
    );
    let botResponse = response.data.response || 'No response from bot';
    const match = botResponse.match(/\*\*You:\*\* (.*)/);
    if (match && match[1]) {
      botResponse = match[1].trim();
    }
    botResponse = botResponse.replace(/^"(.*)"$/, '$1');
    messages.push({ text: botResponse, sender: 'bot' });
    renderMessages();
  } catch (error) {
    console.error('Error:', error);
    messages.push({ text: 'Error reaching AI service', sender: 'bot' });
    renderMessages();
  }
  chatInput.value = '';
}

// Toggle minimize
function toggleMinimize() {
  isMinimized = !isMinimized;
  chatbotContainer.classList.toggle('minimized', isMinimized);
  minimizedContent.classList.toggle('hidden', !isMinimized);
  if (isMenuOpen) {
    isMenuOpen = false;
    chatMenu.classList.add('hidden');
  }
}

// Toggle menu
function toggleMenu() {
  isMenuOpen = !isMenuOpen;
  chatMenu.classList.toggle('hidden', !isMenuOpen);
}

// Clear chat
function clearChat() {
  messages = [];
  renderMessages();
  toggleMenu();
}

// Download chat
function downloadChat() {
  const chatContent = messages.map(msg => `${msg.sender}: ${msg.text}`).join('\n');
  const blob = new Blob([chatContent], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'chat_history.txt';
  a.click();
  URL.revokeObjectURL(url);
  toggleMenu();
}

// Event listeners
inputForm.addEventListener('submit', sendMessage);
chatCloseBtn.addEventListener('click', toggleMinimize);
chatMenuBtn.addEventListener('click', toggleMenu);
minimizedContent.addEventListener('click', toggleMinimize);
clearChatBtn.addEventListener('click', clearChat);
downloadBtn.addEventListener('click', downloadChat);

// Initialize
fetchBotDetails();
sendGreetingMessage();