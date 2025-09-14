# LexiBoost

🚀 **English Vocabulary Learning App for Kids**

LexiBoost helps children learn English vocabulary through engaging single-sentence multiple-choice quizzes. The app uses a spaced repetition system (SRS) to optimize learning and retention.

## Features

- **50-Question Sessions**: Each quiz session contains 50 carefully selected questions
- **Smart Spaced Repetition**: Words are reviewed at optimal intervals (0d→1d→3d→7d→14d)
- **Wrongbook System**: Incorrect words are automatically added to a review queue
- **Dynamic Definitions**: Real-time definition generation using AI (with fallback support)
- **Progress Tracking**: Daily and total score tracking
- **CSV Import**: Import custom word lists via CSV files (simplified format)
- **Kid-Friendly Interface**: Simple, colorful, and engaging design
- **Self-Testing**: Built-in system diagnostics

## Quick Start

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install fire pydantic openai  # For dynamic definition generation
   ```

2. **Configure AI Service (Optional)**:
   For real-time AI-powered definitions, set environment variables:
   ```bash
   # For Azure OpenAI
   export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
   export AZURE_OPENAI_API_KEY="your-api-key"
   export AZURE_OPENAI_API_VERSION="2024-08-01-preview"
   export AZURE_OPENAI_DEPLOYMENT="gpt-4o-mini"
   
   # For OpenAI API
   export OPENAI_API_KEY="your-openai-api-key"
   ```
   If not configured, the app will use fallback definitions.

3. **Run the Application**:
   ```bash
   python app.py
   ```

4. **Open Browser**:
   Navigate to `http://localhost:5000`

4. **Start Learning**:
   - Enter your name
   - Click "Start Quiz Session"
   - Answer questions and build your vocabulary!

## How It Works

### Question Generation
- The app generates safe, age-appropriate sentences (6-16 words)
- Target words are highlighted in the sentence  
- Each question has 1 correct answer and 2+ distractors
- **Definitions are generated dynamically** using AI or fallback templates
- Questions adapt to different difficulty levels (k12, general, academic)

### Spaced Repetition System (SRS)
- **Correct Answer**: Word moves to next SRS interval
- **Incorrect Answer**: Word returns to beginning of cycle
- **Graduation**: Words are removed from wrongbook after 3 correct answers

### Scoring System
- **+1 point** for each correct answer
- **Daily scores** and **total scores** are tracked
- **Accuracy statistics** shown at session completion

## API Endpoints

- `POST /api/users` - Create new user
- `GET /api/users/{username}` - Get user info
- `POST /api/users/{user_id}/session/start` - Start quiz session
- `GET /api/sessions/{session_id}/question` - Get next question
- `POST /api/sessions/{session_id}/answer` - Submit answer
- `GET /api/users/{user_id}/stats` - Get user statistics
- `POST /api/users/{user_id}/wrongbook/import` - Import CSV wordlist
- `GET /api/self-test` - Run system diagnostics

## CSV Import Format

The simplified format only requires the word itself:

```csv
word,category
apple,fruit
book,object
run,action
happy,emotion
```

Optional fields: `category`, `register`, `notes`. Definitions are generated dynamically when needed.

## Testing

Run the test suite:
```bash
python -m pytest test_app.py -v
```

Run self-tests:
```bash
curl http://localhost:5000/api/self-test
```

## Technology Stack

- **Backend**: Python Flask with SQLite database
- **Frontend**: HTML, CSS, JavaScript
- **Database**: SQLite with SRS tracking
- **Testing**: pytest

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests to ensure functionality
5. Submit a pull request

## License

This project is licensed under the Apache License 2.0 - see the LICENSE file for details.