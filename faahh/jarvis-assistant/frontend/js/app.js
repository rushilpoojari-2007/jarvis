let newsLoading = false;
let chatRecognition = null;
let chatIsListening = false;
let finalSpeechTranscript = '';
let interimSpeechTranscript = '';
let speechRecognitionError = false;
let currentConversationId = null;
let chatConversations = [];
let chatHistoryRequest = 0;
let selectedChatImage = null;

const CHAT_WELCOME_HTML = '<div class="chat-message assistant"><strong>JARVIS</strong><p>At your service, sir.</p></div>';

document.addEventListener('DOMContentLoaded', () => {
  const page = window.location.pathname.split('/').filter(Boolean)[0] || 'dashboard';
  document.querySelectorAll('.nav-link').forEach((link) => {
    const active = link.dataset.page === page;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page');
  });

  updateLiveClock();
  window.setInterval(updateLiveClock, 30_000);
  if (document.getElementById('dashboard-summary')) loadDashboard();

  if (document.getElementById('news-list')) {
    loadNews();
    document.getElementById('load-news').addEventListener('click', loadNews);
    document.getElementById('news-country').addEventListener('change', loadNews);
    document.getElementById('news-category').addEventListener('change', loadNews);
    document.getElementById('news-query').addEventListener('keydown', (event) => {
      if (event.key === 'Enter') loadNews();
    });
    window.setInterval(() => {
      if (!document.hidden && !newsLoading) loadNews();
    }, 5 * 60_000);
  }

  if (document.getElementById('weather-output')) {
    loadWeather();
    document.getElementById('load-weather').addEventListener('click', loadWeather);
    document.getElementById('weather-city').addEventListener('keydown', (event) => {
      if (event.key === 'Enter') loadWeather();
    });
    window.setInterval(() => {
      if (!document.hidden) loadWeather();
    }, 10 * 60_000);
  }

  if (document.getElementById('task-list')) {
    loadTasks();
    document.getElementById('task-form').addEventListener('submit', addTask);
    document.getElementById('task-list').addEventListener('click', handleTaskAction);
  }
  if (document.getElementById('briefing-output')) {
    loadBriefing();
    document.getElementById('generate-briefing').addEventListener('click', loadBriefing);
  }
  if (document.getElementById('chat-log')) {
    initConversationControls();
    initVoiceAssistant();
    document.getElementById('send-chat').addEventListener('click', sendChat);
    document.getElementById('new-chat').addEventListener('click', createNewChat);
    document.getElementById('attach-chat-image').addEventListener('click', () => {
      document.getElementById('chat-image-input').click();
    });
    document.getElementById('chat-image-input').addEventListener('change', selectChatImage);
    document.getElementById('remove-chat-image').addEventListener('click', clearChatImage);
    document.getElementById('conversation-select').addEventListener('change', (event) => {
      currentConversationId = Number(event.target.value);
      if (window.speechSynthesis) window.speechSynthesis.cancel();
      loadChatHistory(currentConversationId);
    });
    document.getElementById('chat-input').addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendChat();
      }
    });
  }
});

function updateLiveClock() {
  const now = new Date();
  const hour = now.getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  const greetingEl = document.getElementById('greeting');
  const clockEl = document.getElementById('live-clock');
  const dateEl = document.getElementById('live-date');
  if (greetingEl) greetingEl.textContent = `${greeting}, welcome back`;
  if (clockEl) clockEl.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (dateEl) dateEl.textContent = now.toLocaleDateString([], {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
  });
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);
}

function renderChatReply(value) {
  const textHtml = escapeHtml(String(value ?? '')).replace(/\n/g, '<br>');
  return textHtml ? `<p>${textHtml}</p>` : '';
}

function renderChatUserMessage(value, attachmentUrl = null) {
  const message = String(value ?? '');
  const marker = message.match(/\[\[JARVIS_UPLOAD:(\/static\/uploads\/[a-f0-9]{32}\.(?:jpg|png|webp))\]\]/i);
  const cleanText = marker ? message.replace(marker[0], '').trim() : message.trim();
  let imageUrl = marker?.[1] || attachmentUrl;
  if (imageUrl && !/^\/static\/uploads\/[a-f0-9]{32}\.(?:jpg|png|webp)$/i.test(imageUrl)
      && !/^data:image\/(?:png|jpeg|webp);base64,[A-Za-z0-9+/]+=*$/i.test(imageUrl)) {
    imageUrl = null;
  }
  const textHtml = escapeHtml(cleanText).replace(/\n/g, '<br>');
  const imageHtml = imageUrl
    ? `<img class="chat-upload-image" src="${imageUrl}" alt="Image attached to this message" />`
    : '';
  return `<strong>You:</strong>${textHtml ? `<p>${textHtml}</p>` : ''}${imageHtml}`;
}

