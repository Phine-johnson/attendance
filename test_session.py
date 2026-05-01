# Simple test to verify session handling
from flask import Flask, session, redirect, url_for, request, render_template_string
import os

app = Flask(__name__)
app.secret_key = 'test-secret-key-for-debugging'

@app.route('/set')
def set_session():
    session['test'] = 'value'
    return f"Session set: {dict(session)}"

@app.route('/get')
def get_session():
    return f"Session contents: {dict(session)}"

@app.route('/')
def index():
    return '''
    <h1>Session Test</h1>
    <p><a href="/set">Set session variable</a></p>
    <p><a href="/get">Get session contents</a></p>
    '''

if __name__ == '__main__':
    app.run(debug=True, port=5001)