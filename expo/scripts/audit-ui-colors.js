const fs = require('fs');
const path = require('path');

const ROOT = process.cwd();
const ROOTS = ['src', 'app'];
const SOURCE_FILE_PATTERN = /\.(ts|tsx|js|jsx)$/;
const TOKEN_FILE = path.join('src', 'theme', 'tokens.ts');
const DISALLOWED_PATTERNS = [
  { name: 'hex', regex: /#[0-9A-Fa-f]{3,8}/g },
  { name: 'rgba', regex: /rgba?\(/g },
  { name: 'hsla', regex: /hsla?\(/g },
];

function walk(dir, files) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(fullPath, files);
      continue;
    }
    if (SOURCE_FILE_PATTERN.test(entry.name)) {
      files.push(fullPath);
    }
  }
}

function relative(filePath) {
  return path.relative(ROOT, filePath).replace(/\\/g, '/');
}

const files = [];
for (const root of ROOTS) {
  const fullRoot = path.join(ROOT, root);
  if (fs.existsSync(fullRoot)) {
    walk(fullRoot, files);
  }
}

const violations = [];

for (const file of files) {
  const rel = relative(file);
  if (rel === TOKEN_FILE.replace(/\\/g, '/')) {
    continue;
  }

  const source = fs.readFileSync(file, 'utf8');
  for (const pattern of DISALLOWED_PATTERNS) {
    const matches = source.match(pattern.regex);
    if (matches && matches.length > 0) {
      violations.push({
        file: rel,
        pattern: pattern.name,
        sample: matches[0],
      });
      break;
    }
  }
}

if (violations.length > 0) {
  console.error('Found disallowed UI color literals outside src/theme/tokens.ts:');
  for (const violation of violations) {
    console.error(`- ${violation.file} (${violation.pattern}: ${violation.sample})`);
  }
  process.exit(1);
}

console.log('UI color audit passed.');
