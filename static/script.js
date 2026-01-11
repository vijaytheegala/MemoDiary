// Secure User Identity Management
let sessionId = localStorage.getItem('memodiary_user_id');
if (!sessionId) {
    // We'll let the backend generate the first secure ID on the first chat request
    sessionId = null;
}

// Session State Management
let chatMessages = [];
try {
    const storedHistory = sessionStorage.getItem('memodiary_chat_history');
    if (storedHistory) {
        chatMessages = JSON.parse(storedHistory);
    }
} catch (e) {
    console.warn("Failed to restore chat history:", e);
    chatMessages = [];
}

let lastUserText = "";

function saveChatHistory() {
    try {
        sessionStorage.setItem('memodiary_chat_history', JSON.stringify(chatMessages));
    } catch (e) {
        console.warn("Failed to save chat history:", e);
    }
}

// Global retry function
window.retryLastMessage = function () {
    const btn = document.getElementById('retry-btn-active');
    if (btn) btn.remove(); // Remove button to prevent double clicks

    if (lastUserText) {
        // Remove the error message (last AI message) if we want? 
        // Or just let the new message appear below.
        // Let's just retry.
        addMessageToUI('user', lastUserText, true); // Re-add user message or just send?
        // Actually, usually retry implies re-sending the LAST attempt. 
        // The user message is already in the chat. We shouldn't duplicate the user message visually if it's already there.
        // But `sendMessageToAI` doesn't add user message, `handleTextInput` does.
        // So we just call sendMessageToAI.
        sendMessageToAI(lastUserText);
    }
};

const micButton = document.getElementById('micButton');
const statusText = document.getElementById('statusText');
const chatHistory = document.getElementById('chatHistory');
const currentMood = document.getElementById('currentMood');
const userInput = document.getElementById('userInput');
const sendButton = document.getElementById('sendButton');
const profileButton = document.getElementById('profileButton');
const aboutButton = document.getElementById('aboutButton');
const muteButton = document.getElementById('muteButton');
const muteIcon = document.getElementById('muteIcon');

// Mute State Initialization
let isMuted = localStorage.getItem('memodiary_is_muted') === 'true';

function updateMuteIcon() {
    if (isMuted) {
        // Muted Icon
        muteIcon.innerHTML = `
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
            <line x1="23" y1="9" x2="17" y2="15"></line>
            <line x1="17" y1="9" x2="23" y2="15"></line>
        `;
        muteButton.classList.add('muted'); // Optional styling hook
    } else {
        // Unmuted Icon (Volume Up)
        muteIcon.innerHTML = `
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
            <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
        `;
        muteButton.classList.remove('muted');
    }
}
// Initial update
if (muteButton) updateMuteIcon();

// --- REPLACEMENT: Backend-Powered Speech Recognition (MediaRecorder) ---
let mediaRecorder = null;
let audioChunks = [];
let isListening = false; // Track state
let silenceTimer = null;
const SILENCE_TIMEOUT = 2000; // 2 seconds delay
let audioContext = null;
let analyser = null;
let microphone = null;
let animationFrame = null;

async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });

        audioChunks = [];

        mediaRecorder.ondataavailable = event => {
            if (event.data.size > 0) audioChunks.push(event.data);
        };

        mediaRecorder.onstop = async () => {
            stopVAD(); // Stop visualizer/VAD

            // Create Blob
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            if (audioBlob.size < 1000) {
                // Too small, ignore
                resetMicUI();
                return;
            }

            // Send to Backend
            statusText.textContent = "Transcribing...";
            statusText.style.color = "var(--accent-primary)";

            // UI Change: Switch from 'listening' (Red) to 'transcribing' (Theme Color)
            micButton.classList.remove('listening');
            micButton.classList.add('transcribing');

            try {
                const formData = new FormData();
                formData.append("file", audioBlob, "voice.webm");

                const response = await fetch('/api/transcribe', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) throw new Error("Transcription Failed");

                const data = await response.json();
                const text = data.text;

                if (text && text.length > 0) {
                    addMessageToUI('user', text);
                    sendMessageToAI(text);
                } else {
                    statusText.textContent = "I didn't catch that.";
                }
            } catch (e) {
                console.error("Transcribe Error:", e);
                statusText.textContent = "Error hearing you.";
            } finally {
                resetMicUI();
                // Stop all tracks
                stream.getTracks().forEach(track => track.stop());
            }
        };

        mediaRecorder.start();
        isListening = true;
        micButton.classList.add('listening');
        statusText.textContent = "Listening... (Click to stop)";
        statusText.style.color = "#f87171";

        // Start VAD / Visualizer
        startVAD(stream);

    } catch (e) {
        console.error("Mic Error:", e);
        statusText.textContent = "Microphone Access Denied";
    }
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
    }
    isListening = false;
}