function selectChatImage(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
    document.getElementById('voice-status').textContent = 'Choose a PNG, JPEG, or WebP image.';
    event.target.value = '';
    return;
  }
  if (file.size > 5 * 1024 * 1024) {
    document.getElementById('voice-status').textContent = 'Choose an image smaller than 5 MB.';
    event.target.value = '';
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    if (typeof reader.result !== 'string') return;
    if (selectedChatImage?.previewUrl) URL.revokeObjectURL(selectedChatImage.previewUrl);
    selectedChatImage = { file, dataUrl: reader.result, previewUrl: URL.createObjectURL(file) };
    const preview = document.getElementById('chat-attachment-preview');
    document.getElementById('chat-attachment-thumbnail').src = selectedChatImage.previewUrl;
    document.getElementById('chat-attachment-name').textContent = file.name;
    preview.hidden = false;
    document.getElementById('chat-input').focus();
  };
  reader.onerror = () => {
    document.getElementById('voice-status').textContent = 'Could not read that image. Please choose it again.';
    event.target.value = '';
  };
  reader.readAsDataURL(file);
}

function clearChatImage() {
  if (selectedChatImage?.previewUrl) URL.revokeObjectURL(selectedChatImage.previewUrl);
  selectedChatImage = null;
  document.getElementById('chat-image-input').value = '';
  document.getElementById('chat-attachment-thumbnail').removeAttribute('src');
  document.getElementById('chat-attachment-name').textContent = '';
  document.getElementById('chat-attachment-preview').hidden = true;
}

function safeNewsUrl(value) {
  try {
    const url = new URL(value, window.location.origin);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '#';
  } catch {
    return '#';
  }
}

async function loadDashboard() {
  try {
    const [settings, tasks, news] = await Promise.allSettled([
      api('/api/settings/'), api('/api/tasks/'), api('/api/news/'),
    ]);
    if (tasks.status === 'fulfilled') document.getElementById('task-count').textContent = tasks.value.tasks.length;
    if (news.status === 'fulfilled') document.getElementById('news-count').textContent = news.value.count || 0;
    if (settings.status === 'fulfilled') {
      document.getElementById('weather-status').textContent = settings.value.default_city || 'N/A';
      document.getElementById('dashboard-summary').textContent = `AI: ${settings.value.ai_enabled ? 'enabled' : 'disabled'} • News: ${settings.value.news_enabled ? 'enabled' : 'disabled'} • City: ${settings.value.default_city}`;
    } else {
      document.getElementById('dashboard-summary').textContent = 'Dashboard settings unavailable: ' + settings.reason.message;
    }
  } catch (error) {
    document.getElementById('dashboard-summary').textContent = 'Dashboard unavailable: ' + error.message;
  }
}

