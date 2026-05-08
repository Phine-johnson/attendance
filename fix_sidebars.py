import re, os

templates_dir = 'templates'
exclude = {'sermons.html', 'member_card.html', 'error.html', 'member_cards.html'}

files = [f for f in os.listdir(templates_dir) if f.endswith('.html') and f not in exclude]
pattern = re.compile(r'onclick="location\.href=\'\{\{ url_for\(\'([^\']+)\'\) \}\}\'"')
replacement = r'data-href="{{ url_for('\1') }}"'

for fname in files:
    fpath = os.path.join(templates_dir, fname)
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    new_content = pattern.sub(replacement, content)
    if new_content != content:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Fixed: {fname}")
    else:
        print(f"No change: {fname}")

print(f"Processed {len(files)} files.")
