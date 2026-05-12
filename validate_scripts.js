const fs = require('fs');
const html = fs.readFileSync('templates/dashboard.html', 'utf8');
const lines = html.split('\n');

// Find all <script> tags without src, and their closing tags
let scripts = [];
let inScript = false;
let startLine = -1;
for (let i = 0; i < lines.length; i++) {
  const line = lines[i];
  if (!inScript && line.includes('<script') && !line.includes('src=')) {
    inScript = true;
    startLine = i;
  } else if (inScript && line.includes('</script>')) {
    scripts.push({ start: startLine, end: i });
    inScript = false;
  }
}
console.log('Inline script blocks:');
scripts.forEach((s, idx) => {
  console.log(`Script ${idx+1}: lines ${s.start+1} to ${s.end+1} (content lines ${s.start+2} to ${s.end})`);
});

// Validate each
scripts.forEach((s, idx) => {
  const content = lines.slice(s.start+1, s.end).join('\n');
  try {
    new Function(content);
    console.log(`Script ${idx+1}: syntax OK`);
  } catch (e) {
    console.log(`Script ${idx+1} error: ${e.message} at line ${e.lineNumber || '?'}`);
  }
});
