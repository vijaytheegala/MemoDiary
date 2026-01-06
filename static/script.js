// Secure User Identity Management
let sessionId = localStorage.getItem('memodiary_user_id');
if (!sessionId) {
    // We'll let the backend generate the first secure ID on the first chat request
    sessionId = null;
}

const micButton = document.getElementById('micButton');
const statusText = document.getElementById('statusText');
const chatHistory = document.getElementById('chatHistory');
const currentMood = document.getElementById('currentMood');
const userInput = document.getElementById('userInput');
const sendButton = document.getElementById('sendButton');
const profileButton = document.getElementById('profileButton');
const aboutButton = document.getElementById('aboutButton');

// Web Speech API Configuration
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const recognition = SpeechRecognition ? new SpeechRecognition() : null;
if (recognition) {
    recognition.continuous = true;
    recognition.lang = 'en-US';
    recognition.interimResults = false;
}

let isListening = false;
let transcriptBuffer = '';
let isProcessing = false;
let abortController = null;
let lastRequestTime = 0;
const COOLDOWN_MS = 2000;

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
            isListening = false;
            recognition.stop();
            if (transcriptBuffer.trim().length > 2) {
                const finalTranscript = transcriptBuffer.trim();
                transcriptBuffer = '';
                addMessageToUI('user', finalTranscript);
                sendMessageToAI(finalTranscript);
            } else {
                transcriptBuffer = '';
                if (statusText) statusText.textContent = "I’m here to hear you—press the mic to speak";
                if (statusText) statusText.style.color = "var(--text-muted)";
            }
        } else {
            transcriptBuffer = '';
            recognition.start();
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

async function initApp() {
    // Only run if not already processing (though on load it shouldn't be)
    // if (isProcessing) return; 

    // Visual feedback handled by "Connecting..." or similar if we wanted, 
    // but requirement says "Treat user as new... greet warmly".
    // We'll let the bubble appear naturally.

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

        // Speak it? Requirement implies "greet the user...". 
        // Auto-speaking on load might be blocked by browsers (autoplay policy), 
        // but we can try or just display text. 
        // Let's NOT auto-speak to avoid annoyance/blocking issues unless user interacts.
        // We will just text for now.

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

    addMessageToUI('user', text);
    sendMessageToAI(text);
    userInput.value = '';
    userInput.blur();
}

// --- Speech Recognition Flow ---

recognition.onstart = () => {
    isListening = true;
    micButton.classList.add('listening');
    statusText.textContent = "Listening... (Click Stop when finished)";
    statusText.style.color = "#f87171";
};

recognition.onend = () => {
    // Only restart if we're still supposed to be listening AND not processing
    // This prevents infinite loops if there are permission issues or hardware errors
    if (isListening && !isProcessing) {
        try {
            recognition.start();
        } catch (e) {
            console.warn("Could not auto-restart recognition:", e);
            isListening = false;
            micButton.classList.remove('listening');
        }
    } else {
        micButton.classList.remove('listening');
    }
};

recognition.onresult = (event) => {
    // Accumulate results from continuous recognition
    for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
            transcriptBuffer += event.results[i][0].transcript + ' ';
        }
    }
    // Update status to show we're hearing them
    statusText.textContent = "Recording your thoughts...";
};

recognition.onerror = (event) => {
    console.error("Speech recognition error", event.error);
    statusText.textContent = "I didn't catch that. Try again?";
};

// --- UI Interaction Logic ---

function addMessageToUI(role, text) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', role === 'user' ? 'user-message' : 'ai-message');

    const bubble = document.createElement('div');
    bubble.classList.add('bubble');
    bubble.innerHTML = formatMessage(text);

    messageDiv.appendChild(bubble);
    chatHistory.appendChild(messageDiv);

    // Smooth scroll to bottom
    // We trust the CSS padding to keep the content visible above the fixed inputs
    setTimeout(() => {
        chatHistory.scrollTo({
            top: chatHistory.scrollHeight,
            behavior: 'smooth'
        });
    }, 100);
}

