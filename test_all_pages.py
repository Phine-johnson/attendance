from app import app

with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['user'] = 'test-user'
        sess['email'] = 'test@example.com'

    endpoints = [
        '/',
        '/dashboard',
        '/members',
        '/attendance',
        '/events',
        '/groups',
        '/donations',
        '/sermons',
        '/communications',
        '/member-cards',
        '/volunteers',
        '/resources',
        '/bible',
        '/notes',
        '/search',
        '/service-update',
        '/highlights',
        '/bookmarks',
        '/history',
    ]

    for path in endpoints:
        rv = client.get(path)
        if rv.status_code != 200:
            print(f"{path} -> {rv.status_code}")
            print(rv.data[:300])
        else:
            print(f"{path} -> OK")