async function loadNews() {
  if (newsLoading) return;
  newsLoading = true;
  const button = document.getElementById('load-news');
  const updated = document.getElementById('news-updated');
  const list = document.getElementById('news-list');
  const originalLabel = button.textContent;
  button.disabled = true;
  button.textContent = 'Refreshing...';
  button.classList.add('is-loading');
  updated.textContent = 'Checking live feeds...';
  list.setAttribute('aria-busy', 'true');
  if (!list.children.length) list.innerHTML = '<div class="list-item loading-card"><span class="spinner"></span> Fetching the latest headlines...</div>';
  try {
    const query = document.getElementById('news-query').value.trim();
    const category = document.getElementById('news-category').value;
    const country = document.getElementById('news-country').value;
    const params = new URLSearchParams({ category, country });
    if (query) params.set('query', query);
    const data = await api(`/api/news/?${params.toString()}`);
    const newsCount = document.getElementById('news-count');
    if (newsCount) newsCount.textContent = data.count || 0;
    if (!data.articles.length) {
      list.innerHTML = `<div class="list-item">${escapeHtml(data.message || 'No news articles were returned.')}</div>`;
      updated.textContent = 'No stories returned';
      return;
    }
    list.innerHTML = data.articles.map((item) => `
      <div class="list-item">
        <h4><a href="${escapeHtml(safeNewsUrl(item.url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title)}</a></h4>
        <div class="article-meta"><span>${escapeHtml(item.source)}</span><time>${escapeHtml(formatArticleAge(item.published_at))}</time></div>
        <p>${escapeHtml(item.description || 'No summary available.')}</p>
      </div>
    `).join('');
    const edition = document.getElementById('news-country').selectedOptions[0].textContent;
    updated.textContent = `${edition} edition · Updated ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · ${data.count} stories`;
  } catch (error) {
    document.getElementById('news-list').innerHTML = `<div class="list-item">${escapeHtml(error.message)}</div>`;
    updated.textContent = 'Feed unavailable';
  } finally {
    newsLoading = false;
    button.disabled = false;
    button.textContent = originalLabel;
    button.classList.remove('is-loading');
    list.setAttribute('aria-busy', 'false');
  }
}

