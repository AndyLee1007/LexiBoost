// LexiBoost JavaScript Application

let currentUser = null;
let currentUserId = null;
let currentSession = null;
let currentQuestion = null;
let questionNumber = 0;
let sessionScore = 0;
let selectedAnswer = null;
// Timer related variables
let timerInterval = null;
let remainingTime = 0;
let sessionStartTime = null;
let isTimerEnabled = false;
// Default configuration - should match backend defaults
const DEFAULT_CONFIG = {
    max_questions_per_session: 50,  // Must match LEXIBOOST_MAX_QUESTIONS default in app.py
    hover_zh_enabled: false,        // Must match LEXIBOOST_HOVER_ZH default in app.py
    timer_enabled: false,           // Must match LEXIBOOST_ENABLE_TIMER default in app.py
    time_per_question: 600,         // Must match LEXIBOOST_TIME_PER_QUESTION default in app.py (10 minutes)
    total_session_time: 30000       // Default: 50 questions * 600 seconds = 30000 seconds
};

let appConfig = { ...DEFAULT_CONFIG };

// Load configuration from backend and update appConfig
async function loadAppConfig() {
    try {
        const response = await fetch('/api/config');
        if (response.ok) {
            const config = await response.json();
            appConfig = {
                max_questions_per_session: config.max_questions_per_session ?? DEFAULT_CONFIG.max_questions_per_session,
                hover_zh_enabled: config.hover_zh_enabled ?? DEFAULT_CONFIG.hover_zh_enabled,
                timer_enabled: config.timer_enabled ?? DEFAULT_CONFIG.timer_enabled,
                time_per_question: config.time_per_question ?? DEFAULT_CONFIG.time_per_question,
                total_session_time: config.total_session_time ?? DEFAULT_CONFIG.total_session_time
            };
            isTimerEnabled = appConfig.timer_enabled;
        }
    } catch (e) {
        // If fetch fails, keep defaults
        console.warn('Failed to load app config from backend, using defaults.', e);
    }
}

// Initialize application
async function initApp() {
    await loadAppConfig();
    setupDOMHandlers();
}

// Test timer function for debugging
function testTimer() {
    // Show quiz screen first
    showScreen('quiz-screen');
    
    // Force start timer
    if (appConfig.timer_enabled) {
        isTimerEnabled = true;
        startTimer();
    }
}

