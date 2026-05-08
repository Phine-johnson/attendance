#!/usr/bin/env python
"""Test script for attendance system features."""
import requests
import json
from datetime import date

BASE_URL = "http://localhost:5000"
API_KEY = "AIzaSyAl4pSD5u6m8dIoHQGV6v14ifJ98mJMG6U"

def firebase_auth(email, password):
    """Login via Firebase Auth REST API to get ID token."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    resp = requests.post(url, json=payload)
    if resp.status_code == 200:
        return resp.json()['idToken']
    else:
        print(f"Firebase Auth failed: {resp.text}")
        return None

def flask_login(session, email, password):
    """Login via Flask login form."""
    resp = session.post(f"{BASE_URL}/login", data={
        'email': email,
        'password': password
    }, allow_redirects=False)
    print("Login status:", resp.status_code)
    print("Login body snippet:", resp.text[:300])
    # Check if it's a redirect (302) on success
    if resp.status_code in [301, 302]:
        # Follow redirect
        follow = session.get(f"{BASE_URL}{resp.headers.get('Location', '/dashboard')}")
        print("After redirect status:", follow.status_code)
        return follow.status_code == 200
    # If 200, check if it's the login page again (failed) or dashboard
    return 'Dashboard' in resp.text or 'Welcome' in resp.text

def create_member(session, member_data):
    resp = session.post(f"{BASE_URL}/api/members", json=member_data)
    print(f"Create member: {resp.status_code} - {resp.text[:200]}")
    return resp.json() if resp.ok else None

def admin_scan(session, qr_data):
    resp = session.post(f"{BASE_URL}/api/scan-member", json={"qr_data": qr_data})
    print(f"Admin scan: {resp.status_code} - {resp.text[:200]}")
    return resp.json() if resp.ok else None

def get_attendance(session, start_date, end_date):
    resp = session.get(f"{BASE_URL}/api/attendance/records?start={start_date}&end={end_date}")
    return resp.json() if resp.ok else None

def delete_member(session, member_id):
    resp = session.delete(f"{BASE_URL}/api/members/{member_id}")
    print(f"Delete member: {resp.status_code} - {resp.text[:200]}")
    return resp.json() if resp.ok else None

def get_trash(session):
    resp = session.get(f"{BASE_URL}/api/trash")
    return resp.json() if resp.ok else None

def restore_trash(session, item_id):
    resp = session.post(f"{BASE_URL}/api/trash/restore/{item_id}")
    print(f"Restore trash: {resp.status_code} - {resp.text[:200]}")
    return resp.json() if resp.ok else None

def test_password_reset():
    resp = requests.post(f"{BASE_URL}/api/auth/reset-password", json={"email": "admin@example.com"})
    print(f"Password reset: {resp.status_code} - {resp.text[:200]}")
    return resp.ok

def main():
    print("=" * 60)
    print("CHURCH ATTENDANCE SYSTEM - TEST SUITE")
    print("=" * 60)

    session = requests.Session()

    # Step 1: Login as admin
    print("\n[1] Logging in as admin...")
    if not flask_login(session, "admin@example.com", "AdminPass123!"):
        print("ERROR: Flask login failed")
        return
    print("OK: Logged in successfully")

    # Verify session works by hitting a protected endpoint
    me_resp = session.get(f"{BASE_URL}/api/stats")
    print("Session check - /api/stats:", me_resp.status_code, me_resp.text[:150])

    # Step 2: Create a test member
    print("\n[2] Creating test member...")
    member_data = {
        "memberId": "TEST001",
        "firstName": "Test",
        "lastName": "Member",
        "email": "test.member@example.com",
        "phone": "555-123-4567",
        "status": "active"
    }
    member_resp = create_member(session, member_data)
    if not member_resp or 'member_id' not in member_resp:
        print("ERROR: Could not create member")
        return
    member_id = member_resp['member_id']
    print("OK: Created member: " + member_id)

    # Step 3: Start service (QR generation - visual check)
    print("\n[3] Starting service (QR code)...")
    qr_resp = session.post(f"{BASE_URL}/start_service", json={})
    if qr_resp.ok and 'svg' in qr_resp.text:
        print("OK: Service started, QR SVG generated")
    else:
        print("Note: Start service returned: " + str(qr_resp.status_code))

    # Step 4: Admin scan (simulate admin scanning member ID card)
    print("\n[4] Testing admin scan...")
    members_resp = session.get(f"{BASE_URL}/api/members")
    if members_resp.ok:
        members_list = members_resp.json().get('members', [])
        test_member = next((m for m in members_list if m.get('member_id') == member_id), None)
        if test_member:
            member_key = test_member['id']
            qr_data = {"member_id": member_id, "type": "member_card"}
            admin_result = admin_scan(session, qr_data)
            if admin_result and admin_result.get('success'):
                print("OK: Admin scan recorded attendance for member key: " + member_key)
            else:
                print("ERROR: Admin scan failed: " + str(admin_result))
        else:
            print("ERROR: Could not find test member")
    else:
        print("ERROR: Could not fetch members list")

    # Step 5: Verify attendance record
    print("\n[5] Verifying attendance record...")
    today = date.today().isoformat()
    attendance = get_attendance(session, today, today)
    if attendance and 'records' in attendance:
        records = attendance['records']
        print("OK: Found " + str(len(records)) + " attendance record(s) for today")
        for rec in records:
            print("  - Date: " + rec.get('date') + " | Member: " + rec.get('member_id') + " | Mode: " + rec.get('mode', 'N/A'))
    else:
        print("No attendance records found (or error)")

    # Step 6: Test delete and trash
    print("\n[6] Testing delete → trash...")
    delete_resp = delete_member(session, member_id)
    if delete_resp and delete_resp.get('success'):
        print("OK: Member deleted (moved to trash)")
    else:
        print("ERROR: Delete failed: " + str(delete_resp))

    print("\n[7] Checking trash...")
    trash = get_trash(session)
    if trash and 'trash' in trash:
        items = trash['trash']
        print("OK: Trash contains " + str(len(items)) + " item(s)")
        if items:
            item = items[0]
            print("  Item type: " + item.get('type'))
            print("  Original ID: " + item.get('original_id'))
            item_id = item['id']
            restore_resp = restore_trash(session, item_id)
            if restore_resp.get('success'):
                print("OK: Item restored from trash")
            else:
                print("ERROR: Restore failed: " + str(restore_resp))
    else:
        print("ERROR: Could not fetch trash")

    # Step 8: Test password reset
    print("\n[8] Testing password reset endpoint...")
    if test_password_reset():
        print("OK: Password reset email sent")
    else:
        print("ERROR: Password reset failed")

    print("\n============================================================")
    print("ALL TESTS COMPLETED")
    print("============================================================")

if __name__ == "__main__":
    main()