function formatArticleAge(value) {
  if (!value) return 'Time unavailable';
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return 'Time unavailable';
  const minutes = Math.round((timestamp - Date.now()) / 60_000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
  if (Math.abs(minutes) < 60) return formatter.format(minutes, 'minute');
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return formatter.format(hours, 'hour');
  return formatter.format(Math.round(hours / 24), 'day');
}

async function loadTasks() {
  try {
    const data = await api('/api/tasks/');
    const list = document.getElementById('task-list');
    const total = document.getElementById('task-total');
    const taskCount = document.getElementById('task-count');
    if (total) total.textContent = `${data.tasks.length} ${data.tasks.length === 1 ? 'task' : 'tasks'}`;
    if (taskCount) taskCount.textContent = data.tasks.length;
    if (!data.tasks.length) {
      list.innerHTML = '<div class="list-item">No tasks yet.</div>';
      return;
    }
    list.innerHTML = data.tasks.map((task) => `
      <div class="list-item">
        <h4>${escapeHtml(task.title)}</h4>
        <div class="article-meta"><span>${escapeHtml(task.priority)} priority</span><span>${escapeHtml(task.status)}</span></div>
        <p>${escapeHtml(task.description || 'No details')}</p>
        ${['done', 'cancelled'].includes(task.status) ? '' : `<div class="task-actions"><button type="button" data-task-id="${task.id}" data-task-status="done">Complete</button><button type="button" class="button-secondary" data-task-id="${task.id}" data-task-status="cancelled">Cancel</button></div>`}
      </div>
    `).join('');
  } catch (error) {
    document.getElementById('task-list').innerHTML = `<div class="list-item">${escapeHtml(error.message)}</div>`;
  }
}

async function handleTaskAction(event) {
  const button = event.target.closest('button[data-task-id][data-task-status]');
  if (!button) return;
  button.disabled = true;
  try {
    const { tasks } = await api('/api/tasks/');
    const task = tasks.find((item) => item.id === Number(button.dataset.taskId));
    if (!task) throw new Error('Task not found. Refresh the page and try again.');
    await api(`/api/tasks/${task.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        title: task.title,
        description: task.description || '',
        priority: task.priority,
        status: button.dataset.taskStatus,
        due_date: task.due_date || null,
      }),
    });
    await loadTasks();
  } catch (error) {
    alert(error.message);
    button.disabled = false;
  }
}

async function addTask(event) {
  event.preventDefault();
  const title = document.getElementById('task-title').value.trim();
  if (!title) return;
  const description = document.getElementById('task-description').value.trim();
  const priority = document.getElementById('task-priority').value;
  try {
    await api('/api/tasks/', {
      method: 'POST',
      body: JSON.stringify({ title, description, priority, status: 'pending' }),
    });
    document.getElementById('task-form').reset();
    await loadTasks();
  } catch (error) {
    alert(error.message);
  }
}

async function loadWeather() {
  try {
    const city = document.getElementById('weather-city').value.trim() || 'Belagavi';
    const data = await api(`/api/weather/?city=${encodeURIComponent(city)}`);
    document.getElementById('weather-output').innerHTML = `
      <strong>${escapeHtml(data.city)}</strong><br>
      ${escapeHtml(data.weather || 'Weather data')}<br>
      ${data.temperature_c !== null && data.temperature_c !== undefined ? `${escapeHtml(data.temperature_c)}°C` : ''}<br>
      ${escapeHtml(data.summary)}
    `;
  } catch (error) {
    document.getElementById('weather-output').textContent = error.message;
  }
}

async function loadBriefing() {
  try {
    const data = await api('/api/briefing/');
    document.getElementById('briefing-output').textContent = data.summary;
  } catch (error) {
    document.getElementById('briefing-output').textContent = error.message;
  }
}

function initVoiceAssistant() {
  const micButton = document.getElementById('voice-input');
  const stopButton = document.getElementById('stop-speaking');
  const speakToggle = document.getElementById('speak-replies');
  const languageSelect = document.getElementById('voice-language');
  const status = document.getElementById('voice-status');
  const input = document.getElementById('chat-input');
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const canSpeak = 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;

  try {
    const savedSpeakSetting = localStorage.getItem('jarvis-speak-replies');
    if (savedSpeakSetting !== null) speakToggle.checked = savedSpeakSetting === 'true';
    const savedLanguage = localStorage.getItem('jarvis-voice-language');
    if (savedLanguage && [...languageSelect.options].some((option) => option.value === savedLanguage)) {
      languageSelect.value = savedLanguage;
    }
  } catch {
    // Voice controls still work when browser storage is unavailable.
  }

  if (!canSpeak) {
    speakToggle.checked = false;
    speakToggle.disabled = true;
    status.textContent = 'Spoken replies are not supported in this browser.';
  }
  speakToggle.addEventListener('change', () => {
    try { localStorage.setItem('jarvis-speak-replies', String(speakToggle.checked)); } catch { /* Optional preference. */ }
    if (!speakToggle.checked && canSpeak) window.speechSynthesis.cancel();
  });
  languageSelect.addEventListener('change', () => {
    try { localStorage.setItem('jarvis-voice-language', languageSelect.value); } catch { /* Optional preference. */ }
  });

  stopButton.addEventListener('click', () => {
    if (canSpeak) window.speechSynthesis.cancel();
    stopButton.disabled = true;
    status.textContent = 'Speech stopped.';
  });

  if (!SpeechRecognition) {
    micButton.disabled = true;
    status.textContent = canSpeak
      ? 'Voice input is not supported in this browser. You can still hear replies and type messages.'
      : 'Voice is not supported in this browser. You can still type messages.';
    return;
  }
  if (!window.isSecureContext) {
    micButton.disabled = true;
    status.textContent = 'Microphone access requires localhost or a secure HTTPS connection.';
    return;
  }

  chatRecognition = new SpeechRecognition();
  chatRecognition.continuous = false;
  chatRecognition.interimResults = true;
  chatRecognition.maxAlternatives = 1;
  chatRecognition.lang = languageSelect.value;

  chatRecognition.onstart = () => {
    chatIsListening = true;
    speechRecognitionError = false;
    micButton.textContent = 'Listening...';
    micButton.classList.add('is-listening');
    micButton.setAttribute('aria-pressed', 'true');
    status.textContent = 'Listening. Speak now.';
  };

  chatRecognition.onresult = (event) => {
    interimSpeechTranscript = '';
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const transcript = event.results[index][0].transcript;
      if (event.results[index].isFinal) finalSpeechTranscript += `${transcript} `;
      else interimSpeechTranscript += transcript;
    }
    input.value = `${finalSpeechTranscript}${interimSpeechTranscript}`.trim();
    status.textContent = interimSpeechTranscript ? `Hearing: ${interimSpeechTranscript}` : 'Got it.';
  };

  chatRecognition.onerror = (event) => {
    speechRecognitionError = true;
    const messages = {
      'not-allowed': 'Microphone permission was denied. Allow microphone access in your browser settings.',
      'service-not-allowed': 'The browser speech service is unavailable or blocked.',
      'no-speech': 'I did not hear anything. Tap Speak and try again.',
      network: 'Voice recognition could not reach the browser speech service.',
      'audio-capture': 'No microphone was found. Check that a microphone is connected.',
    };
    status.textContent = messages[event.error] || `Voice input stopped (${event.error}). You can type instead.`;
  };

  chatRecognition.onend = () => {
    chatIsListening = false;
    micButton.textContent = 'Speak';
    micButton.classList.remove('is-listening');
    micButton.setAttribute('aria-pressed', 'false');
    if (finalSpeechTranscript.trim()) {
      input.value = finalSpeechTranscript.trim();
      status.textContent = 'Sending your voice request...';
      void sendChat({ fromVoice: true });
    } else if (!speechRecognitionError) {
      status.textContent = 'No speech detected. Tap Speak and try again.';
    }
    finalSpeechTranscript = '';
    interimSpeechTranscript = '';
  };

  micButton.addEventListener('click', () => {
    if (chatIsListening) {
      status.textContent = 'Finishing listening...';
      chatRecognition.stop();
      return;
    }
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    finalSpeechTranscript = '';
    interimSpeechTranscript = '';
    speechRecognitionError = false;
    input.value = '';
    chatRecognition.lang = languageSelect.value;
    try {
      chatRecognition.start();
    } catch (error) {
      status.textContent = `Could not start the microphone: ${error.message}`;
    }
  });
}

function speakChatReply(text) {
  const speakToggle = document.getElementById('speak-replies');
  if (!speakToggle?.checked || !('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window)) return;

  const status = document.getElementById('voice-status');
  const stopButton = document.getElementById('stop-speaking');
  const language = document.getElementById('voice-language').value;
  const cleanText = String(text || '').replace(/https?:\/\/\S+/g, '').replace(/[|*_#`]/g, ' ').replace(/\s+/g, ' ').trim();
  if (!cleanText) return;
  const maxLength = 700;
  const spokenText = cleanText.length > maxLength
    ? `${cleanText.slice(0, maxLength).replace(/\s+\S*$/, '')}. I have shown the rest in the chat.`
    : cleanText;
  const utterance = new SpeechSynthesisUtterance(spokenText);
  utterance.lang = language;
  utterance.rate = 1;
  const voices = window.speechSynthesis.getVoices();
  utterance.voice = voices.find((voice) => voice.lang.toLowerCase() === language.toLowerCase())
    || voices.find((voice) => voice.lang.toLowerCase().startsWith(language.slice(0, 2).toLowerCase()))
    || null;
  utterance.onstart = () => {
    stopButton.disabled = false;
    status.textContent = 'Speaking reply...';
  };
  utterance.onend = () => {
    stopButton.disabled = true;
    if (!chatIsListening) status.textContent = 'Voice ready.';
  };
  utterance.onerror = () => {
    stopButton.disabled = true;
    status.textContent = 'Could not play the spoken reply. The text is shown in chat.';
  };
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

async function sendChat({ fromVoice = false } = {}) {
  const input = document.getElementById('chat-input');
  const message = input.value.trim();
  const imageData = selectedChatImage?.dataUrl || null;
  if (!message && !imageData) return;
  if (!currentConversationId) {
    try {
      await loadConversations();
    } catch (error) {
      document.getElementById('voice-status').textContent = error.message;
      return;
    }
  }
  const sentConversationId = currentConversationId;
  const log = document.getElementById('chat-log');
  const userBubble = document.createElement('div');
  userBubble.className = 'chat-message user';
  userBubble.innerHTML = renderChatUserMessage(message, imageData);
  log.appendChild(userBubble);
  const sendButton = document.getElementById('send-chat');
  const micButton = document.getElementById('voice-input');
  const micWasDisabled = micButton.disabled;
  const pending = document.createElement('div');
  pending.className = 'chat-message assistant chat-pending';
  pending.innerHTML = '<strong>JARVIS:</strong><p>One moment, I am checking that...</p>';
  log.appendChild(pending);
  log.scrollTop = log.scrollHeight;
  sendButton.disabled = true;
  micButton.disabled = true;
  input.value = '';
  try {
    const query = new URLSearchParams({ conversation_id: String(sentConversationId) });
    const resp = await api(`/api/chat/?${query}`, {
      method: 'POST',
      body: JSON.stringify({ message, image: imageData }),
    });
    if (resp.history_cleared) {
      currentConversationId = resp.conversation.id;
      log.replaceChildren(pending);
      await loadConversations(currentConversationId);
    } else {
      await loadConversations(currentConversationId);
    }
    if (resp.image_url) userBubble.innerHTML = renderChatUserMessage(message || 'Image attached for review.', resp.image_url);
    if (imageData) clearChatImage();
    pending.innerHTML = `<strong>JARVIS:</strong>${renderChatReply(resp.reply)}`;
    if (fromVoice) document.getElementById('voice-status').textContent = 'Voice request complete.';
    if (currentConversationId === sentConversationId || resp.history_cleared) speakChatReply(resp.reply);
  } catch (error) {
    pending.innerHTML = `<strong>JARVIS:</strong><p>${escapeHtml(error.message)}</p>`;
    if (message && !input.value) input.value = message;
  } finally {
    pending.classList.remove('chat-pending');
    sendButton.disabled = false;
    micButton.disabled = micWasDisabled;
    if (currentConversationId === sentConversationId || !sentConversationId) log.scrollTop = log.scrollHeight;
  }
}

async function initConversationControls() {
  loadChatProviderStatus();
  try {
    await loadConversations();
  } catch {
    setChatWelcome();
  }
}

async function loadChatProviderStatus() {
  const status = document.getElementById('chat-provider-status');
  if (!status) return;
  try {
    const settings = await api('/api/settings/');
    const features = [
      settings.ai_enabled ? 'NVIDIA chat is configured.' : 'Add NVIDIA_API_KEY for chat.',
      settings.image_analysis_enabled ? 'NVIDIA image review is configured.' : 'Add NVIDIA_VISION_API_KEY for image review.',
    ];
    status.textContent = features.join(' ');
  } catch {
    status.textContent = 'AI configuration status is unavailable. Check that the JARVIS server is running.';
  }
}

async function loadConversations(preferredId = currentConversationId) {
  const selector = document.getElementById('conversation-select');
  const data = await api('/api/chat/conversations');
  chatConversations = data.conversations || [];
  if (!chatConversations.length) {
    const created = await api('/api/chat/conversations', { method: 'POST' });
    chatConversations = [created.conversation];
  }

  const selected = chatConversations.find((conversation) => conversation.id === Number(preferredId))
    || chatConversations[0];
  currentConversationId = selected.id;
  selector.innerHTML = chatConversations.map((conversation) =>
    `<option value="${conversation.id}">${escapeHtml(conversation.title || 'New chat')}</option>`
  ).join('');
  selector.value = String(currentConversationId);
  if (preferredId == null || Number(preferredId) !== currentConversationId) {
    await loadChatHistory(currentConversationId);
  }
}

async function createNewChat() {
  const button = document.getElementById('new-chat');
  button.disabled = true;
  try {
    const data = await api('/api/chat/conversations', { method: 'POST' });
    currentConversationId = data.conversation.id;
    chatConversations.unshift(data.conversation);
    const selector = document.getElementById('conversation-select');
    selector.innerHTML = chatConversations.map((conversation) =>
      `<option value="${conversation.id}">${escapeHtml(conversation.title || 'New chat')}</option>`
    ).join('');
    selector.value = String(currentConversationId);
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    setChatWelcome();
    document.getElementById('chat-input').focus();
  } catch (error) {
    document.getElementById('voice-status').textContent = `Couldn't start a new chat: ${error.message}`;
  } finally {
    button.disabled = false;
  }
}

function setChatWelcome() {
  document.getElementById('chat-log').innerHTML = CHAT_WELCOME_HTML;
}

async function loadChatHistory(conversationId = currentConversationId) {
  const log = document.getElementById('chat-log');
  const requestId = ++chatHistoryRequest;
  log.replaceChildren();
  try {
    const data = await api(`/api/chat/history?conversation_id=${encodeURIComponent(conversationId)}`);
    if (requestId !== chatHistoryRequest || conversationId !== currentConversationId) return;
    if (!data.messages.length) {
      setChatWelcome();
      return;
    }
    data.messages.forEach((entry) => {
      log.insertAdjacentHTML('beforeend', `
        <div class="chat-message user">${renderChatUserMessage(entry.message)}</div>
        <div class="chat-message assistant"><strong>JARVIS:</strong>${renderChatReply(entry.response)}</div>
      `);
    });
    log.scrollTop = log.scrollHeight;
  } catch {
    if (requestId === chatHistoryRequest) setChatWelcome();
  }
}