function resetMicUI() {
    micButton.classList.remove('listening');
    micButton.classList.remove('transcribing');
    statusText.textContent = "I’m here to hear you—press the mic to speak";
    statusText.style.color = "var(--text-muted)";
    isListening = false;
}

// Simple VAD / Audio Visualizer Setup
function startVAD(stream) {
    if (!audioContext) audioContext = new (window.AudioContext || window.webkitAudioContext)();
    analyser = audioContext.createAnalyser();
    microphone = audioContext.createMediaStreamSource(stream);
    microphone.connect(analyser);
    analyser.fftSize = 256;
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    let lastVoiceTime = Date.now();

    function detect() {
        analyser.getByteFrequencyData(dataArray);
        let sum = 0;
        for (let i = 0; i < bufferLength; i++) {
            sum += dataArray[i];
        }
        let average = sum / bufferLength;

        // Threshold for "Speech"
        if (average > 10) {
            lastVoiceTime = Date.now();
        }

        if (isListening) animationFrame = requestAnimationFrame(detect);
    }
    detect();
}

function stopVAD() {
    if (animationFrame) cancelAnimationFrame(animationFrame);
}


let isProcessing = false;
let abortController = null;
let lastRequestTime = 0;
const COOLDOWN_MS = 500;

// --- Voice Engine Initialization ---
let availableVoices = [];
function updateVoices() {
    availableVoices = window.speechSynthesis.getVoices();
}
if (window.speechSynthesis.onvoiceschanged !== undefined) {
    window.speechSynthesis.onvoiceschanged = updateVoices;
}
updateVoices();

// --- Event Listeners with Safety Checks ---

if (micButton) {
    micButton.addEventListener('click', () => {
        if (isListening) {
            stopRecording();
        } else {
            startRecording();
        }
    });
}

if (sendButton) sendButton.addEventListener('click', handleTextInput);
if (userInput) {
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleTextInput();
    });
}

if (profileButton) {
    profileButton.addEventListener('click', () => {
        if (sessionId) {
            alert(`Your ID ${sessionId} has been generated successfully.`);
        } else {
            alert("ID generation in progress... Please start a conversation.");
        }
    });
}

if (aboutButton) {
    aboutButton.addEventListener('click', () => {
        window.location.href = '/static/about.html';
    });
}

if (muteButton) {
    muteButton.addEventListener('click', () => {
        isMuted = !isMuted;
        localStorage.setItem('memodiary_is_muted', isMuted);
        updateMuteIcon();

        // If muting, stop any current speech
        if (isMuted) {
            window.speechSynthesis.cancel();
            if (window.currentAudio) {
                window.currentAudio.pause();
            }
        }
    });
}

async function initApp() {
    // 1. Check for existing session history (Navigation restoration)
    if (chatMessages.length > 0) {
        console.log("Restoring session history...");

        // Restore Messages
        chatMessages.forEach(msg => {
            // Pass save=false to avoid duplicating in state
            addMessageToUI(msg.role, msg.text, false);
        });

        // Restore Mood
        const storedMood = sessionStorage.getItem('memodiary_mood');
        if (storedMood) updateMood(storedMood, false);

        statusText.textContent = "I’m here to hear you—press the mic to speak";

        // Scroll to bottom
        setTimeout(() => {
            chatHistory.scrollTo({ top: chatHistory.scrollHeight, behavior: 'instant' });
        }, 100);

        return; // SKIP startup/welcome message
    }

    // 2. Fresh Start -> Call Startup
    try {
        const response = await fetch('/api/startup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId })
        });

        if (!response.ok) throw new Error("STARTUP_FAILED");
        const data = await response.json();

        // Update Session ID
        sessionId = data.session_id;
        localStorage.setItem('memodiary_user_id', sessionId);

        // Display Welcome Message
        addMessageToUI('ai', data.message);
        if (data.mood) updateMood(data.mood);

        statusText.textContent = "I’m here to hear you—press the mic to speak";

    } catch (error) {
        console.error("Startup Error:", error);
        statusText.textContent = "Connection failed. Please refresh.";
    }
}