async function sendMessageToAI(message) {
    if (isProcessing) return; // double-check guard

    isProcessing = true;
    setInputState(false); // Disable inputs

    statusText.textContent = "Reflecting...";
    statusText.style.color = "var(--accent-primary)";
    showTypingIndicator();

    // Setup Timeout (30s)
    abortController = new AbortController();
    const timeoutId = setTimeout(() => abortController.abort(), 30000);

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                message: message
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

        const data = await response.json();
        removeTypingIndicator();

        // Save new ID if provided by backend (first time generation)
        if (data.new_session_id) {
            sessionId = data.new_session_id;
            localStorage.setItem('memodiary_user_id', sessionId);
        }
        setTimeout(() => {
            addMessageToUI('ai', data.response);
            updateMood(data.mood);
            speakResponse(data.response);
            statusText.textContent = "I’m here to hear you—press the mic to speak";
            statusText.style.color = "var(--text-muted)";
        }, 800);

    } catch (error) {
        console.error("Interaction Error:", error);
        removeTypingIndicator();

        let errorMessage = `I'm having a quiet moment. (${error.message || 'ERR_UNKNOWN'}) 😌`;
        let statusMsg = "Connection Error";

        if (error.name === 'AbortError') {
            errorMessage = "I took a bit too long to think. Could you try that again? (ERR_TIMEOUT) ⏳";
            statusMsg = "Timed Out";
        } else if (error.message === "RATE_LIMIT") {
            errorMessage = "I'm a bit overwhelmed with thoughts right now. Let's take a breath. (ERR_429) 🤯";
            statusMsg = "Too Many Requests";
        } else if (error.message === "SERVICE_OVERLOAD") {
            errorMessage = "My thinking engine is briefly busy. I'll be ready in a moment. (ERR_503) 😵‍💫";
            statusMsg = "System Busy";
        }

        addMessageToUI('ai', errorMessage);
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

function updateMood(emoji) {
    if (emoji) {
        currentMood.textContent = emoji;
        currentMood.style.animation = 'none';
        currentMood.offsetHeight; // trigger reflow
        currentMood.style.animation = 'float 4s infinite ease-in-out';
    }
}

async function speakResponse(text) {
    if (!text) return;

    // Clean text for TTS
    const cleanText = text.replace(/[^\w\s\d,.!?]/gi, '').substring(0, 1000);

    try {
        // Stop any currently playing audio or speech
        window.speechSynthesis.cancel();
        if (window.currentAudio) {
            window.currentAudio.pause();
        }

        const response = await fetch('/api/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: cleanText,
                session_id: sessionId
            })
        });

        if (!response.ok) throw new Error("TTS_BACKEND_FAILED");

        const blob = await response.blob();
        const audioUrl = URL.createObjectURL(blob);
        const audio = new Audio(audioUrl);
        window.currentAudio = audio;

        await audio.play();
    } catch (error) {
        console.warn("Backend TTS failed, falling back to browser synthesis");

        // Fallback to browser synthesis
        const utterance = new SpeechSynthesisUtterance(cleanText);
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
}

function formatMessage(text) {
    if (!text) return '';

    // Minimal sanitation while allowing some formatting
    let formatted = text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");

    // Bold
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Italic
    formatted = formatted.replace(/\*(.*?)\*/g, '<em>$1</em>');
    // Newlines
    formatted = formatted.replace(/\n/g, '<br>');

    return formatted;
}

// --- Smooth Scroll-Based Header Behavior for About Page ---
// --- Smooth Scroll-Based Header Behavior for About Page ---
// Only activate if we are on a scrollable page (like About)
if (document.querySelector('body.scrollable')) {
    let lastScrollY = window.scrollY;
    let ticking = false;
    const header = document.querySelector('.main-header');

    function updateHeader() {
        const currentScrollY = window.scrollY;

        // Threshold of 50px to avoid jitter at top
        if (currentScrollY <= 50) {
            header.classList.remove('header-hidden');
            lastScrollY = currentScrollY;
            ticking = false;
            return;
        }

        // Sensitivity threshold
        if (Math.abs(currentScrollY - lastScrollY) < 10) {
            ticking = false;
            return;
        }

        if (currentScrollY > lastScrollY) {
            // Scrolling DOWN (Reading deeper) -> Hide Header for immersion
            header.classList.add('header-hidden');
        } else {
            // Scrolling UP (Going back) -> Show Header
            header.classList.remove('header-hidden');
        }

        lastScrollY = currentScrollY;
        ticking = false;
    }

    window.addEventListener('scroll', () => {
        if (!ticking) {
            window.requestAnimationFrame(updateHeader);
            ticking = true;
        }
    });
}

// --- Mobile-Only Header Scroll Behavior for Index Page ---
if (chatHistory && !document.querySelector('body.scrollable')) {
    let lastChatScrollTop = 0;
    let chatTicking = false;
    const indexHeader = document.querySelector('.main-header');

    function updateIndexHeader() {
        // Only active on mobile/tablet (<= 768px matches CSS media query)
        if (window.innerWidth > 768) {
            indexHeader.classList.remove('header-hidden');
            chatTicking = false;
            return;
        }

        const currentChatScrollTop = chatHistory.scrollTop;

        // Threshold to avoid jitter at very top
        if (currentChatScrollTop <= 50) {
            indexHeader.classList.remove('header-hidden');
            lastChatScrollTop = currentChatScrollTop;
            chatTicking = false;
            return;
        }

        // Sensitivity threshold
        if (Math.abs(currentChatScrollTop - lastChatScrollTop) < 10) {
            chatTicking = false;
            return;
        }

        if (currentChatScrollTop > lastChatScrollTop) {
            // Scrolling DOWN (Swiping Up) -> Hide Header
            indexHeader.classList.add('header-hidden');
        } else {
            // Scrolling UP (Swiping Down) -> Show Header
            indexHeader.classList.remove('header-hidden');
        }

        lastChatScrollTop = currentChatScrollTop;
        chatTicking = false;
    }

    chatHistory.addEventListener('scroll', () => {
        if (!chatTicking) {
            window.requestAnimationFrame(updateIndexHeader);
            chatTicking = true;
        }
    });
}
