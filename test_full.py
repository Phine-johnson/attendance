#!/usr/bin/env python3
"""
Test script to verify full functionality: login -> start service -> QR code generation
"""
import requests
import time

BASE_URL = "http://127.0.0.1:5000"

def test_full_flow():
    """Test the complete flow: login -> start service -> check QR code"""
    print("Testing full functionality flow...")
    
    # Start a session
    session = requests.Session()
    
    # 1. Login
    print("1. Logging in...")
    login_data = {
        'email': 'test@example.com',
        'password': 'testpassword'
    }
    login_response = session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=False)
    print(f"   Login status: {login_response.status_code}")
    
    if login_response.status_code != 302 or '/dashboard' not in login_response.headers.get('Location', ''):
        print("   ERROR: Login failed")
        return False
    
    print("   SUCCESS: Login successful")
    
    # 2. Access dashboard
    print("2. Accessing dashboard...")
    dashboard_response = session.get(f"{BASE_URL}/dashboard")
    print(f"   Dashboard status: {dashboard_response.status_code}")
    
    if dashboard_response.status_code != 200:
        print("   ERROR: Could not access dashboard")
        return False
    
    print("   SUCCESS: Dashboard accessible")
    
    # 3. Start service
    print("3. Starting service...")
    start_service_response = session.post(f"{BASE_URL}/start_service", allow_redirects=False)
    print(f"   Start service status: {start_service_response.status_code}")
    print(f"   Content-Type: {start_service_response.headers.get('Content-Type')}")
    
    if start_service_response.status_code != 200:
        print("   ERROR: Start service failed")
        return False
    
    if 'image/png' not in start_service_response.headers.get('Content-Type', ''):
        print("   ERROR: Response is not a PNG image")
        return False
    
    print("   SUCCESS: Service started and QR code generated")
    print(f"   QR code size: {len(start_service_response.content)} bytes")
    
    # 4. Verify we can still access dashboard
    print("4. Verifying dashboard still accessible after starting service...")
    dashboard_after_service = session.get(f"{BASE_URL}/dashboard")
    print(f"   Dashboard status: {dashboard_after_service.status_code}")
    
    if dashboard_after_service.status_code != 200:
        print("   ERROR: Could not access dashboard after starting service")
        return False
    
    print("   SUCCESS: Dashboard still accessible")
    return True

if __name__ == "__main__":
    success = test_full_flow()
    if success:
        print("\n[PASS] Full functionality test passed!")
    else:
        print("\n[FAIL] Full functionality test failed!")