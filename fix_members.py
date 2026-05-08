import re

with open('templates/members.html', 'r', encoding='utf-8') as f:
    content = f.read()

pattern = re.compile(r"onclick=\"location\.href='\{\{ url_for\('([^']+)'\) \}\}'\"")

def repl(m):
    endpoint = m.group(1)
    return f'data-href="{{{{ url_for(\'{endpoint}\') }}}}"'

new_content = pattern.sub(repl, content)

if new_content != content:
    print("Content changed")
    with open('templates/members.html', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("File updated")
else:
    print("No change")
