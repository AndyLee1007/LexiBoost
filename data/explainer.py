#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Word Explainer via Azure OpenAI (LLM)
- Input: a word
- Output: JSON with English & Chinese definitions, POS, and bilingual examples
- CLI powered by Fire: python word_explainer.py explain "giant" --level=k12
- Batch: python word_explainer.py explain_many words.txt --indent=2
"""

import csv
import json
import os
import sys
import time
from typing import List, Optional

import fire
from pydantic import BaseModel, Field, ValidationError

# --- Azure OpenAI (OpenAI SDK v1.x with Azure endpoint) ---
# pip install openai==1.* (or latest 1.x)
from openai import AzureOpenAI, OpenAI
from openai._exceptions import APIStatusError, RateLimitError, APIConnectionError, APIError


# ---------------------------
# Configuration via ENV VARS
# ---------------------------
# Required:
#   AZURE_OPENAI_ENDPOINT   e.g. https://your-aoai-resource.openai.azure.com/
#   AZURE_OPENAI_API_KEY
#   AZURE_OPENAI_API_VERSION  e.g. 2024-08-01-preview
#   AZURE_OPENAI_DEPLOYMENT   your deployed model name (e.g. gpt-4o-mini, gpt-4o, gpt-35-turbo)
#
# Optional:
#   WORD_EXPLAINER_DEFAULT_LEVEL  default: "k12"
#   WORD_EXPLAINER_TEMPERATURE    default: 0.2

AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
AZURE_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview").strip()
AZURE_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini").strip()


OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL       = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

DEFAULT_INPUT_PATH = os.getenv("WORD_EXPLAINER_DEFAULT_PATH", "data/extracted/b1_words_with_topics.csv").strip()
DEFAULT_OUTPUT_PATH = os.getenv("WORD_EXPLAINER_DEFAULT_OUTPUT_PATH", "data/explained/b1_words_with_topics_explained.csv").strip()
DEFAULT_LEVEL = os.getenv("WORD_EXPLAINER_DEFAULT_LEVEL", "k12")
DEFAULT_TEMPERATURE = float(os.getenv("WORD_EXPLAINER_TEMPERATURE", "0.2"))

def validate_azure_config():
    return all([
        AZURE_ENDPOINT,
        AZURE_API_KEY,
        AZURE_API_VERSION,
        AZURE_DEPLOYMENT
    ])

if not validate_azure_config():
    # Don't crash on import—only warn; CLI will raise on call for better UX.
    sys.stderr.write(
        "[WARN] Missing Azure OpenAI configuration. Set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, "
        "AZURE_OPENAI_API_VERSION, and AZURE_OPENAI_DEPLOYMENT.\n"
    )

# ---------------------------
# Pydantic schema for output
# ---------------------------

class ExampleItem(BaseModel):
    en: str = Field(..., description="Example sentence in English using the word in the intended sense.")
    zh: str = Field(..., description="Chinese translation of the example sentence.")

class WordExplanation(BaseModel):
    word: str
    pos: List[str] = Field(..., description="Part-of-speech tags like ['n','v','adj'].")
    definition_en: str = Field(..., description="Concise, plain-English definition for general readers.")
    definition_zh: str = Field(..., description="Natural Chinese explanation matching the English definition.")
    register: Optional[str] = Field(None, description="Optional: formality/usage register (e.g., academic, informal).")
    notes: Optional[str] = Field(None, description="Optional: pitfalls, common confusions, or collocations.")
    examples: List[ExampleItem] = Field(..., min_items=1, max_items=3)
    distractors_en: List[str] = Field(..., min_items=3, max_items=3, description="3 plausible but incorrect English definitions for quiz options.")
    distractors_zh: List[str] = Field(..., min_items=3, max_items=3, description="Chinese translations aligned with distractors_en.")
# ---------------------------
# Prompt & LLM call
# ---------------------------

SYSTEM_PROMPT = """You are a bilingual lexicographer and quiz generator.
Return STRICT JSON only (no markdown). Avoid IPA and HTML.

Output must be concise, accurate, and usable for vocabulary learning apps."""

def make_user_prompt(word: str, level: str) -> str:
    """
    level:
      - general : everyday adult learner, concise
      - k12     : simpler language suitable for grade 5-9
      - academic: precise, slightly more formal
    """
    return f"""
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
- distractors_en (3 alternative incorrect definitions in English only, same style and length as definition_en — similar word count, plausible but clearly wrong)
- distractors_zh (the natural Chinese translations of the 3 distractors above, aligned with distractors_en)

Requirements:
- "definition_en" must reflect the intended sense and difficulty of {level}, expressed clearly in ~8-12 words.
- "definition_zh" must be a natural and accurate translation of definition_en.
- Each item in "distractors_en" must:
  • be plausible for the word but ultimately incorrect,
  • closely match the word count of definition_en (±2 words),
  • follow the same formal tone and structure.
