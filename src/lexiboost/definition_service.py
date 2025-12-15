#!/usr/bin/env python3
"""
Real-time Definition Service for LexiBoost
Uses the explainer module to generate definitions and distractors in real-time
"""

import os
from typing import Dict, Optional
from .explainer import explain_word
from .question_preloader import question_preloader

class DefinitionService:
    """Service for generating real-time definitions and distractors"""
    
    def __init__(self):
        self.default_level = os.getenv("LEXIBOOST_DEFAULT_LEVEL", "k12")
    
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
            cached_explanation = question_preloader.get_cached_explanation(word, level)
            if cached_explanation:
                return cached_explanation
        except Exception:
            pass  # If preloader not available, continue with normal flow
            
        try:
            explanation = explain_word(word, level=level) 
            question_preloader.cache_explanation(word, level, explanation)
            return explanation
        except Exception as e:
            print(f"DefinitionService: Failed to get explanation for '{word}': {e}")
            pass

# Global instance
definition_service = DefinitionService()