# LexiBoost Release Notes

## Version 2.1.0 - September 20, 2025

### ✨ New Features
- **Concise Chinese Translations**: Added `word_zh` field for concise word-level Chinese mappings in question prompts (e.g., "有雾" instead of full definitions)
- **Enhanced Button UX**: Redesigned next question button behavior:
  - Correct answers: Button immediately available
  - Incorrect answers: 3-second countdown before button activation
- **Improved Layout**: Moved Submit Answer and Next Question buttons to right-bottom for better user flow

### 🎨 UI/UX Improvements
- **Consistent Button Styling**: Both Submit Answer and Next Question buttons now use the same blue primary style
- **Better Visual Feedback**: Clear disabled/enabled states for buttons with proper visual indicators
- **Streamlined Interface**: Inline result display without separate result screens
- **Enhanced Tooltips**: Restored hover tooltips for Chinese translations (controlled by `LEXIBOOST_HOVER_ZH`)

### 🔧 Technical Improvements
- **API Enhancement**: Added `target_word_zh` field to question API responses
- **Improved Caching**: Enhanced preloader with word-level Chinese translation caching
- **Code Quality**: Removed unused imports, improved error handling, and consistent formatting
- **Mock Data**: Enhanced mock definitions with proper `word_zh` fallbacks

### 📊 Data Flow
1. **LLM Integration**: `data/explainer.py` now requests concise `word_zh` from language models
2. **Preloader Cache**: `question_preloader.py` stores and serves questions with Chinese word mappings
3. **API Responses**: Flask endpoints return both full definitions and concise word translations
4. **Frontend Display**: Client shows concise Chinese in question prompts, full translations in choices

### 🛠️ Configuration
- `LEXIBOOST_MAX_QUESTIONS`: Maximum questions per session
- `LEXIBOOST_HOVER_ZH`: Enable/disable hover tooltips for Chinese translations
- `LEXIBOOST_MOCK_DEFINITIONS`: Use mock data instead of real LLM calls

### 📁 File Changes
- `app.py`: Enhanced API responses with target_word_zh
- `question_preloader.py`: Updated PreloadedQuestion dataclass
- `definition_service.py`: Added word_zh to mock explanations
- `data/explainer.py`: Updated LLM prompt for concise Chinese
- `static/js/app.js`: Improved button behavior and Chinese display logic
- `templates/index.html`: Updated button containers and styling
- `static/css/style.css`: Enhanced button positioning and visual feedback

### 🎯 User Experience
- **Faster Learning**: Immediate progression for correct answers
- **Better Retention**: Forced pause for incorrect answers to digest information
- **Clearer Understanding**: Concise Chinese word mappings instead of lengthy definitions
- **Professional Interface**: Consistent button styling and positioning