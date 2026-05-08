import re, os

templates_dir = 'templates'
exclude = {'sermons.html', 'member_card.html', 'error.html', 'member_cards.html'}

files = [f for f in os.listdir(templates_dir) if f.endswith('.html') and f not in exclude]
count = 0
for fname in files:
    fpath = os.path.join(templates_dir, fname)
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    # Match: onclick="location.href='{{ url_for('xxx') }}'"
    # We want to replace with: data-href="{{ url_for('xxx') }}"
    new_content = re.sub(
        r'onclick="location\.href=\'\{\{ url_for\(\'([^\']+)\'\) \}\}\'"',
        r'data-href="{{ url_for('\1') }}"',
        content
    )
    if new_content != content:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Fixed: {fname}")
        count += 1
    else:
        print(f"No change: {fname}")

print(f"\nTotal modified: {count}")
