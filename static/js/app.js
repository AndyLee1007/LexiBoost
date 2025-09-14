// LexiBoost JavaScript Application

let currentUser = null;
let currentSession = null;
let currentQuestion = null;
let questionNumber = 0;
let sessionScore = 0;
let selectedAnswer = null;

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
        await loadUserStats();
        showScreen('dashboard-screen');
    } catch (error) {
        showError('Failed to login. Please try again.');
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
        updateProgressBar(0, 50);
        
        showScreen('quiz-screen');
        await loadNextQuestion();
    } catch (error) {
        showError('Failed to start quiz session. Please try again.');
    }
}

async function loadNextQuestion() {
    try {
        const q = await apiRequest(`/api/sessions/${currentSession.session_id}/question`);
        if (q.session_complete) {
            await showSessionComplete();
            return;
        }

        currentQuestion = q;
        questionNumber = q.question_number;
        selectedAnswer = null;

        // basic information
        document.getElementById('question-number').textContent = questionNumber;
        document.getElementById('target-word').textContent = q.target_word;

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
            choiceElement.textContent = c.en || ''; // default to English
            choiceElement.dataset.en = c.en || '';
            choiceElement.dataset.zh = c.zh || '';

            // float tooltip
            if (q.hover_zh_enabled && c.zh) {
                choiceElement.addEventListener('mouseenter', () => showTooltip(choiceElement, c.zh));
                choiceElement.addEventListener('mouseleave', hideTooltip);
            }

            choiceElement.onclick = () => selectChoice(choiceElement, c.en || '');
            choicesContainer.appendChild(choiceElement);
        });

        // submit button
        document.getElementById('submit-answer').disabled = true;

        // progress bar: completed is questionNumber - 1
        updateProgressBar(questionNumber - 1, 50);
    } catch (error) {
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

    try {
        const answerData = await apiRequest(`/api/sessions/${currentSession.session_id}/answer`, {
            method: 'POST',
            body: JSON.stringify({
                word_id: currentQuestion.word_id,
                user_answer: selectedAnswer,
                // Note: maintaining backward compatibility with previous sentence field
                question_text: currentQuestion.sentence
            })
        });

        // Update score
        sessionScore += answerData.score_change;
        document.getElementById('current-score').textContent = sessionScore;

        // Show result
        showAnswerResult(answerData);

    } catch (error) {
        showError('Failed to submit answer. Please try again.');
    }
}

function showAnswerResult(answerData) {
    const correctEn = (currentQuestion.correct_answer_i18n && currentQuestion.correct_answer_i18n.en) || '';

    // Highlight choices
    document.querySelectorAll('.choice').forEach(choice => {
        if (choice.textContent === correctEn) {
            choice.classList.add('correct');
        } else if (choice.textContent === selectedAnswer && !answerData.is_correct) {
            choice.classList.add('incorrect');
        }
    });

    // Show result
    document.getElementById('result-title').textContent = answerData.is_correct ? '✅ Correct!' : '❌ Incorrect';
    document.getElementById('result-message').textContent = answerData.is_correct 
        ? 'Well done! You got it right.' 
        : 'Don\'t worry, keep learning!';
    document.getElementById('result-message').className = `result-message ${answerData.is_correct ? 'correct' : 'incorrect'}`;

    // explanation (if any) - bilingual display
    const expEn = answerData.explanation_en || '';
    const expZh = answerData.explanation_zh || '';
    const expEl = document.getElementById('explanation');
    expEl.innerHTML = '';
    const enDiv = document.createElement('div');
    const enStrong = document.createElement('strong');
    enStrong.textContent = 'Correct answer (EN):';
    enDiv.appendChild(enStrong);
    enDiv.appendChild(document.createTextNode(' ' + expEn));
    expEl.appendChild(enDiv);
    const zhDiv = document.createElement('div');
    const zhStrong = document.createElement('strong');
    zhStrong.textContent = '正确释义（ZH）：';
    zhDiv.appendChild(zhStrong);
    zhDiv.appendChild(document.createTextNode(' ' + (expZh || '（无）')));
    expEl.appendChild(zhDiv);

    showScreen('result-screen');
}

async function nextQuestion() {
    showScreen('quiz-screen');
    await loadNextQuestion();
}

async function showSessionComplete() {
    // Calculate final stats
    const accuracy = questionNumber > 0 ? Math.round((sessionScore / questionNumber) * 100) : 0;
    
    document.getElementById('final-questions').textContent = questionNumber;
    document.getElementById('final-correct').textContent = sessionScore;
    document.getElementById('final-score').textContent = sessionScore;
    document.getElementById('final-accuracy').textContent = accuracy + '%';

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