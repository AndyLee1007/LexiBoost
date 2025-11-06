#!/usr/bin/env python3
"""
Test script to validate the new session statistics and trends feature
"""

import requests
import json
import sys

BASE_URL = "http://localhost:5000"

def test_session_stats_api():
    """Test the session statistics API"""
    print("Testing session statistics API...")
    
    # Use session ID 53 which has good data
    response = requests.get(f"{BASE_URL}/api/sessions/53/stats")
    
    if response.status_code == 200:
        data = response.json()
        print("✅ Session stats API working!")
        print(f"   Status: {data.get('status')}")
        if 'stats' in data:
            stats = data['stats']
            print(f"   Session ID: {stats.get('session_id')}")
            print(f"   Total Questions: {stats.get('total_questions')}")
            print(f"   Correct Answers: {stats.get('correct_answers')}")
            print(f"   Accuracy: {stats.get('accuracy_rate')}%")
            print(f"   New Words: {stats.get('new_words_count')}")
            print(f"   Review Words: {stats.get('review_words_count')}")
            print(f"   Hover Enabled: {stats.get('hover_enabled')}")
            return True
    else:
        print(f"❌ Session stats API failed: {response.status_code}")
        print(f"   Response: {response.text}")
        return False

def test_trends_api():
    """Test the trends API"""
    print("\nTesting trends API...")
    
    # Use user ID 1 which has good trend data
    response = requests.get(f"{BASE_URL}/api/users/1/sessions/trends")
    
    if response.status_code == 200:
        data = response.json()
        print("✅ Trends API working!")
        print(f"   Status: {data.get('status')}")
        
        if 'trends' in data and data['trends']:
            print(f"   Number of data points: {len(data['trends'])}")
            print(f"   Date range: {data['trends'][0]['date']} to {data['trends'][-1]['date']}")
            
            if 'summary' in data:
                summary = data['summary']
                print(f"   Average accuracy: {summary.get('avg_accuracy')}%")
                print(f"   Total sessions: {summary.get('total_sessions')}")
                print(f"   Include hover: {summary.get('include_hover')}")
            return True
        else:
            print("⚠️  No trend data found")
            return False
    else:
        print(f"❌ Trends API failed: {response.status_code}")
        print(f"   Response: {response.text}")
        return False

def test_trends_with_hover_filter():
    """Test trends API with hover filter"""
    print("\nTesting trends API with hover filter...")
    
    # Test with hover filter disabled
    response = requests.get(f"{BASE_URL}/api/users/1/sessions/trends?hover_filter=0")
    
    if response.status_code == 200:
        data = response.json()
        print("✅ Trends API with hover filter working!")
        print(f"   Data points (hover=0): {len(data.get('trends', []))}")
        
        # Test with hover filter enabled
        response2 = requests.get(f"{BASE_URL}/api/users/1/sessions/trends?hover_filter=1")
        if response2.status_code == 200:
            data2 = response2.json()
            print(f"   Data points (hover=1): {len(data2.get('trends', []))}")
            return True
    
    print("❌ Trends API with hover filter failed")
    return False

def main():
    """Run all tests"""
    print("=== LexiBoost Statistics Feature Test ===\n")
    
    tests = [
        test_session_stats_api,
        test_trends_api,
        test_trends_with_hover_filter
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            results.append(False)
    
    print(f"\n=== Test Results ===")
    print(f"Tests passed: {sum(results)}/{len(results)}")
    
    if all(results):
        print("🎉 All tests passed! The statistics feature is working correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())