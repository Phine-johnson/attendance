from app import app

with app.test_client() as client:
    rv = client.get('/sermons')
    print('Status:', rv.status_code)
    if rv.status_code != 200:
        print('Error body:')
        print(rv.data[:500])