// Auto-init on load
window.addEventListener('DOMContentLoaded', () => {
    initApp();
});

function handleTextInput() {
    const text = userInput.value.trim();
    const now = Date.now();

    // GUARD: Rate Limit / Cooldown
    if (now - lastRequestTime < COOLDOWN_MS) {
        statusText.textContent = "Take a breath... 😌";
        statusText.style.color = "var(--accent-primary)";
        return;
    }

    // GUARD: Validation
    if (!text || text.length < 2) return;

    // GUARD: Concurrent requests
    if (isProcessing) return;

    lastRequestTime = now;
    lastUserText = text; // Store for retry

    addMessageToUI('user', text);
    sendMessageToAI(text);
    userInput.value = '';
    userInput.blur();
}


// --- UI Interaction Logic ---

function addMessageToUI(role, text, save = true) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', role === 'user' ? 'user-message' : 'ai-message');

    const bubble = document.createElement('div');
    bubble.classList.add('bubble');
    bubble.innerHTML = formatMessage(text); // Basic formatting

    messageDiv.appendChild(bubble);
    chatHistory.appendChild(messageDiv);

    // Persist to Session Storage
    if (save) {
        chatMessages.push({ role, text });
        saveChatHistory();
    }

    // Smooth scroll to bottom
    setTimeout(() => {
        chatHistory.scrollTo({
            top: chatHistory.scrollHeight,
            behavior: 'smooth'
        });
    }, 100);

    return messageDiv; // Return for further modification (Retry button)
}

// Queue to manage sequential playback of sentence audio chunks
const audioQueue = [];
let isPlayingAudio = false;

async function processAudioQueue() {
    if (isPlayingAudio || audioQueue.length === 0) return;
    isPlayingAudio = true;

    // Dequeue next text chunk
    const textToSpeak = audioQueue.shift();

    if (isMuted) {
        isPlayingAudio = false;
        // If there are more in queue, process next (though we shouldn't really queue if muted)
        if (audioQueue.length > 0) processAudioQueue();
        return;
    }

    try {
        await playAudioChunk(textToSpeak);
    } catch (e) {
        console.warn("Audio chunk failed:", e);
    } finally {
        isPlayingAudio = false;
        if (audioQueue.length > 0) processAudioQueue();
    }
}

async function playAudioChunk(text) {
    return new Promise((resolve, reject) => {
        const audioUrl = `/api/tts?text=${encodeURIComponent(text)}&session_id=${sessionId}`;
        const audio = new Audio(audioUrl);
        window.currentAudio = audio; // Track current global

        audio.onended = () => resolve();
        audio.onerror = (e) => {
            console.warn("TTS Fetch Error", e);
            // Attempt browser fallback for this chunk?
            fallbackToBrowserTTS(text);
            resolve(); // Don't block queue on error
        };

        audio.play().catch(e => {
            console.warn("Autoplay blocked or error:", e);
            resolve();
        });
    });
}

