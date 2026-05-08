from app import app

with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['user'] = 'test-user'
        sess['email'] = 'test@example.com'

    # Test a member card page (using a fake member ID)
    rv = client.get('/api/members/test-id/card')
    print('Member card page status:', rv.status_code)
    if rv.status_code != 200:
        print(rv.data[:300])

    # Test error page
    rv2 = client.get('/nonexistent')
    print('Check 404?')