// Start initialization when DOM is ready
document.addEventListener('DOMContentLoaded', initApp);
// Utility functions
function escapeRegExp(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

let tooltipEl = null;

function showTooltip(target, text) {
    // remove existing tooltip
    hideTooltip();

    tooltipEl = document.createElement('div');
    tooltipEl.className = 'tooltip';
    tooltipEl.textContent = text;

    document.body.appendChild(tooltipEl);

    // location below the target
    const rect = target.getBoundingClientRect();
    tooltipEl.style.left = rect.left + window.scrollX + 'px';
    tooltipEl.style.top = rect.bottom + window.scrollY + 'px';
}

function hideTooltip() {
    if (tooltipEl) {
        tooltipEl.remove();
        tooltipEl = null;
    }
}

function showScreen(screenId) {
    document.querySelectorAll('.screen').forEach(screen => {
        screen.classList.add('hidden');
    });
    document.getElementById(screenId).classList.remove('hidden');
}

function showError(message) {
    alert(message); // Simple error handling for now
}

function showMessage(message) {
    alert(message); // Simple success message for now
}

function updateProgressBar(current, total) {
    const percentage = (current / total) * 100;
    document.getElementById('progress-fill').style.width = percentage + '%';
    // Update total questions display
    document.getElementById('total-questions').textContent = total;
}

function showQuestionLoading(isLoading) {
    const loadingContainer = document.getElementById('question-loading');
    const questionContent = document.getElementById('question-content');
    
    if (isLoading) {
        loadingContainer.classList.remove('hidden');
        questionContent.classList.add('hidden');
    } else {
        loadingContainer.classList.add('hidden');
        questionContent.classList.remove('hidden');
    }
}

// Timer functions
function formatTime(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hours > 0) {
        return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    } else {
        return `${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
}

function updateTimerDisplay() {
    if (!isTimerEnabled) return;
    
    const timerDisplay = document.getElementById('timer-display');
    const timerContainer = document.getElementById('timer-container');
    
    if (!timerDisplay || !timerContainer) return;
    
    timerDisplay.textContent = formatTime(remainingTime);
    
    // Update timer color based on remaining time
    timerDisplay.className = 'timer-value';
    
    // Calculate percentage of total time remaining
    const totalTime = appConfig.total_session_time || 3600; // fallback to 1 hour
    const percentageRemaining = (remainingTime / totalTime) * 100;
    
    if (percentageRemaining > 20) { // > 20% of total time remaining
        timerDisplay.classList.add('timer-normal');
    } else if (percentageRemaining > 5) { // 5-20% of total time remaining
        timerDisplay.classList.add('timer-warning');
    } else { // < 5% of total time remaining
        timerDisplay.classList.add('timer-danger');
    }
}

function startTimer() {
    if (!isTimerEnabled) return;
    
    const timerContainer = document.getElementById('timer-container');
    if (timerContainer) {
        timerContainer.classList.remove('hidden');
    }
    
    // Use actual session time instead of total configured time
    const sessionTime = (currentSession && currentSession.actual_session_time) ? currentSession.actual_session_time : appConfig.total_session_time;
    remainingTime = sessionTime;
    sessionStartTime = Date.now();
    
    console.log('Timer started with dynamic time:', {
        session_time: sessionTime,
        current_session: currentSession,
        configured_total: appConfig.total_session_time
    });
    
    // Clear any existing timer
    if (timerInterval) {
        clearInterval(timerInterval);
    }
    
    updateTimerDisplay();
    
    timerInterval = setInterval(() => {
        remainingTime--;
        updateTimerDisplay();
        
        if (remainingTime <= 0) {
            clearInterval(timerInterval);
            // Time expired - automatically complete session
            handleTimeExpired();
        }
    }, 1000);
}

function stopTimer() {
    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
}

function getActualTimeSpent() {
    if (!sessionStartTime) return 0;
    return Math.floor((Date.now() - sessionStartTime) / 1000);
}

async function handleTimeExpired() {
    stopTimer();
    
    // Record actual time spent
    const actualTimeSpent = getActualTimeSpent();
    
    try {
        // Complete the session with time expired status
        await apiRequest(`/api/sessions/${currentSession.id}/complete`, {
            method: 'POST',
            body: JSON.stringify({
                reason: 'time_expired',
                actual_time_spent: actualTimeSpent
            })
        });
        
        // Show completion screen with time expired message
        await showSessionComplete({
            session_complete: true,
            final_score: sessionScore,
            total_questions: questionNumber,
            time_expired: true
        });
    } catch (error) {
        console.error('Failed to complete session on time expiry:', error);
        showError('Session time expired. Please start a new session.');
        showScreen('dashboard-screen');
    }
}

// API functions
async function apiRequest(url, options = {}) {
    try {
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('API request failed:', error);
        throw error;
    }
}

// User management
async function loginUser() {
    const usernameInput = document.getElementById('username');
    let username = usernameInput.value.trim();
    
    // If no username provided, use a default one
    if (!username) {
        username = 'Guest';
        usernameInput.value = username;
    }

    try {
        // Try to get existing user first
        try {
            const userData = await apiRequest(`/api/users/${encodeURIComponent(username)}`);
            currentUser = userData;
            currentUserId = userData.id;
        } catch (error) {
            // User doesn't exist, create new one
            const userData = await apiRequest('/api/users', {
                method: 'POST',
                body: JSON.stringify({ username })
            });
            currentUser = userData;
            currentUserId = userData.id;
        }

        document.getElementById('user-name').textContent = currentUser.username;
        await loadAppConfig();
        await loadUserStats();
        showScreen('dashboard-screen');
        await loadUserDictionaries();
    } catch (error) {
        showError('Failed to login. Please try again.');
    }
}

// (Removed duplicate loadAppConfig function. The implementation at lines 15-29 is used.)

async function loadUserStats() {
    try {
        const stats = await apiRequest(`/api/users/${currentUser.user_id}/stats`);
        
        // Safely update stats elements if they exist
        const dailyScoreEl = document.getElementById('daily-score');
        if (dailyScoreEl) dailyScoreEl.textContent = stats.daily_score;
        
        const totalScoreEl = document.getElementById('total-score');
        if (totalScoreEl) totalScoreEl.textContent = stats.total_score;
        
        const wrongbookCountEl = document.getElementById('wrongbook-count');
        if (wrongbookCountEl) wrongbookCountEl.textContent = stats.wrongbook_count;
        
        console.log('User stats loaded:', stats);
    } catch (error) {
        console.error('Failed to load user stats:', error);
    }
}

// Quiz functionality
async function startQuizSession() {
    try {
        const sessionData = await apiRequest(`/api/users/${currentUser.user_id}/session/start`, {
            method: 'POST'
        });
        
        currentSession = sessionData;
        questionNumber = 0;
        sessionScore = 0;
        
        document.getElementById('current-score').textContent = sessionScore;
        const totalQuestions = (currentSession && currentSession.available_questions) ? currentSession.available_questions : appConfig.max_questions_per_session;
        updateProgressBar(0, totalQuestions);
        
        // Start timer if enabled
        if (isTimerEnabled) {
            startTimer();
        }
        
        showScreen('quiz-screen');
        await loadNextQuestion();
    } catch (error) {
        showError('Failed to start quiz session. Please try again.');
    }
}

async function loadNextQuestion() {
    try {
        // Show loading state
        showQuestionLoading(true);
        
        const q = await apiRequest(`/api/sessions/${currentSession.id}/question`);
        if (q.session_complete) {
            await showSessionComplete(q);
            return;
        }

        currentQuestion = q;
        questionNumber = q.question_number;
        selectedAnswer = null;

        // basic information
        document.getElementById('question-number').textContent = questionNumber;
        document.getElementById('target-word').textContent = q.target_word;
        
        // Prefer concise target_word_zh returned by the API (word-level Chinese mapping). Fall back to definition_zh or choice zh.
        const targetWordZh = q.target_word_zh || q.definition_zh || (currentQuestion.correct_answer_i18n && currentQuestion.correct_answer_i18n.zh) || q.target_word;
        document.getElementById('target-word-zh').textContent = targetWordZh;

        // sentence highlighting (to prevent special characters from breaking regex)
        const sentenceElement = document.getElementById('sentence-text');
        const tw = (q.target_word || '').trim();
        if (tw) {
            // Clear the element
            sentenceElement.textContent = '';
            // Split the sentence into parts, keeping the target word
            const re = new RegExp(`\\b${escapeRegExp(tw)}\\b`, 'gi');
            let lastIndex = 0;
            let match;
            const sentence = q.sentence || '';
            while ((match = re.exec(sentence)) !== null) {
                // Add text before the match
                if (match.index > lastIndex) {
                    sentenceElement.appendChild(document.createTextNode(sentence.slice(lastIndex, match.index)));
                }
                // Add the highlighted word
                const mark = document.createElement('mark');
                mark.textContent = match[0];
                sentenceElement.appendChild(mark);
                lastIndex = re.lastIndex;
            }
            // Add any remaining text after the last match
            if (lastIndex < sentence.length) {
                sentenceElement.appendChild(document.createTextNode(sentence.slice(lastIndex)));
            }
        } else {
            sentenceElement.textContent = q.sentence;
        }

        // options (using i18n)
        const choicesContainer = document.getElementById('answer-choices');
        choicesContainer.innerHTML = '';
        (q.choices_i18n || []).forEach((c, idx) => {
            const choiceElement = document.createElement('div');
            choiceElement.className = 'choice';
            choiceElement.dataset.en = c.en || '';
            choiceElement.dataset.zh = c.zh || '';

            // Create bilingual content
            const enDiv = document.createElement('div');
            enDiv.className = 'choice-en';
            enDiv.textContent = c.en || '';
            
            const zhDiv = document.createElement('div');
            zhDiv.className = 'choice-zh';
            zhDiv.textContent = c.zh || '';
            
            choiceElement.appendChild(enDiv);
            choiceElement.appendChild(zhDiv);

            // Restore hover functionality (only if enabled in config)
            if (appConfig && appConfig.hover_zh_enabled && c.zh) {
                choiceElement.addEventListener('mouseenter', () => showTooltip(choiceElement, c.zh));
                choiceElement.addEventListener('mouseleave', hideTooltip);
            }

            choiceElement.onclick = () => selectChoice(choiceElement, c.en || '');
            choicesContainer.appendChild(choiceElement);
        });

        // submit button - reset state and text
        const submitButton = document.getElementById('submit-answer');
        submitButton.disabled = true;
        submitButton.textContent = 'Submit Answer';

        // progress bar: completed is questionNumber - 1
        const totalQuestions = (currentSession && currentSession.available_questions) ? currentSession.available_questions : appConfig.max_questions_per_session;
        updateProgressBar(questionNumber - 1, totalQuestions);
        
        // Hide loading state and show question content
        showQuestionLoading(false);
    } catch (error) {
        console.error('Error in loadNextQuestion:', error);
        showQuestionLoading(false);
        showError('Failed to load question. Please try again. Error: ' + error.message);
    }
}

function selectChoice(choiceElement, answer) {
    // Remove previous selections
    document.querySelectorAll('.choice').forEach(choice => {
        choice.classList.remove('selected');
    });
    
    // Select current choice
    choiceElement.classList.add('selected');
    selectedAnswer = answer;
    
    // Enable submit button
    document.getElementById('submit-answer').disabled = false;
}

async function submitAnswer() {
    if (!selectedAnswer) return;

    const submitButton = document.getElementById('submit-answer');
    const originalButtonText = submitButton.textContent;
    
    try {
        // Disable button and show loading
        submitButton.disabled = true;
        submitButton.textContent = 'Submitting...';
        
        const answerData = await apiRequest(`/api/sessions/${currentSession.id}/answer`, {
            method: 'POST',
            body: JSON.stringify({
                word_id: currentQuestion.word_id,
                user_answer: selectedAnswer,
                correct_answer: currentQuestion.correct_answer_i18n.en,
                question_text: currentQuestion.question_text
            })
        });

        // Update score
        // sessionScore += answerData.score_change;
        // document.getElementById('current-score').textContent = sessionScore;
        is_correct = selectedAnswer == currentQuestion.correct_answer_i18n.en
        if (is_correct) {
            sessionScore += 1;
            document.getElementById('current-score').textContent = sessionScore;
        }

        // Show result
        showAnswerResult(answerData);

    } catch (error) {
        // Restore button state
        submitButton.disabled = false;
        submitButton.textContent = originalButtonText;
        showError('Failed to submit answer. Please try again.');
    }
}

function showAnswerResult(answerData) {
    const correctEn = (currentQuestion.correct_answer_i18n && currentQuestion.correct_answer_i18n.en) || '';

    // Show Chinese translations after answer submission
    document.getElementById('question-zh').style.display = 'block';
    document.querySelectorAll('.choice-zh').forEach(zhElement => {
        zhElement.style.display = 'block';
    });

    // Disable submit button and all choices
    document.getElementById('submit-answer').style.display = 'none';
    document.querySelectorAll('.choice').forEach(choice => {
        choice.style.pointerEvents = 'none';
        choice.style.cursor = 'default';
    });

    // Highlight choices and mark user selection
    document.querySelectorAll('.choice').forEach(choice => {
        const choiceEn = choice.dataset.en;
        
        // Mark correct answer
        if (choiceEn === correctEn) {
            choice.classList.add('correct');
        }
        
        // Mark user's selection
        if (choiceEn === selectedAnswer) {
            choice.classList.add('user-selected');
            if (!answerData.is_correct) {
                choice.classList.add('incorrect');
            }
        }
        
        // Remove the selected class as it's now replaced by result classes
        choice.classList.remove('selected');
    });

    // Hide explanation section since translations are already shown in choices
    const expEl = document.getElementById('explanation');
    expEl.style.display = 'none';

    // Handle next question behavior based on answer correctness
    const nextButton = document.getElementById('next-question-btn');
    const autoProgressMsg = document.getElementById('auto-progress-message');
    const resultDisplay = document.getElementById('result-display');
    
    // Show result display area
    resultDisplay.classList.remove('hidden');
    
    if (answerData.is_correct) {
        // For correct answers: show button immediately, no countdown
        nextButton.style.display = 'block';
        nextButton.disabled = false;
        if (autoProgressMsg) {
            autoProgressMsg.style.display = 'none';
        }
    } else {
        // For incorrect answers: show disabled button with 3s countdown before enabling
        nextButton.style.display = 'block';
        nextButton.disabled = true;
        
        if (autoProgressMsg) {
            autoProgressMsg.style.display = 'block';
            let countdown = 0;
            autoProgressMsg.textContent = `Next question available in ${countdown} seconds...`;
            
            const countdownInterval = setInterval(() => {
                countdown--;
                if (countdown > 0) {
                    autoProgressMsg.textContent = `Next question available in ${countdown} seconds...`;
                } else {
                    clearInterval(countdownInterval);
                    nextButton.disabled = false;
                    if (autoProgressMsg) {
                        autoProgressMsg.style.display = 'none';
                    }
                }
            }, 1000);
        } else {
            // Fallback if element doesn't exist
            setTimeout(() => {
                nextButton.disabled = false;
            }, 3000);
        }
    }

    // Stay on the same screen - no screen switching
}

async function nextQuestion() {
    // Reset the quiz screen state
    const resultDisplay = document.getElementById('result-display');
    const submitButton = document.getElementById('submit-answer');
    
    // Hide result display
    resultDisplay.classList.add('hidden');
    
    // Reset next button state
    const nextButton = document.getElementById('next-question-btn');
    const autoProgressMsg = document.getElementById('auto-progress-message');
    nextButton.disabled = false;
    if (autoProgressMsg) {
        autoProgressMsg.style.display = 'none';
    }
    
    // Hide Chinese translations for new question
    document.getElementById('question-zh').style.display = 'none';
    document.querySelectorAll('.choice-zh').forEach(zhElement => {
        zhElement.style.display = 'none';
    });
    
    // Show submit button
    submitButton.style.display = 'block';
    submitButton.disabled = true;
    
    // Reset all choices
    document.querySelectorAll('.choice').forEach(choice => {
        choice.classList.remove('correct', 'incorrect', 'user-selected', 'selected');
        choice.style.pointerEvents = 'auto';
        choice.style.cursor = 'pointer';
    });
    
    // Clear selected answer
    selectedAnswer = null;
    
    // Load next question
    await loadNextQuestion();
}

async function showSessionComplete(sessionData = {}) {
    console.log('showSessionComplete called with:', sessionData);
    console.log('currentSession:', currentSession);
    console.log('currentUserId:', currentUserId);
    console.log('questionNumber:', questionNumber);
    console.log('sessionScore:', sessionScore);
    
    // Stop timer when session completes
    stopTimer();
    
    // Calculate final stats
    const accuracy = questionNumber > 0 ? Math.round((sessionScore / questionNumber) * 100) : 0;
    
    // Update title and message based on completion reason
    const titleEl = document.getElementById('complete-title');
    const messageEl = document.getElementById('complete-message');
    const statsContainer = document.getElementById('final-stats-container');
    
    // Check if required elements exist
    if (!titleEl || !messageEl || !statsContainer) {
        console.error('Missing completion screen elements:', {
            titleEl: !!titleEl,
            messageEl: !!messageEl,
            statsContainer: !!statsContainer
        });
        return;
    }
    
    if (sessionData.reason === 'no_words_in_db') {
        titleEl.textContent = '📚 No Words Available';
        messageEl.textContent = sessionData.message || 'No words available in the database. Please import vocabulary data.';
        statsContainer.style.display = 'none';
    } else if (sessionData.reason === 'all_words_completed') {
        titleEl.textContent = '🎯 All Words Completed!';
        messageEl.textContent = sessionData.message || 'Congratulations! You have completed all available words in this session.';
        statsContainer.style.display = 'block';
    } else if (sessionData.reason === 'no_words_due') {
        titleEl.textContent = '✅ All Caught Up!';
        messageEl.textContent = sessionData.message || 'No more words due for review at this time. Great job!';
        statsContainer.style.display = 'block';
    } else if (sessionData.reason === 'time_expired' || sessionData.time_expired) {
        titleEl.textContent = '⏰ Time Expired!';
        messageEl.textContent = `Time limit reached! You completed ${questionNumber} questions before time ran out.`;
        statsContainer.style.display = 'block';
    } else {
        // Normal session completion (max questions reached)
        titleEl.textContent = '🎉 Session Complete!';
        messageEl.textContent = `Great job! You completed ${questionNumber} questions.`;
        statsContainer.style.display = 'block';
    }
    
    // Update stats if they should be shown
    if (statsContainer.style.display !== 'none') {
        document.getElementById('final-questions').textContent = questionNumber;
        document.getElementById('final-correct').textContent = sessionScore;
        document.getElementById('final-accuracy').textContent = accuracy + '%';
        
        // Load detailed session statistics
        if (currentSession) {
            try {
                await loadSessionDetailedStats(currentSession.id);
            } catch (error) {
                console.error('Failed to load session detailed stats:', error);
            }
        }
        
        // Load session trends for current user
        console.log('About to load session trends, currentUserId:', currentUserId);
        console.log('currentUser:', currentUser);
        console.log('currentSession:', currentSession);
        
        // Try to get user ID from multiple sources
        let userId = currentUserId || (currentUser && currentUser.id) || (currentUser && currentUser.user_id) || (currentSession && currentSession.user_id);
        console.log('Resolved userId:', userId);
        
        if (userId) {
            try {
                console.log('Calling loadSessionTrends with userId:', userId);
                await loadSessionTrends(userId, false);
                console.log('loadSessionTrends completed');
            } catch (error) {
                console.error('Failed to load session trends:', error);
            }
        } else {
            console.warn('No userId available for trends loading from any source');
        }
    }

    showScreen('complete-screen');
}

function returnToDashboard() {
    loadUserStats(); // Refresh stats
    showScreen('dashboard-screen');
    if (currentUser) {
        loadUserDictionaries(); // Refresh dictionaries
    }
}

// Show standalone trends screen
function showTrendsScreen() {
    showScreen('trends-screen');
    // Load trends data when screen is shown
    if (currentUser) {
        loadStandaloneTrends();
    }
}

// Import functionality
function showImportScreen() {
    showScreen('import-screen');
}

async function uploadCSV() {
    const fileInput = document.getElementById('csv-file');
    const file = fileInput.files[0];
    
    if (!file) {
        showError('Please select a CSV file');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(`/api/users/${currentUser.user_id}/wrongbook/import`, {
            method: 'POST',
            body: formData
        });

        const result = await response.json();
        
        if (response.ok) {
            alert(`${result.message}`);
            fileInput.value = ''; // Clear file input
        } else {
            showError(result.error);
        }
    } catch (error) {
        showError('Failed to upload CSV file');
    }
}

// Self-test functionality
async function runSelfTest() {
    showScreen('selftest-screen');
    
    try {
        const testResults = await apiRequest('/api/self-test');
        
        const resultsContainer = document.getElementById('test-results');
        resultsContainer.innerHTML = '';
        
        // Overall status
        const overallStatus = document.createElement('div');
        overallStatus.className = 'test-item';
        overallStatus.innerHTML = `
            <span>Overall Status</span>
            <span class="test-status ${testResults.overall_status.toLowerCase()}">${testResults.overall_status}</span>
        `;
        resultsContainer.appendChild(overallStatus);
        
        // Individual tests
        testResults.tests.forEach(test => {
            const testItem = document.createElement('div');
            testItem.className = 'test-item';
            testItem.innerHTML = `
                <span>${test.test}</span>
                <span class="test-status ${test.status.toLowerCase()}">${test.status}</span>
            `;
            if (test.error) {
                testItem.title = test.error;
            }
            resultsContainer.appendChild(testItem);
        });
        
    } catch (error) {
        showError('Failed to run self-test');
    }
}

// Dictionary Management Functions

async function loadUserDictionaries() {
    if (!currentUser) return;
    
    const loadingElement = document.getElementById('dictionaries-loading');
    const listElement = document.getElementById('dictionaries-list');
    
    if (!loadingElement || !listElement) {
        console.error('Dictionary DOM elements not found');
        return;
    }
    
    try {
        loadingElement.style.display = 'block';
        listElement.innerHTML = '';
        
        const response = await fetch(`/api/users/${currentUser.user_id}/dictionaries`);
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || `HTTP ${response.status}: Failed to load dictionaries`);
        }
        
        loadingElement.style.display = 'none';
        
        if (!data.dictionaries || data.dictionaries.length === 0) {
            listElement.innerHTML = '<p class="loading-text">No dictionaries found. Import your first dictionary to get started!</p>';
            return;
        }
        
        data.dictionaries.forEach(dict => {
            const dictCard = createDictionaryCard(dict);
            listElement.appendChild(dictCard);
        });
        
    } catch (error) {
        console.error('Error loading dictionaries:', error);
        if (loadingElement) loadingElement.style.display = 'none';
        if (listElement) {
            listElement.innerHTML = '<p class="loading-text" style="color: #d32f2f;">Failed to load dictionaries: ' + error.message + '</p>';
        }
    }
}

function createDictionaryCard(dictionary) {
    const card = document.createElement('div');
    card.className = 'dictionary-card';
    
    const progressWidth = dictionary.total_words > 0 ? 
        (dictionary.learned_words / dictionary.total_words * 100) : 0;
    const encounterWidth = dictionary.total_words > 0 ? 
        (dictionary.encountered_words / dictionary.total_words * 100) : 0;
    
    card.innerHTML = `
        <div class="dictionary-header">
            <h4 class="dictionary-name">${escapeHtml(dictionary.name)}</h4>
            <div class="dictionary-stats">
                <span>📚 ${dictionary.total_words} words</span>
                <span>👁️ ${dictionary.encountered_words} encountered</span>
                <span>✅ ${dictionary.learned_words} learned</span>
                <span>🎯 ${dictionary.accuracy_rate}% accuracy</span>
            </div>
        </div>
        ${dictionary.description ? `<p class="dictionary-description">${escapeHtml(dictionary.description)}</p>` : ''}
        <div class="dictionary-progress">
            <div class="progress-container">
                <div class="progress-label">Encountered: ${dictionary.encounter_rate}%</div>
                <div class="progress-bar">
                    <div class="progress-fill encounter" style="width: ${encounterWidth}%"></div>
                </div>
            </div>
            <div class="progress-container">
                <div class="progress-label">Learned: ${dictionary.completion_rate}%</div>
                <div class="progress-bar">
                    <div class="progress-fill learned" style="width: ${progressWidth}%"></div>
                </div>
            </div>
        </div>
        <div class="dictionary-actions">
            <button class="dictionary-btn primary" onclick="startQuizWithDictionary(${dictionary.id})">
                🚀 Start Quiz
            </button>
            ${dictionary.id !== 1 ? `
            <button class="dictionary-btn danger" onclick="deleteDictionary(${dictionary.id}, '${escapeHtml(dictionary.name)}')" title="Delete Dictionary">
                🗑️ Delete
            </button>
            ` : ''}
        </div>
    `;
    
    return card;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function startQuizWithDictionary(dictionaryId) {
    if (!currentUser) {
        showError('Please log in first');
        return;
    }
    
    try {
        const response = await fetch(`/api/users/${currentUser.user_id}/session/start`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ dictionary_id: dictionaryId })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Failed to start session');
        }
        
        currentSession = {
            id: data.session_id,
            session_id: data.session_id,  // Keep both for compatibility
            dictionary_id: data.dictionary_id,
            available_questions: data.available_questions || appConfig.max_questions_per_session,
            actual_session_time: data.actual_session_time || appConfig.total_session_time
        };
        
        // Debug logging
        console.log('Session started with:', {
            available_questions: currentSession.available_questions,
            actual_session_time: currentSession.actual_session_time,
            max_questions_config: appConfig.max_questions_per_session,
            total_session_time_config: appConfig.total_session_time
        });
        
        console.log('Session started with dynamic timing:', {
            available_questions: currentSession.available_questions,
            actual_session_time: currentSession.actual_session_time,
            total_configured_time: appConfig.total_session_time
        });
        
        // Initialize quiz state
        questionNumber = 0;
        sessionScore = 0;
        selectedAnswer = null;
        
        document.getElementById('current-score').textContent = sessionScore;
        updateProgressBar(0, currentSession.available_questions);
        
        // Start timer if enabled (using actual session time)
        if (isTimerEnabled) {
            startTimer();
        }
        
        showScreen('quiz-screen');
        await loadNextQuestion();
        
    } catch (error) {
        showError('Failed to start quiz: ' + error.message);
        console.error('Error starting quiz:', error);
    }
}

function showImportDictionaryScreen() {
    showScreen('import-dictionary-screen');
}

function showImportWrongbookScreen() {
    // Load dictionaries for selection
    loadDictionariesForWrongbook();
    showScreen('import-wrongbook-screen');
}

async function loadDictionariesForWrongbook() {
    if (!currentUser) return;
    
    const selectElement = document.getElementById('wrongbook-dictionary-select');
    
    try {
        selectElement.innerHTML = '<option value="">Loading dictionaries...</option>';
        
        const response = await fetch(`/api/users/${currentUser.user_id}/dictionaries`);
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Failed to load dictionaries');
        }
        
        selectElement.innerHTML = '<option value="">Select a dictionary...</option>';
        
        data.dictionaries.forEach(dict => {
            const option = document.createElement('option');
            option.value = dict.id;
            option.textContent = dict.name;
            selectElement.appendChild(option);
        });
        
    } catch (error) {
        selectElement.innerHTML = '<option value="">Failed to load dictionaries</option>';
        console.error('Error loading dictionaries for wrongbook:', error);
    }
}

async function uploadDictionaryCSV() {
    const nameInput = document.getElementById('dictionary-name');
    const descriptionInput = document.getElementById('dictionary-description');
    const fileInput = document.getElementById('dictionary-csv-file');
    
    const name = nameInput.value.trim();
    const description = descriptionInput.value.trim();
    const file = fileInput.files[0];
    
    if (!name) {
        showError('Please enter a dictionary name');
        return;
    }
    
    if (!file) {
        showError('Please select a CSV file');
        return;
    }
    
    if (!currentUser) {
        showError('Please log in first');
        return;
    }
    
    try {
        // First create the dictionary
        const createResponse = await fetch('/api/dictionaries', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: name,
                description: description,
                created_by: currentUser.user_id
            })
        });
        
        const createData = await createResponse.json();
        
        if (!createResponse.ok) {
            throw new Error(createData.error || 'Failed to create dictionary');
        }
        
        // Then import the CSV
        const formData = new FormData();
        formData.append('file', file);
        
        const importResponse = await fetch(`/api/dictionaries/${createData.id}/import`, {
            method: 'POST',
            body: formData
        });
        
        const importData = await importResponse.json();
        
        if (!importResponse.ok) {
            throw new Error(importData.error || 'Failed to import CSV');
        }
        
        showMessage(`Dictionary imported successfully! ${importData.message}`);
        
        // Clear form
        nameInput.value = '';
        descriptionInput.value = '';
        fileInput.value = '';
        
        // Return to dashboard and reload dictionaries
        returnToDashboard();
        
    } catch (error) {
        showError('Failed to import dictionary: ' + error.message);
        console.error('Error importing dictionary:', error);
    }
}

async function uploadWrongbookCSV() {
    const dictionarySelect = document.getElementById('wrongbook-dictionary-select');
    const fileInput = document.getElementById('wrongbook-csv-file');
    
    const dictionaryId = dictionarySelect.value;
    const file = fileInput.files[0];
    
    if (!dictionaryId) {
        showError('Please select a dictionary');
        return;
    }
    
    if (!file) {
        showError('Please select a CSV file');
        return;
    }
    
    if (!currentUser) {
        showError('Please log in first');
        return;
    }
    
    try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('dictionary_id', dictionaryId);
        
        const response = await fetch(`/api/users/${currentUser.user_id}/wrongbook/import-to-dictionary`, {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Failed to import wrongbook');
        }
        
        showMessage(`Wrongbook imported successfully! ${data.message}`);
        
        // Clear form
        dictionarySelect.value = '';
        fileInput.value = '';
        
        // Return to dashboard and reload dictionaries
        returnToDashboard();
        
    } catch (error) {
        showError('Failed to import wrongbook: ' + error.message);
        console.error('Error importing wrongbook:', error);
    }
}

// Update existing functions to support dictionaries
// We'll modify the original loginUser to load dictionaries after login
// This is handled by updating the showDashboard function instead

// Additional DOM initialization
function setupDOMHandlers() {
    // Add enter key support for login
    document.getElementById('username').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            loginUser();
        }
    });
    
    // Show login screen initially
    showScreen('login-screen');
}

// Dictionary management functions
async function deleteDictionary(dictionaryId, dictionaryName) {
    if (!confirm(`Are you sure you want to delete the dictionary "${dictionaryName}"?\n\nThis will permanently delete all words in this dictionary and cannot be undone.`)) {
        return;
    }
    
    try {
        const response = await apiRequest(`/api/dictionaries/${dictionaryId}`, {
            method: 'DELETE'
        });
        
        showMessage(`Dictionary "${dictionaryName}" deleted successfully!`);
        
        // Reload dictionaries list
        await loadUserDictionaries();
        
    } catch (error) {
        console.error('Failed to delete dictionary:', error);
        showError(`Failed to delete dictionary: ${error.message}`);
    }
}

// Load session detailed statistics
async function loadSessionDetailedStats(sessionId) {
    try {
        const response = await fetch(`/api/sessions/${sessionId}/stats`);
        const data = await response.json();
        
        if (data.status === 'success') {
            const stats = data.stats;
            
            // Update UI with detailed stats
            const newWordsElement = document.getElementById('final-new-words');
            if (newWordsElement) {
                if (stats.is_all_review) {
                    // When all words are review words, show wrong words count
                    newWordsElement.textContent = stats.wrong_words_count || 0;
                    // Update the parent stat div label
                    const statDiv = newWordsElement.parentElement;
                    if (statDiv && statDiv.textContent.includes('New Words:')) {
                        statDiv.innerHTML = statDiv.innerHTML.replace('New Words:', 'Need Practice:');
                    }
                } else {
                    newWordsElement.textContent = stats.new_words_count;
                }
            }
            
            const reviewWordsElement = document.getElementById('final-review-words');
            if (reviewWordsElement) {
                reviewWordsElement.textContent = stats.review_words_count;
            }
            
            // Note: hover state display removed as it's not in the UI design
            
            console.log('Session stats loaded:', stats);
        } else {
            console.error('Failed to load session stats:', data.message);
        }
    } catch (error) {
        console.error('Error loading session stats:', error);
    }
}

// Load and display user session trends
async function loadSessionTrends(userId) {
    console.log('=== TRENDS DEBUG START ===');
    console.log('loadSessionTrends called with userId:', userId);
    try {
        // Always include hover data and let legend control visibility, limit to recent 15 sessions
        const url = `/api/users/${userId}/sessions/trends?include_hover=true&limit=15`;
        console.log('Fetching trends from URL:', url);
        console.log('About to call fetch...');
        const response = await fetch(url);
        console.log('Fetch response received, status:', response.status, 'ok:', response.ok);
        
        const data = await response.json();
        console.log('Trends API response data:', JSON.stringify(data, null, 2));
        
        // Always show trends section
        const trendsSection = document.getElementById('trends-section');
        if (trendsSection) {
            trendsSection.style.display = 'block';
        }
        
        if (data.status === 'success' && data.trends && data.trends.length > 0) {
            console.log('SUCCESS: Rendering trend chart with', data.trends.length, 'data points');
            console.log('Trends data:', data.trends);
            renderTrendChart(data.trends);
            
            // Update summary stats
            if (data.summary) {
                updateTrendsSummary(data.summary);
                console.log('Trends summary updated:', data.summary);
                console.log('Include hover enabled:', data.summary.include_hover);
                console.log('Total sessions in filter:', data.summary.total_sessions);
            }
            
            // Show chart, hide no-data message
            showElement('trends-chart-container');
            hideElement('trends-no-data');
        } else {
            console.log('NO DATA: Insufficient data for trends or error');
            console.log('data.status:', data.status);
            console.log('data.trends:', data.trends);
            console.log('data.trends length:', data.trends ? data.trends.length : 'undefined');
            console.log('data.message:', data.message);
            
            // Hide chart, show no-data message
            hideElement('trends-chart-container');
            showElement('trends-no-data');
        }
    } catch (error) {
        console.error('FETCH ERROR: Error loading session trends:', error);
        console.error('Error details:', error.message, error.stack);
        
        // Always show trends section, but show error state
        const trendsSection = document.getElementById('trends-section');
        if (trendsSection) {
            trendsSection.style.display = 'block';
        }
        
        // Hide chart, show no-data message
        hideElement('trends-chart-container');
        showElement('trends-no-data');
    }
}

// Render trend chart using Chart.js
function renderTrendChart(trendsData) {
    console.log('renderTrendChart called with data:', trendsData);
    const canvas = document.getElementById('trends-chart');
    console.log('Canvas element found:', !!canvas);
    if (!canvas) {
        console.error('Canvas element "trends-chart" not found');
        return;
    }
    
    const ctx = canvas.getContext('2d');
    console.log('Canvas context obtained:', !!ctx);
    
    // Destroy existing chart if it exists
    if (window.trendsChart instanceof Chart) {
        window.trendsChart.destroy();
    }
    
    // 按时间顺序，labels和数据点一一对应，hover和normal模式用null填充
    const labels = [];
    const nonHoverData = [];
    const hoverData = [];
    trendsData.forEach(point => {
        const date = new Date(point.date);
        labels.push(date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }));
        const accuracy = parseFloat(point.accuracy_rate);
        if (point.hover_enabled) {
            hoverData.push(accuracy);
            nonHoverData.push(null);
        } else {
            nonHoverData.push(accuracy);
            hoverData.push(null);
        }
    });
    
    // Create new chart
    console.log('Creating Chart.js with hover data:', hoverData.length, 'non-hover data:', nonHoverData.length);
    try {
        window.trendsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                label: 'Accuracy (Normal Mode)',
                data: nonHoverData,
                borderColor: '#4a90e2',
                backgroundColor: 'rgba(74, 144, 226, 0.1)',
                borderWidth: 2,
                pointBackgroundColor: '#4a90e2',
                pointBorderColor: '#ffffff',
                pointBorderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 6,
                tension: 0.3,
                spanGaps: true // Connect points across null gaps
                },
                {
                label: 'Accuracy (Hover Mode)',
                data: hoverData,
                borderColor: '#ff6b6b',
                backgroundColor: 'rgba(255, 107, 107, 0.1)',
                borderWidth: 2,
                pointBackgroundColor: '#ff6b6b',
                pointBorderColor: '#ffffff',
                pointBorderWidth: 2,
                pointRadius: 5,
                pointHoverRadius: 7,
                tension: 0.3,
                spanGaps: true // Connect points across null gaps
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        boxWidth: 12,
                        padding: 15,
                        font: {
                            size: 12
                        }
                    },
                    onClick: function(e, legendItem, legend) {
                        const index = legendItem.datasetIndex;
                        const chart = legend.chart;
                        
                        if (chart.isDatasetVisible(index)) {
                            chart.hide(index);
                            legendItem.hidden = true;
                        } else {
                            chart.show(index);
                            legendItem.hidden = false;
                        }
                        chart.update();
                    }
                },
                title: {
                    display: true,
                    text: 'Accuracy Trends',
                    font: {
                        size: 16,
                        weight: 'bold'
                    },
                    color: '#333'
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    ticks: {
                        callback: function(value) {
                            return value + '%';
                        }
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.1)'
                    }
                },
                x: {
                    grid: {
                        color: 'rgba(0, 0, 0, 0.1)'
                    }
                }
            },
            elements: {
                point: {
                    hoverBackgroundColor: '#ff6b6b'
                }
            },
            interaction: {
                intersect: false,
                mode: 'index'
            }
        }
    });
        console.log('Chart created successfully:', window.trendsChart);
    } catch (error) {
        console.error('Error creating Chart.js:', error);
        console.error('Chart constructor available:', typeof Chart);
        console.error('Canvas context:', ctx);
    }
}



// Helper functions for element visibility
function showElement(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.classList.remove('hidden');
    }
}

function hideElement(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.classList.add('hidden');
    }
}

// Update trends summary statistics
function updateTrendsSummary(summary) {
    const avgAccuracyEl = document.getElementById('avg-accuracy');
    const totalSessionsEl = document.getElementById('total-sessions');
    
    if (avgAccuracyEl) {
        avgAccuracyEl.textContent = `${summary.avg_accuracy || 0}%`;
    }
    
    if (totalSessionsEl) {
        totalSessionsEl.textContent = summary.total_sessions || 0;
    }
}

// Load standalone trends screen
async function loadStandaloneTrends() {
    if (!currentUser) return;
    
    const userId = currentUser.user_id;
    console.log('Loading standalone trends for user:', userId);
    
    try {
        // Show loading state
        const loadingEl = document.getElementById('standalone-trends-loading');
        const noDataEl = document.getElementById('standalone-trends-no-data');
        const containerEl = document.getElementById('standalone-trends-chart-container');
        
        if (loadingEl) loadingEl.classList.remove('hidden');
        if (noDataEl) noDataEl.classList.add('hidden');
        if (containerEl) containerEl.style.display = 'none';
        
        // Fetch trends data
        const url = `/api/users/${userId}/sessions/trends?include_hover=true&limit=15`;
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.status === 'success' && data.trends && data.trends.length > 0) {
            console.log('Rendering standalone trend chart with', data.trends.length, 'data points');
            renderStandaloneTrendChart(data.trends);
            
            // Update summary stats
            if (data.summary) {
                updateStandaloneTrendsSummary(data.summary);
            }
            
            // Show chart, hide loading/no-data
            if (containerEl) containerEl.style.display = 'block';
            if (loadingEl) loadingEl.classList.add('hidden');
            if (noDataEl) noDataEl.classList.add('hidden');
        } else {
            console.log('No data available for standalone trends');
            // Hide chart, show no-data message
            if (containerEl) containerEl.style.display = 'none';
            if (loadingEl) loadingEl.classList.add('hidden');
            if (noDataEl) noDataEl.classList.remove('hidden');
        }
    } catch (error) {
        console.error('Error loading standalone trends:', error);
        // Show error state
        const loadingEl = document.getElementById('standalone-trends-loading');
        const noDataEl = document.getElementById('standalone-trends-no-data');
        const containerEl = document.getElementById('standalone-trends-chart-container');
        
        if (containerEl) containerEl.style.display = 'none';
        if (loadingEl) loadingEl.classList.add('hidden');
        if (noDataEl) noDataEl.classList.remove('hidden');
    }
}

// Render standalone trend chart
function renderStandaloneTrendChart(trendsData) {
    console.log('renderStandaloneTrendChart called with data:', trendsData);
    const canvas = document.getElementById('standalone-trends-chart');
    
    if (!canvas) {
        console.error('Canvas element "standalone-trends-chart" not found');
        return;
    }
    
    const ctx = canvas.getContext('2d');
    
    // Destroy existing chart if it exists
    if (window.standaloneTrendsChart instanceof Chart) {
        window.standaloneTrendsChart.destroy();
    }
    
    // Process data same way as main trends chart
    const labels = [];
    const nonHoverData = [];
    const hoverData = [];
    trendsData.forEach(point => {
        const date = new Date(point.date);
        labels.push(date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }));
        const accuracy = parseFloat(point.accuracy_rate);
        if (point.hover_enabled) {
            hoverData.push(accuracy);
            nonHoverData.push(null);
        } else {
            nonHoverData.push(accuracy);
            hoverData.push(null);
        }
    });
    
    // Create chart with same configuration as main chart
    try {
        window.standaloneTrendsChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Accuracy (Normal Mode)',
                        data: nonHoverData,
                        borderColor: '#4a90e2',
                        backgroundColor: 'rgba(74, 144, 226, 0.1)',
                        borderWidth: 2,
                        pointBackgroundColor: '#4a90e2',
                        pointBorderColor: '#ffffff',
                        pointBorderWidth: 2,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        tension: 0.3,
                        spanGaps: true
                    },
                    {
                        label: 'Accuracy (Hover Mode)',
                        data: hoverData,
                        borderColor: '#ff6b6b',
                        backgroundColor: 'rgba(255, 107, 107, 0.1)',
                        borderWidth: 2,
                        pointBackgroundColor: '#ff6b6b',
                        pointBorderColor: '#ffffff',
                        pointBorderWidth: 2,
                        pointRadius: 5,
                        pointHoverRadius: 7,
                        tension: 0.3,
                        spanGaps: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            boxWidth: 12,
                            padding: 15,
                            font: {
                                size: 12
                            }
                        },
                        onClick: function(e, legendItem, legend) {
                            const index = legendItem.datasetIndex;
                            const chart = legend.chart;
                            
                            if (chart.isDatasetVisible(index)) {
                                chart.hide(index);
                                legendItem.hidden = true;
                            } else {
                                chart.show(index);
                                legendItem.hidden = false;
                            }
                            chart.update();
                        }
                    },
                    title: {
                        display: true,
                        text: 'Accuracy Trends',
                        font: {
                            size: 16,
                            weight: 'bold'
                        },
                        color: '#333'
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            callback: function(value) {
                                return value + '%';
                            }
                        },
                        grid: {
                            color: 'rgba(0, 0, 0, 0.1)'
                        }
                    },
                    x: {
                        grid: {
                            color: 'rgba(0, 0, 0, 0.1)'
                        }
                    }
                },
                elements: {
                    point: {
                        hoverBackgroundColor: '#ff6b6b'
                    }
                },
                interaction: {
                    intersect: false,
                    mode: 'index'
                }
            }
        });
        console.log('Standalone chart created successfully');
    } catch (error) {
        console.error('Error creating standalone Chart.js:', error);
    }
}

// Update standalone trends summary statistics
function updateStandaloneTrendsSummary(summary) {
    const avgAccuracyEl = document.getElementById('standalone-avg-accuracy');
    const totalSessionsEl = document.getElementById('standalone-total-sessions');
    
    if (avgAccuracyEl) {
        avgAccuracyEl.textContent = `${summary.avg_accuracy || 0}%`;
    }
    
    if (totalSessionsEl) {
        totalSessionsEl.textContent = summary.total_sessions || 0;
    }
}

// onHoverToggleChange function removed - now using legend click events