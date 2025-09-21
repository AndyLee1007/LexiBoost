#!/usr/bin/env python3
"""
Real-time Definition Service for LexiBoost
Uses the explainer module to generate definitions and distractors in real-time
"""

import os
from typing import Dict, Optional

class DefinitionService:
    """Service for generating real-time definitions and distractors"""
    
    def __init__(self):
        self.default_level = os.getenv("LEXIBOOST_DEFAULT_LEVEL", "k12")
        self.mock_mode = os.getenv("LEXIBOOST_MOCK_DEFINITIONS", "true").lower() == "true"
    
    def get_word_explanation(self, word: str, level: Optional[str] = None) -> Dict:
        """
        Get real-time explanation for a word including definitions and distractors.
        First checks preloader cache, then generates if needed.
        
        Returns:
        {
            'word': str,
            'pos': List[str],
            'definition_en': str,
            'definition_zh': str,  
            'register': Optional[str],
            'notes': Optional[str],
            'examples': List[{'en': str, 'zh': str}],
            'distractors_en': List[str],
            'distractors_zh': List[str]
        }
        """
        if not level:
            level = self.default_level
        
        # First try to get from preloader cache
        try:
            from question_preloader import question_preloader
            cached_explanation = question_preloader.get_cached_explanation(word, level)
            if cached_explanation:
                return cached_explanation
        except Exception:
            pass  # If preloader not available, continue with normal flow
            
        if self.mock_mode:
            return self._mock_explanation(word, level)
            
        try:
            from data.explainer import explain_word
            explanation = explain_word(word, level=level) 
            
            # Cache the result for future reuse
            try:
                from question_preloader import question_preloader
                question_preloader.cache_explanation(word, level, explanation)
            except Exception:
                pass  # If caching fails, continue
                
            return explanation
        except Exception:
            # Fallback to mock if LLM fails
            return self._mock_explanation(word, level)
    
    def _mock_explanation(self, word: str, level: str) -> Dict:
        """Mock explanation for testing without real LLM API"""
        # Simple mock definitions based on word
        definitions = {
            'apple': {
                'en': 'A round red or green fruit that grows on trees',
                'zh': '一种生长在树上的红色或绿色圆形水果',
                'word_zh': '苹果'
            },
            'book': {
                'en': 'A written work with pages that you can read',
                'zh': '有页面可以阅读的书面作品',
                'word_zh': '书'
            },
            'happy': {
                'en': 'Feeling pleased, joyful, or content',
                'zh': '感到高兴、快乐或满足',
                'word_zh': '快乐'
            },
            'run': {
                'en': 'To move quickly on foot',
                'zh': '用脚快速移动',
                'word_zh': '跑'
            },
            'house': {
                'en': 'A building where people live',
                'zh': '人们居住的建筑物',
                'word_zh': '房子'
            }
        }
        
        definition = definitions.get(word, {
            'en': f'A word related to {word}',
            'zh': f'与{word}相关的词',
            'word_zh': word[:2] if len(word) > 2 else word  # Simple fallback
        })
        
        return {
            'word': word,
            'word_zh': definition['word_zh'],
            'pos': ['noun'] if word in ['apple', 'book', 'house'] else ['adjective'] if word == 'happy' else ['verb'],
            'definition_en': definition['en'],
            'definition_zh': definition['zh'],
            'register': None,
            'notes': None,
            'examples': [
                {'en': f'I like the {word}.', 'zh': f'我喜欢{word}。'}
            ],
            'distractors_en': [
                'Something completely unrelated to this word',
                'A different concept that is not correct',
                'An incorrect meaning for this term'
            ],
            'distractors_zh': [
                '与这个词完全无关的东西',
                '不正确的不同概念',
                '这个词的错误含义'
            ]
        }
    
    def _fallback_explanation(self, word: str) -> Dict:
        """Fallback explanation when LLM service is unavailable"""
        return {
            'word': word,
            'word_zh': word[:2] if len(word) > 2 else word,  # Simple fallback
            'pos': ['unknown'],
            'definition_en': f'A word meaning related to {word}',
            'definition_zh': f'与{word}相关的词',
            'register': None,
            'notes': None,
            'examples': [
                {'en': f'The {word} is important.', 'zh': f'{word}很重要。'}
            ],
            'distractors_en': [
                'Something completely different',
                'An unrelated concept',
                'A different meaning entirely'
            ],
            'distractors_zh': [
                '完全不同的东西',
                '不相关的概念', 
                '完全不同的含义'
            ]
        }

# Global instance
definition_service = DefinitionService()