async function sendMessageToAI(message) {
    if (isProcessing) return; // double-check guard

    isProcessing = true;
    setInputState(false); // Disable inputs

    statusText.textContent = "Reflecting...";
    statusText.style.color = "var(--accent-primary)";

    // Show Loading Animation
    showTypingIndicator();
    let messageDiv = null;
    let bubbleContent = null;

    // Setup Timeout (60s) - Increased for long inputs/slow processing
    abortController = new AbortController();
    const timeoutId = setTimeout(() => abortController.abort(), 60000);

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                message: message,
                stream: true
            }),
            signal: abortController.signal
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
            const errorText = `ERR_${response.status}`;
            if (response.status === 429) {
                throw new Error("RATE_LIMIT");
            } else if (response.status === 503) {
                throw new Error("SERVICE_OVERLOAD");
            }
            throw new Error(errorText);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let done = false;
        let aiFullText = "";
        let sentenceBuffer = "";

        while (!done) {
            const { value, done: readerDone } = await reader.read();
            done = readerDone;
            if (value) {
                const chunk = decoder.decode(value, { stream: true });
                // Split by double newline to separate SSE messages
                const blocks = chunk.split('\n\n');

                for (const block of blocks) {
                    if (!block.trim()) continue;

                    // Initialize message UI on first data arrival
                    if (!messageDiv) {
                        removeTypingIndicator();
                        messageDiv = addMessageToUI('ai', '', false); // Empty initially, don't save empty
                        bubbleContent = messageDiv.querySelector('.bubble');
                    }

                    const blockLines = block.split('\n');
                    let eventType = 'message';
                    let dataContent = '';

                    for (const row of blockLines) {
                        if (row.startsWith('event: ')) {
                            eventType = row.replace('event: ', '').trim();
                        } else if (row.startsWith('data: ')) {
                            dataContent = row.replace('data: ', '');
                        }
                    }

                    if (eventType === 'session_id') {
                        if (dataContent) {
                            console.log("New Session ID received:", dataContent);
                            sessionId = dataContent;
                            localStorage.setItem('memo_session_id', sessionId);
                        }
                        continue;
                    }

                    if (dataContent === '[DONE]') continue;
                    if (!dataContent) continue;

                    aiFullText += dataContent;

                    // Update UI seamlessly
                    if (bubbleContent) {
                        bubbleContent.innerHTML = formatMessage(aiFullText);
                    }

                    // --- TTS Streaming Logic ---
                    if (!isMuted) {
                        sentenceBuffer += dataContent;
                        // Check for sentence delimiters (. ? ! ) allow quotes ".'
                        const match = sentenceBuffer.match(/([^\.!\?]+[\.!\?]+)\s/);

                        if (match) {
                            const completedSentence = match[1];
                            audioQueue.push(completedSentence);
                            processAudioQueue();
                            sentenceBuffer = sentenceBuffer.replace(completedSentence, "").trimStart();
                        }
                    }
                }
            }
        }

        // Final flush of TTS buffer
        if (sentenceBuffer.trim() && !isMuted) {
            audioQueue.push(sentenceBuffer);
            processAudioQueue();
        }

        // Save to storage now that full text is ready
        if (aiFullText) {
            chatMessages.push({ role: 'ai', text: aiFullText });
            saveChatHistory();
        }

        statusText.textContent = "I’m here to hear you—press the mic to speak";
        statusText.style.color = "var(--text-muted)";

    } catch (error) {
        console.error("Interaction Error:", error);
        removeTypingIndicator(); // Ensure indicator is gone

        // If messageDiv wasn't created yet, create it for the error
        if (!messageDiv) {
            messageDiv = addMessageToUI('ai', '', false);
            bubbleContent = messageDiv.querySelector('.bubble');
        }

        let errorMessage = `I'm having a quiet moment. (${error.message || 'ERR_UNKNOWN'}) 😌`;
        let statusMsg = "Connection Error";
        let allowRetry = true;

        if (error.name === 'AbortError') {
            errorMessage = "I took a bit too long to think. (ERR_TIMEOUT) ⏳";
            statusMsg = "Timed Out";
        } else if (error.message === "RATE_LIMIT") {
            errorMessage = "I'm a bit overwhelmed with thoughts right now. Let's take a breath. (ERR_429) 🤯";
            statusMsg = "Too Many Requests";
        } else if (error.message === "SERVICE_OVERLOAD") {
            errorMessage = "My thinking engine is briefly busy. I'll be ready in a moment. (ERR_503) 😵‍💫";
            statusMsg = "System Busy";
        }

        bubbleContent.innerHTML = formatMessage(errorMessage);

        // Append Retry Button if actionable
        if (allowRetry) {
            const retryBtn = document.createElement('button');
            retryBtn.id = 'retry-btn-active';
            retryBtn.textContent = 'Retry Request';
            retryBtn.style.cssText = `
                display: block;
                margin-top: 10px;
                padding: 8px 16px;
                background: var(--accent-primary);
                color: #0c0c12;
                border: none;
                border-radius: 12px;
                cursor: pointer;
                font-family: inherit;
                font-weight: 600;
                font-size: 0.9rem;
                transition: transform 0.2s;
             `;
            retryBtn.onmouseover = () => retryBtn.style.transform = 'scale(1.05)';
            retryBtn.onmouseout = () => retryBtn.style.transform = 'scale(1)';
            retryBtn.onclick = (e) => {
                e.stopPropagation();
                window.retryLastMessage();
            };
            bubbleContent.appendChild(retryBtn);
        }

        statusText.textContent = statusMsg;
        statusText.style.color = "#f87171";
    } finally {
        isProcessing = false;
        setInputState(true); // Re-enable inputs
        abortController = null;

        // Focus back on input for convenience
        if (userInput) {
            setTimeout(() => {
                userInput.focus();
                // Ensure cursor is at the end
                userInput.selectionStart = userInput.selectionEnd = userInput.value.length;
            }, 100);
        }
    }
}

