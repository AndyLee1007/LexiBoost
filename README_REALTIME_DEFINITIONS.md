# Real-time Definition Generation

This version of LexiBoost has been updated to generate definitions and distractors in real-time using LLM services instead of storing them in the database.

## Key Changes

1. **Database Schema**: The `words` table now only stores:
   - `word` (the vocabulary word)
   - `category` (optional classification)
   - `level` (difficulty level, defaults to 'k12')
   - No more `definition_en`, `definition_zh` fields

2. **Real-time Generation**: Each question now calls the LLM explainer service to generate:
   - English definition (level-aware)
   - Chinese translation
   - 3 plausible but incorrect distractors (in both languages)
   - Example sentences

## Configuration

### Mock Mode (Default)
For testing and development, mock definitions are used by default:
```bash
export LEXIBOOST_MOCK_DEFINITIONS=true  # Default
```

### Real LLM Integration
To use real LLM APIs, set the appropriate environment variables:

#### Azure OpenAI
```bash
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_API_KEY="your-api-key"
export AZURE_OPENAI_API_VERSION="2024-08-01-preview"
export AZURE_OPENAI_DEPLOYMENT="gpt-4o-mini"
export LEXIBOOST_MOCK_DEFINITIONS=false
```

#### OpenAI
```bash
export OPENAI_API_KEY="your-api-key"
export LEXIBOOST_MOCK_DEFINITIONS=false
```

## LLM Prompt Template

The system uses this prompt template for generating definitions:

```
Task:
For the English word: {word!r}
Produce STRICT JSON with keys:
- word
- pos (array)
- definition_en (the correct meaning, level-aware: {level})
- definition_zh
- register (optional)
- notes (optional)
- examples (1-2 items, each with en and zh)
- distractors_en (3 alternative incorrect definitions in English only, same style as definition_en, plausible but clearly wrong)
- distractors_zh (the natural Chinese translations of the 3 distractors above, aligned with distractors_en)

Requirements:
- "definition_en" should be single-sense and level-aware: {level}.
- "definition_zh" should be natural, correct, and aligned with definition_en.
- "distractors_en" must look realistic but be wrong for this word, not random nonsense.
- "distractors_zh" must be faithful translations of "distractors_en".
- Examples must use the word in exactly that sense.
- No extra keys. No preface. No code fences.

Output JSON only.
```

## Usage

1. **Import Words**: CSV imports now only need the `word` column:
   ```csv
   word,category
   apple,food
   book,object
   ```

2. **Question Generation**: When a question is requested, the system:
   - Selects a word from the database
   - Calls the LLM explainer service with the word and level
   - Generates real-time definitions and distractors
   - Returns the question with 3 multiple-choice options

3. **Error Handling**: If the LLM service fails, the system falls back to simple mock definitions to ensure continuity.

## Benefits

- **Dynamic Content**: Each question has fresh, contextual definitions
- **Level Awareness**: Definitions are generated based on the specified difficulty level
- **No Storage**: Reduced database size and maintenance
- **Consistent Quality**: LLM ensures consistent definition quality and format
- **Multilingual**: Automatic generation of both English and Chinese content