#!/usr/bin/env python3
import csv
import sys
import os

PROJECT_ROOT = os.path.dirname(__file__)
SRC_PATH = os.path.join(PROJECT_ROOT, 'src')
if SRC_PATH not in sys.path:
    sys.path.append(SRC_PATH)

from lexiboost.definition_service import definition_service  # type: ignore  # noqa: E402

def add_chinese_translations():
    input_file = 'wrong_words_daniel_latest_session.csv'
    output_file = 'wrong_words_daniel_latest_session.csv'
    
    # Read existing CSV
    words_data = []
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        words_data = list(reader)
    
    print(f"Processing {len(words_data)} words...")
    
    # Add Chinese translations
    for i, row in enumerate(words_data):
        word = row['word']
        print(f"Processing {i+1}/{len(words_data)}: {word}")
        
        try:
            # Get explanation from definition service
            explanation = definition_service.get_explanation(word, 'k12')
            if explanation and hasattr(explanation, 'word_zh'):
                row['chinese_meaning'] = explanation.word_zh
            else:
                row['chinese_meaning'] = '翻译获取失败'
        except Exception as e:
            print(f"Error processing {word}: {e}")
            row['chinese_meaning'] = '翻译获取失败'
    
    # Write updated CSV
    fieldnames = ['word', 'definition', 'chinese_meaning']
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(words_data)
    
    print(f"Updated CSV saved to {output_file}")

if __name__ == '__main__':
    add_chinese_translations()
