import re

with open('templates/members.html', 'r', encoding='utf-8') as f:
    content = f.read()

pattern = re.compile(r"onclick=\"location\.href='\{\{ url_for\('([^']+)'\) \}\}'\"")

matches = pattern.findall(content)
print("Found", len(matches), "matches")
if matches:
    print("First few:", matches[:5])
