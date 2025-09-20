// LexiBoost JavaScript Application

let currentUser = null;
let currentSession = null;
let currentQuestion = null;
let questionNumber = 0;
let sessionScore = 0;
let selectedAnswer = null;
let appConfig = {
    max_questions_per_session: 50,
    hover_zh_enabled: false
};

// Load configuration from backend and update appConfig
async function loadAppConfig() {
    try {
        const response = await fetch('/api/config');
        if (response.ok) {
            const config = await response.json();
            appConfig = {
                max_questions_per_session: config.max_questions_per_session !== undefined ? config.max_questions_per_session : appConfig.max_questions_per_session,
                hover_zh_enabled: config.hover_zh_enabled !== undefined ? config.hover_zh_enabled : appConfig.hover_zh_enabled
            };
        }
    } catch (e) {
        // If fetch fails, keep defaults
        console.warn('Failed to load app config from backend, using defaults.', e);
    }
}

// Immediately load config on app initialization
loadAppConfig();
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
    const username = document.getElementById('username').value.trim();
    if (!username) {
        showError('Please enter your name');
        return;
    }

    try {
        // Try to get existing user first
        try {
            const userData = await apiRequest(`/api/users/${encodeURIComponent(username)}`);
            currentUser = userData;
        } catch (error) {
            // User doesn't exist, create new one
            const userData = await apiRequest('/api/users', {
                method: 'POST',
                body: JSON.stringify({ username })
            });
            currentUser = userData;
        }

        document.getElementById('user-name').textContent = currentUser.username;
        await loadAppConfig();
        await loadUserStats();
        showScreen('dashboard-screen');
    } catch (error) {
        showError('Failed to login. Please try again.');
    }
}

async function loadAppConfig() {
    try {
        const config = await apiRequest('/api/config');
        appConfig = config;
    } catch (error) {
        console.error('Failed to load app config:', error);
        // Use defaults if config fails to load
    }
}

async function loadUserStats() {
    try {
        const stats = await apiRequest(`/api/users/${currentUser.user_id}/stats`);
        document.getElementById('daily-score').textContent = stats.daily_score;
        document.getElementById('total-score').textContent = stats.total_score;
        document.getElementById('wrongbook-count').textContent = stats.wrongbook_count;
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
        updateProgressBar(0, appConfig.max_questions_per_session);
        
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
        
        const q = await apiRequest(`/api/sessions/${currentSession.session_id}/question`);
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
        updateProgressBar(questionNumber - 1, appConfig.max_questions_per_session);
        
        // Hide loading state and show question content
        showQuestionLoading(false);
    } catch (error) {
        showQuestionLoading(false);
        showError('Failed to load question. Please try again.');
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
        
        const answerData = await apiRequest(`/api/sessions/${currentSession.session_id}/answer`, {
            method: 'POST',
            body: JSON.stringify({
                word_id: currentQuestion.word_id,
                user_answer: selectedAnswer,
                correct_answer: currentQuestion.correct_answer_i18n.en,
                question_text: currentQuestion.question_text
            })
        });

        // Update score
        sessionScore += answerData.score_change;
        document.getElementById('current-score').textContent = sessionScore;

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
        // For correct answers: hide button and auto-advance after 3 seconds
        nextButton.style.display = 'none';
        if (autoProgressMsg) {
            autoProgressMsg.style.display = 'block';
            let countdown = 3;
            autoProgressMsg.textContent = `Next question in ${countdown} seconds...`;
            
            const countdownInterval = setInterval(() => {
                countdown--;
                if (countdown > 0) {
                    autoProgressMsg.textContent = `Next question in ${countdown} seconds...`;
                } else {
                    clearInterval(countdownInterval);
                    nextQuestion();
                }
            }, 1000);
        } else {
            // Fallback if element doesn't exist
            setTimeout(() => {
                nextQuestion();
            }, 3000);
        }
    } else {
        // For incorrect answers: show button and require manual click
        nextButton.style.display = 'block';
        if (autoProgressMsg) {
            autoProgressMsg.style.display = 'none';
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
    // Calculate final stats
    const accuracy = questionNumber > 0 ? Math.round((sessionScore / questionNumber) * 100) : 0;
    
    // Update title and message based on completion reason
    const titleEl = document.getElementById('complete-title');
    const messageEl = document.getElementById('complete-message');
    const statsContainer = document.getElementById('final-stats-container');
    
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
        document.getElementById('final-score').textContent = sessionScore;
        document.getElementById('final-accuracy').textContent = accuracy + '%';
    }

    showScreen('complete-screen');
}

function returnToDashboard() {
    loadUserStats(); // Refresh stats
    showScreen('dashboard-screen');
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

// Initialize application
document.addEventListener('DOMContentLoaded', function() {
    // Add enter key support for login
    document.getElementById('username').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            loginUser();
        }
    });
    
    // Show login screen initially
    showScreen('login-screen');
});