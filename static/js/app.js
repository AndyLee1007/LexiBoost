// LexiBoost JavaScript Application

let currentUser = null;
let currentSession = null;
let currentQuestion = null;
let questionNumber = 0;
let sessionScore = 0;
let selectedAnswer = null;

// Utility functions
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
        const questionData = await apiRequest(`/api/sessions/${currentSession.session_id}/question`);
        
        if (questionData.session_complete) {
            await showSessionComplete();
            return;
        }

        currentQuestion = questionData;
        questionNumber = questionData.question_number;
        selectedAnswer = null;

        // Update UI
        document.getElementById('question-number').textContent = questionNumber;
        document.getElementById('sentence-text').textContent = questionData.sentence;
        document.getElementById('target-word').textContent = questionData.target_word;
        
        // Highlight target word in sentence
        const sentenceElement = document.getElementById('sentence-text');
        const highlightedSentence = questionData.sentence.replace(
            new RegExp(`\\b${questionData.target_word}\\b`, 'gi'),
            `<mark>${questionData.target_word}</mark>`
        );
        sentenceElement.innerHTML = highlightedSentence;

        // Create answer choices
        const choicesContainer = document.getElementById('answer-choices');
        choicesContainer.innerHTML = '';
        
        questionData.choices.forEach((choice, index) => {
            const choiceElement = document.createElement('div');
            choiceElement.className = 'choice';
            choiceElement.textContent = choice;
            choiceElement.onclick = () => selectChoice(choiceElement, choice);
            choicesContainer.appendChild(choiceElement);
        });

        // Reset submit button
        document.getElementById('submit-answer').disabled = true;
        
        // Update progress
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
                correct_answer: currentQuestion.correct_answer,
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
    // Update choice colors
    document.querySelectorAll('.choice').forEach(choice => {
        if (choice.textContent === currentQuestion.correct_answer) {
            choice.classList.add('correct');
        } else if (choice.textContent === selectedAnswer && !answerData.is_correct) {
            choice.classList.add('incorrect');
        }
    });

    // Show result screen
    document.getElementById('result-title').textContent = answerData.is_correct ? '✅ Correct!' : '❌ Incorrect';
    document.getElementById('result-message').textContent = answerData.is_correct 
        ? 'Well done! You got it right.' 
        : 'Don\'t worry, keep learning!';
    document.getElementById('result-message').className = `result-message ${answerData.is_correct ? 'correct' : 'incorrect'}`;
    document.getElementById('explanation').textContent = `Correct answer: ${answerData.explanation}`;

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

// PDF preprocessing functionality
let currentTSVContent = '';

async function preprocessPDF() {
    const fileInput = document.getElementById('pdf-file');
    const file = fileInput.files[0];
    
    if (!file) {
        showError('Please select a PDF file');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        showPDFProcessing(true);
        
        const response = await fetch('/api/preprocess-pdf', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();
        
        if (response.ok) {
            showPDFResults(result);
            currentTSVContent = result.tsv_content;
            fileInput.value = ''; // Clear file input
        } else {
            showError(result.error);
            showPDFProcessing(false);
        }
    } catch (error) {
        showError('Failed to process PDF file');
        showPDFProcessing(false);
    }
}

function showPDFProcessing(isProcessing) {
    const resultsDiv = document.getElementById('pdf-results');
    const outputDiv = document.getElementById('pdf-output');
    
    if (isProcessing) {
        resultsDiv.classList.remove('hidden');
        outputDiv.innerHTML = '<p>Processing PDF... Please wait.</p>';
    } else {
        resultsDiv.classList.add('hidden');
    }
}

function showPDFResults(result) {
    const resultsDiv = document.getElementById('pdf-results');
    const outputDiv = document.getElementById('pdf-output');
    const downloadBtn = document.getElementById('download-tsv');
    
    resultsDiv.classList.remove('hidden');
    downloadBtn.classList.remove('hidden');
    
    outputDiv.innerHTML = `
        <div class="pdf-success">
            <p><strong>✅ ${result.message}</strong></p>
            <p>Extracted ${result.word_count} unique words</p>
            <p><strong>Sample words:</strong> ${result.words_processed.join(', ')}</p>
            <div class="tsv-preview">
                <h5>TSV Preview (first 5 lines):</h5>
                <pre>${result.tsv_content.split('\n').slice(0, 5).join('\n')}</pre>
            </div>
        </div>
    `;
}

function downloadTSV() {
    if (!currentTSVContent) {
        showError('No TSV content to download');
        return;
    }
    
    const blob = new Blob([currentTSVContent], { type: 'text/tab-separated-values' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'vocabulary_words.tsv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
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