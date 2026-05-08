import re

test = "<div class=\"sidebar-item\" onclick=\"location.href='{{ url_for('dashboard') }}'\">"
pattern = re.compile(r'onclick="location\.href=\'\{\{ url_for\(\'([^\']+)\'\) \}\}\"'')
m = pattern.search(test)
print("Match:", m)
if m:
    print("Group:", m.group(1))
    def repl(m):
        endpoint = m.group(1)
        return f'data-href="{{{{ url_for(\'{endpoint}\') }}}}"'
    result = pattern.sub(repl, test)
    print("Result:", result)