function setInputState(enabled) {
    userInput.disabled = !enabled;
    sendButton.disabled = !enabled;

    if (enabled) {
        sendButton.classList.remove('disabled-state');
        userInput.classList.remove('disabled-state');
    } else {
        sendButton.classList.add('disabled-state');
        userInput.classList.add('disabled-state');
    }
}

function showTypingIndicator() {
    if (document.getElementById('typingIndicator')) return;

    const indicator = document.createElement('div');
    indicator.classList.add('typing-indicator', 'message', 'ai-message');
    indicator.id = 'typingIndicator';

    indicator.innerHTML = `
        <div class="bubble">
            <div class="dot"></div>
            <div class="dot"></div>
            <div class="dot"></div>
        </div>
    `;

    chatHistory.appendChild(indicator);
    chatHistory.scrollTo({ top: chatHistory.scrollHeight, behavior: 'smooth' });
}

function removeTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) {
        indicator.remove();
    }
}

function updateMood(emoji, save = true) {
    if (emoji) {
        currentMood.textContent = emoji;
        currentMood.style.animation = 'none';
        currentMood.offsetHeight; // trigger reflow
        currentMood.style.animation = 'float 4s infinite ease-in-out';

        if (save) {
            sessionStorage.setItem('memodiary_mood', emoji);
        }
    }
}

async function speakResponse(text) {
    if (!text) return;
    if (isMuted) return; // Respect mute setting

    // Clean text for TTS
    const cleanText = text.replace(/[^\w\s\d,.!?]/gi, '').substring(0, 1000);

    try {
        // Stop any currently playing audio or speech
        window.speechSynthesis.cancel();
        if (window.currentAudio) {
            window.currentAudio.pause();
        }

        // OPTIMIZATION: Use GET request for simpler streaming via native Audio element
        // This allows the browser to buffer and play immediately instead of waiting for full blob
        const audioUrl = `/api/tts?text=${encodeURIComponent(cleanText)}&session_id=${sessionId}`;

        const audio = new Audio(audioUrl);
        window.currentAudio = audio;

        // Handle playback errors (like 429 or 500 which appear as loading errors on the media)
        audio.onerror = () => {
            console.warn("Audio stream failed, trying fallback...");
            fallbackToBrowserTTS(cleanText);
        };

        await audio.play();
    } catch (error) {
        console.warn("Backend TTS init failed:", error);
        fallbackToBrowserTTS(cleanText);
    }
}

function fallbackToBrowserTTS(text) {
    // Fallback to browser synthesis
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'en-US';
    const voices = window.speechSynthesis.getVoices();
    const femaleVoice =
        voices.find(v => v.name.includes('Aria')) ||
        voices.find(v => v.name.includes('Google US English') && v.name.includes('Female')) ||
        voices.find(v => v.name.toLowerCase().includes('female') && v.lang.startsWith('en'));

    if (femaleVoice) utterance.voice = femaleVoice;
    utterance.rate = 0.9;
    window.speechSynthesis.speak(utterance);
}

// Basic Formatter Helper (Markdown-lite)
function formatMessage(text) {
    if (!text) return '';

    // Bold
    let formatted = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    // Italic
    formatted = formatted.replace(/\*(.*?)\*/g, '<em>$1</em>');

    // Links
    formatted = formatted.replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank">$1</a>');

    // Newlines to BR
    formatted = formatted.replace(/\n/g, '<br>');

    return formatted;
}
