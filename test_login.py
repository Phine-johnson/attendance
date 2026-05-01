#!/usr/bin/env python3
"""
Test script to verify login flow works correctly
"""
import requests
import json

BASE_URL = "http://127.0.0.1:5000"

def test_login_flow():
    """Test the complete login flow"""
    print("Testing login flow...")
    
    # Start a session
    session = requests.Session()
    
    # 1. Get login page
    print("1. Getting login page...")
    login_page = session.get(f"{BASE_URL}/login")
    print(f"   Status: {login_page.status_code}")
    if login_page.status_code != 200:
        print("   ERROR: Could not get login page")
        return False
    
    # 2. Try to access dashboard without login (should redirect)
    print("2. Testing dashboard access without login...")
    dashboard_response = session.get(f"{BASE_URL}/dashboard", allow_redirects=False)
    print(f"   Status: {dashboard_response.status_code}")
    if dashboard_response.status_code == 302:
        print("   SUCCESS: Redirected to login as expected")
    else:
        print("   WARNING: Expected redirect to login")
    
    # 3. Login with test credentials (will use demo mode)
    print("3. Attempting login with test credentials...")
    login_data = {
        'email': 'test@example.com',
        'password': 'testpassword'
    }
    login_response = session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=False)
    print(f"   Status: {login_response.status_code}")
    print(f"   Headers: {dict(login_response.headers)}")
    
    if login_response.status_code == 302:
        # Check if redirected to dashboard
        location = login_response.headers.get('Location', '')
        print(f"   Redirected to: {location}")
        if '/dashboard' in location:
            print("   SUCCESS: Login successful, redirected to dashboard")
            
            # 4. Access dashboard after login
            print("4. Accessing dashboard after login...")
            dashboard_after_login = session.get(f"{BASE_URL}/dashboard")
            print(f"   Status: {dashboard_after_login.status_code}")
            if dashboard_after_login.status_code == 200:
                print("   SUCCESS: Dashboard accessible after login")
                return True
            else:
                print("   ERROR: Could not access dashboard after login")
                return False
        else:
            print("   ERROR: Redirected to unexpected location")
            return False
    else:
        print("   INFO: Login returned status {} (not redirect)".format(login_response.status_code))
        # Check if it's showing the login page again with error
        if 'Invalid email or password' in login_response.text:
            print("   ERROR: Login failed - invalid credentials")
        elif 'Demo login' in login_response.text or 'session' in str(login_response.headers).lower():
            # Might have succeeded but not redirected
            print("   INFO: Login may have succeeded but no redirect")
            # Try to access dashboard directly
            dashboard_after_login = session.get(f"{BASE_URL}/dashboard")
            if dashboard_after_login.status_code == 200:
                print("   SUCCESS: Dashboard accessible after login (direct access)")
                return True
            else:
                print("   ERROR: Cannot access dashboard after login")
                return False
        else:
            print("   ERROR: Login failed for unknown reason")
            # Print first 200 chars of response for debugging
            print("   Response preview: {}".format(login_response.text[:200]))
            return False

if __name__ == "__main__":
    success = test_login_flow()
    if success:
        print("\n[PASS] All tests passed!")
    else:
        print("\n[FAIL] Some tests failed!")