#!/usr/bin/env python3
"""
Simple integration tests for LexiBoost application
These tests run against the live application
"""

import requests
import json

BASE_URL = 'http://localhost:5000'

def test_self_test_endpoint():
    """Test the self-test endpoint"""
    response = requests.get(f'{BASE_URL}/api/self-test')
    assert response.status_code == 200
    data = response.json()
    assert data['overall_status'] == 'PASS'
    assert len(data['tests']) >= 3
    print("✅ Self-test endpoint working")

def test_user_creation_and_retrieval():
    """Test user creation and retrieval"""
    # Create user
    user_data = {'username': 'integration_test_user'}
    response = requests.post(f'{BASE_URL}/api/users', json=user_data)
    
    if response.status_code == 400:
        # User might already exist, try to get it
        response = requests.get(f'{BASE_URL}/api/users/integration_test_user')
        assert response.status_code == 200
    else:
        assert response.status_code == 200
    
    data = response.json()
    assert data['username'] == 'integration_test_user'
    assert 'user_id' in data
    print("✅ User creation/retrieval working")
    return data['user_id']

def test_session_and_question_flow():
    """Test session creation and question retrieval"""
    user_id = test_user_creation_and_retrieval()
    
    # Start session
    response = requests.post(f'{BASE_URL}/api/users/{user_id}/session/start')
    assert response.status_code == 200
    session_data = response.json()
    assert 'session_id' in session_data
    session_id = session_data['session_id']
    
    # Get question
    response = requests.get(f'{BASE_URL}/api/sessions/{session_id}/question')
    assert response.status_code == 200
    question_data = response.json()
    assert 'sentence' in question_data
    assert 'target_word' in question_data
    assert 'choices_i18n' in question_data
    assert len(question_data['choices_i18n']) >= 3
    print("✅ Session and question flow working")

def test_user_stats():
    """Test user statistics endpoint"""
    user_id = test_user_creation_and_retrieval()
    
    response = requests.get(f'{BASE_URL}/api/users/{user_id}/stats')
    assert response.status_code == 200
    data = response.json()
    assert 'daily_score' in data
    assert 'total_score' in data
    assert 'wrongbook_count' in data
    print("✅ User stats working")

def run_all_tests():
    """Run all integration tests"""
    print("🚀 Running LexiBoost Integration Tests...")
    try:
        test_self_test_endpoint()
        test_user_creation_and_retrieval()
        test_session_and_question_flow()
        test_user_stats()
        print("\n🎉 All integration tests passed!")
        return True
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        return False

if __name__ == '__main__':
    success = run_all_tests()
    exit(0 if success else 1)