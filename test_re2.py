import re

test = "<div class=\"sidebar-item\" onclick=\"location.href='{{ url_for('dashboard') }}'\">"
# Pattern: onclick="location.href='{{ url_for('xxx') }}'"
# We want to capture 'xxx'
pattern = re.compile(r"onclick=\"location\.href='\{\{ url_for\('([^']+)'\) \}\}'\"")

m = pattern.search(test)
if m:
    print("Match found")
    def repl(match):
        endpoint = match.group(1)
        return f'data-href="{{{{ url_for(\'{endpoint}\') }}}}"'
    result = pattern.sub(repl, test)
    print("Result:", result)
else:
    print("No match")
