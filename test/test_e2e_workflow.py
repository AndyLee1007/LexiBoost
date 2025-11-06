#!/usr/bin/env python3
"""
End-to-end test to simulate the browser behavior and identify the exact issue
"""

import requests
import json
import time

BASE_URL = "http://localhost:5000"

def test_complete_workflow():
    """Test the complete workflow including session completion"""
    print("=== Testing Complete E2E Workflow ===\n")
    
    # Step 1: Create user
    print("1. Creating user...")
    try:
        user_response = requests.post(f"{BASE_URL}/api/users", json={"username": "TestUser"})
        if user_response.status_code == 200:
            user_data = user_response.json()
            user_id = user_data['user_id']
            print(f"   ✅ User created: ID {user_id}")
        else:
            # User might exist, try to get it
            user_response = requests.get(f"{BASE_URL}/api/users/TestUser")
            user_data = user_response.json()
            user_id = user_data['user_id']
            print(f"   ✅ Using existing user: ID {user_id}")
    except Exception as e:
        print(f"   ❌ User creation failed: {e}")
        return False
    
    # Step 2: Start session
    print("\n2. Starting session...")
    try:
        session_response = requests.post(f"{BASE_URL}/api/users/{user_id}/session/start", json={"dictionary_id": 1})
        if session_response.status_code == 200:
            session_data = session_response.json()
            session_id = session_data['session_id']
            print(f"   ✅ Session created: ID {session_id}")
        else:
            print(f"   ❌ Session creation failed: {session_response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Session creation failed: {e}")
        return False
    
    # Step 3: Answer 3 questions
    print("\n3. Playing through 3 questions...")
    for i in range(1, 4):
        print(f"\n   Question {i}:")
        
        # Get question
        try:
            q_response = requests.get(f"{BASE_URL}/api/sessions/{session_id}/question")
            if q_response.status_code == 200:
                q_data = q_response.json()
                
                if 'session_complete' in q_data:
                    print(f"      ⚠️  Session completed unexpectedly at question {i}")
                    return False
                
                word = q_data.get('target_word', 'unknown')
                print(f"      Word: {word}")
                
                # Submit answer
                answer_payload = {
                    "word_id": q_data.get('word_id'),
                    "user_answer": q_data.get('correct_answer_i18n', {}).get('en', ''),
                    "correct_answer": q_data.get('correct_answer_i18n', {}).get('en', ''),
                    "question_text": q_data.get('question_text', '')
                }
                
                a_response = requests.post(f"{BASE_URL}/api/sessions/{session_id}/answer", json=answer_payload)
                if a_response.status_code == 200:
                    a_data = a_response.json()
                    print(f"      ✅ Answer: {'Correct' if a_data.get('is_correct') else 'Wrong'}")
                else:
                    print(f"      ❌ Answer submission failed: {a_response.status_code}")
                    return False
            else:
                print(f"      ❌ Question request failed: {q_response.status_code}")
                return False
        except Exception as e:
            print(f"      ❌ Question {i} failed: {e}")
            return False
    
    # Step 4: Try to get 4th question (should return session_complete)
    print("\n4. Checking session completion...")
    try:
        q_response = requests.get(f"{BASE_URL}/api/sessions/{session_id}/question")
        if q_response.status_code == 200:
            q_data = q_response.json()
            
            if 'session_complete' in q_data and q_data['session_complete']:
                print("   ✅ Session correctly marked as complete")
                
                # Step 5: Test session stats API
                print("\n5. Testing session statistics...")
                stats_response = requests.get(f"{BASE_URL}/api/sessions/{session_id}/stats")
                if stats_response.status_code == 200:
                    stats_data = stats_response.json()
                    if stats_data.get('status') == 'success':
                        stats = stats_data.get('stats', {})
                        print(f"   ✅ Session stats: {stats.get('total_questions')} questions, {stats.get('accuracy_rate')}% accuracy")
                    else:
                        print("   ❌ Session stats API returned error")
                        return False
                else:
                    print(f"   ❌ Session stats API failed: {stats_response.status_code}")
                    return False
                
                # Step 6: Test trends API
                print("\n6. Testing trends API...")
                trends_response = requests.get(f"{BASE_URL}/api/users/{user_id}/sessions/trends")
                if trends_response.status_code == 200:
                    trends_data = trends_response.json()
                    if trends_data.get('status') == 'success':
                        trends = trends_data.get('trends', [])
                        print(f"   ✅ Trends data: {len(trends)} data points")
                    else:
                        print("   ❌ Trends API returned error")
                        return False
                else:
                    print(f"   ❌ Trends API failed: {trends_response.status_code}")
                    return False
                
                return True
            else:
                print("   ❌ Session not marked as complete")
                print(f"   Response: {q_data}")
                return False
        else:
            print(f"   ❌ Final question request failed: {q_response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Session completion check failed: {e}")
        return False

if __name__ == "__main__":
    success = test_complete_workflow()
    if success:
        print("\n🎉 All tests passed! The issue should be resolved.")
    else:
        print("\n⚠️  Some tests failed. The issue persists.")
    exit(0 if success else 1)