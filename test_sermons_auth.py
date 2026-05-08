from app import app

with app.test_client() as client:
    # Simulate login by setting session
    with client.session_transaction() as sess:
        sess['user'] = 'test-user'
        sess['email'] = 'test@example.com'
    
    rv = client.get('/sermons')
    print('Status:', rv.status_code)
    if rv.status_code != 200:
        print('Error body:')
        print(rv.data[:1000])
    else:
        print('Success - length:', len(rv.data))
