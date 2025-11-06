#!/usr/bin/env python3
"""
Quick test to verify session completion behavior
"""

import requests
import json

BASE_URL = "http://localhost:5000"
SESSION_ID = 59

def test_session_completion():
    """Test that session completes after 3 questions"""
    print(f"Testing session completion for session {SESSION_ID}")
    
    for i in range(1, 5):  # Try to get 4 questions (should only get 3)
        print(f"\n--- Attempting to get question {i} ---")
        
        # Get question
        response = requests.get(f"{BASE_URL}/api/sessions/{SESSION_ID}/question")
        
        if response.status_code == 200:
            data = response.json()
            
            if 'session_complete' in data:
                print(f"✅ Session completed after {i-1} questions")
                print(f"   Session complete: {data['session_complete']}")
                if 'message' in data:
                    print(f"   Message: {data['message']}")
                if 'reason' in data:
                    print(f"   Reason: {data['reason']}")
                return True
            else:
                print(f"   Question {data.get('question_number', '?')}: {data.get('target_word', 'Unknown word')}")
                
                # Submit a correct answer
                answer_data = {
                    "word_id": data.get('word_id'),
                    "user_answer": data.get('correct_answer_i18n', {}).get('en', ''),
                    "correct_answer": data.get('correct_answer_i18n', {}).get('en', ''),
                    "question_text": data.get('question_text', '')
                }
                
                answer_response = requests.post(
                    f"{BASE_URL}/api/sessions/{SESSION_ID}/answer",
                    json=answer_data
                )
                
                if answer_response.status_code == 200:
                    answer_result = answer_response.json()
                    print(f"   Answer submitted: {'✅ Correct' if answer_result.get('is_correct') else '❌ Wrong'}")
                else:
                    print(f"   ❌ Failed to submit answer: {answer_response.status_code}")
        else:
            print(f"   ❌ Failed to get question: {response.status_code}")
            return False
    
    print("⚠️  Session did not complete after 4 attempts - this might indicate a problem")
    return False

if __name__ == "__main__":
    test_session_completion()