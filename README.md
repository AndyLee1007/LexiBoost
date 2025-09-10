# LexiBoost

🚀 **English Vocabulary Learning App for Kids**

LexiBoost helps children learn English vocabulary through engaging single-sentence multiple-choice quizzes. The app uses a spaced repetition system (SRS) to optimize learning and retention.

## Features

- **50-Question Sessions**: Each quiz session contains 50 carefully selected questions
- **Smart Spaced Repetition**: Words are reviewed at optimal intervals (0d→1d→3d→7d→14d)
- **Wrongbook System**: Incorrect words are automatically added to a review queue
- **Progress Tracking**: Daily and total score tracking
- **CSV Import**: Import custom word lists via CSV files
- **Kid-Friendly Interface**: Simple, colorful, and engaging design
- **Self-Testing**: Built-in system diagnostics

## Quick Start

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the Application**:
   ```bash
   python app.py
   ```

3. **Open Browser**:
   Navigate to `http://localhost:5000`

4. **Start Learning**:
   - Enter your name
   - Click "Start Quiz Session"
   - Answer questions and build your vocabulary!

## How It Works

### Question Generation
- The app generates safe, age-appropriate sentences (6-16 words)
- Target words are highlighted in the sentence
- Each question has 1 correct answer and 2 distractors

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

```csv
word,definition
happy,feeling or showing pleasure or contentment
sad,feeling or showing sorrow or dejection
```

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