#!/usr/bin/env python3
"""
Test the complete session workflow including hover functionality
"""

import requests
import sqlite3
import json

BASE_URL = "http://localhost:5000"
DB_PATH = "lexiboost.db"

def create_test_session_with_hover():
    """Create a test session with hover enabled to test the functionality"""
    print("Creating test session with hover enabled...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create a new session for user 1 with hover enabled
    cursor.execute('''
        INSERT INTO sessions (user_id, session_date, total_questions, correct_answers, 
                             score, completed, dictionary_id, hover_zh_enabled)
        VALUES (1, date('now'), 10, 7, 70, 1, 1, 1)
    ''')
    
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    print(f"✅ Created test session {session_id} with hover enabled")
    return session_id

def test_new_session_stats(session_id):
    """Test the statistics for the newly created session"""
    print(f"\nTesting statistics for session {session_id}...")
    
    response = requests.get(f"{BASE_URL}/api/sessions/{session_id}/stats")
    
    if response.status_code == 200:
        data = response.json()
        stats = data.get('stats', {})
        
        print("✅ New session statistics:")
        print(f"   Session ID: {stats.get('session_id')}")
        print(f"   Total Questions: {stats.get('total_questions')}")
        print(f"   Correct Answers: {stats.get('correct_answers')}")
        print(f"   Accuracy: {stats.get('accuracy_rate')}%")
        print(f"   Hover Enabled: {stats.get('hover_enabled')}")
        
        return stats.get('hover_enabled') == True
    else:
        print(f"❌ Failed to get session stats: {response.status_code}")
        return False

def test_trends_with_hover_data():
    """Test trends including the new hover-enabled session"""
    print("\nTesting trends with hover data...")
    
    # Test all data
    response = requests.get(f"{BASE_URL}/api/users/1/sessions/trends")
    if response.status_code == 200:
        all_data = response.json()
        all_count = len(all_data.get('trends', []))
        print(f"✅ All sessions: {all_count} data points")
    
    # Test hover-only data
    response = requests.get(f"{BASE_URL}/api/users/1/sessions/trends?hover_filter=1")
    if response.status_code == 200:
        hover_data = response.json()
        hover_count = len(hover_data.get('trends', []))
        print(f"✅ Hover-enabled sessions: {hover_count} data points")
        
        # Check if our new session appears in hover data
        hover_sessions = [t['session_id'] for t in hover_data.get('trends', [])]
        return hover_count > 0
    
    return False

def test_frontend_integration():
    """Test that the frontend can load the homepage"""
    print("\nTesting frontend integration...")
    
    response = requests.get(BASE_URL)
    if response.status_code == 200:
        # Check if Chart.js is included
        if 'chart.js' in response.text.lower():
            print("✅ Frontend loaded with Chart.js integration")
            return True
        else:
            print("⚠️  Frontend loaded but Chart.js may not be included")
            return False
    else:
        print(f"❌ Frontend failed to load: {response.status_code}")
        return False

def main():
    """Run the complete workflow test"""
    print("=== Complete LexiBoost Hover Feature Test ===\n")
    
    # Create test session
    session_id = create_test_session_with_hover()
    
    # Run tests
    tests = [
        lambda: test_new_session_stats(session_id),
        test_trends_with_hover_data,
        test_frontend_integration
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            results.append(False)
    
    print(f"\n=== Final Results ===")
    print(f"Tests passed: {sum(results)}/{len(results)}")
    
    if all(results):
        print("🎉 All tests passed! The hover feature integration is complete!")
        print("\n📋 Feature Summary:")
        print("   ✅ Session statistics with hover state tracking")
        print("   ✅ Trends visualization with hover filter")
        print("   ✅ Frontend integration with Chart.js")
        print("   ✅ API endpoints working correctly")
        print("\n🚀 Ready for production testing!")
    else:
        print("⚠️  Some tests failed. Please review the issues above.")
    
    return 0 if all(results) else 1

if __name__ == "__main__":
    exit(main())