- "distractors_zh" must be faithful and natural Chinese translations of distractors_en, not literal.
- "examples" must use the word in the sense from definition_en, not the distractors.
- Output ONLY valid JSON. Do not include any extra text, prefaces, or code fences.
"""

def _get_client() -> OpenAI:
    if AZURE_ENDPOINT:
        if not AZURE_API_KEY:
            raise RuntimeError("Azure route selected. Please set AZURE_OPENAI_API_KEY or set AZURE_USE_AAD=true.")
        return AzureOpenAI(
            azure_endpoint=AZURE_ENDPOINT,
            api_version=AZURE_API_VERSION,
            api_key=AZURE_API_KEY,
        )

    if not OPENAI_API_KEY:
        raise RuntimeError(
            "No backend configured. Set either:\n"
            "- Azure: AZURE_OPENAI_ENDPOINT (+ AZURE_USE_AAD=true or AZURE_OPENAI_API_KEY), or\n"
            "- OpenAI: OPENAI_API_KEY"
        )
    return OpenAI(api_key=OPENAI_API_KEY)

def _chat_once(word: str, level: str, temperature: float = DEFAULT_TEMPERATURE, timeout: int = 60) -> str:
    """
    Returns raw JSON string from the model (no markdown).
    """
    client = _get_client()
    model_name = AZURE_DEPLOYMENT
    kwargs = {
        "model": model_name,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": make_user_prompt(word, level)},
        ],
        "timeout": timeout,
    }

    if "nano" not in model_name:
        kwargs["temperature"] = temperature
        kwargs["max_tokens"] = 450

    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content

def _with_retries(call, max_retries=3, base_delay=1.0):
    for i in range(max_retries):
        try:
            return call()
        except (RateLimitError, APIConnectionError, APIStatusError, APIError) as e:
            if i == max_retries - 1:
                raise
            sleep_s = base_delay * (2 ** i)
            sys.stderr.write(f"[WARN] API error: {type(e).__name__}: {e}. Retrying in {sleep_s:.1f}s...\n")
            time.sleep(sleep_s)

# ---------------------------
# Public API
# ---------------------------

def explain_word(word: str, level: str = DEFAULT_LEVEL, indent: Optional[int] = None) -> dict:
    """
    Return a Python dict matching WordExplanation schema.
    :param word: single English token (case-insensitive)
    :param level: 'general' | 'k12' | 'academic'
    :param indent: optional pretty-printing indent for JSON
    """
    word = word.strip()
    if not word:
        raise ValueError("word is empty")

    raw_json = _with_retries(lambda: _chat_once(word, level))
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Model did not return valid JSON. Raw:\n{raw_json}") from e

    try:
        parsed = WordExplanation(**data)
    except ValidationError as ve:
        # Surface validation errors with the raw payload for debugging.
        raise ValueError(f"JSON schema validation failed:\n{ve}\n\nRaw:\n{json.dumps(data, ensure_ascii=False, indent=2)}")

    # Optionally pretty-print to stdout for CLI usage
    if indent is not None:
        print(json.dumps(parsed.model_dump(), ensure_ascii=False, indent=indent))
    return parsed.model_dump()


def explain_many(input_path: str = DEFAULT_INPUT_PATH, output_path: str = DEFAULT_OUTPUT_PATH, level: str = DEFAULT_LEVEL, indent: Optional[int] = 2) -> List[dict]:
    """
    Batch mode (CSV input).
    Input format: CSV with header 'word,category'
    - Handles UTF-8 BOM
    - Supports skipping comments (#)
    - If a word contains '/', only keep the first part and log a warning.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(input_path)

    results = []
    with open(input_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(
            (line for line in f if line.strip() and not line.strip().startswith("#"))
        )

        if "word" not in reader.fieldnames or "category" not in reader.fieldnames:
            raise ValueError(f"CSV header must include 'word,category' (got {reader.fieldnames})")

        for row in reader:
            word = row["word"].strip()
            category = row["category"].strip()

            if "/" in word:
                original = word
                word = word.split("/")[0].strip()
                sys.stderr.write(f"[WARN] Word '{original}' normalized to '{word}'\n")

            try:
                res = explain_word(word, level=level, indent=None)
                res["category"] = category
                results.append(res)
            except Exception as e:
                sys.stderr.write(f"[ERROR] Failed on '{word}': {e}\n")
                results.append({"word": word, "category": category, "error": str(e)})

    if indent is not None:
        print(json.dumps(results, ensure_ascii=False, indent=indent))
    if results:
        fieldnames = set()
        for r in results:
            fieldnames.update(r.keys())
        fieldnames = list(fieldnames)

        if "word" in fieldnames:
            fieldnames.remove("word")
            fieldnames = ["word"] + fieldnames

        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in results:
                writer.writerow(r)


def main():
    """
    Fire CLI entry:
      - Explain single word:
          python word_explainer.py explain "giant" --level=general --indent=2
      - Batch explain from file:
          python word_explainer.py explain_many words.txt --level=k12
    """
    fire.Fire(explain_many)


if __name__ == "__main__":
    main()
