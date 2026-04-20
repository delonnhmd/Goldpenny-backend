const fs = require('fs');
const path = require('path');

const root = process.cwd();

const scopedDirs = [
  'src/features/gameplayLoop',
  'src/components/layout',
  'src/components/ui',
];

const scopedFiles = [
  'src/components/gameMap/GameMap.tsx',
  'src/components/gameMap/MapDetailSheet.tsx',
  'src/components/gameMap/PlayerStatusBar.tsx',
  'src/components/gameMap/StressHealthBars.tsx',
  'src/components/gameplay/ActionHubPanel.tsx',
  'src/components/gameplay/ActionCard.tsx',
  'src/components/gameplay/ActionPreviewModal.tsx',
  'src/components/gameplay/BusinessOperationsCard.tsx',
  'src/components/gameplay/DailyBriefCard.tsx',
  'src/components/gameplay/EndOfDaySummaryCard.tsx',
  'src/components/gameplay/MarketOverviewCard.tsx',
  'src/components/gameplay/PriceTrendsCard.tsx',
  'src/components/gameplay/StockMarketCard.tsx',
  'src/components/gameplay/ProgressionSummaryCard.tsx',
  'src/lib/economyPresentationFormatters.ts',
  'src/lib/gameplayFormatters.ts',
  'src/lib/commitmentFormatters.ts',
  'src/lib/worldMemoryFormatters.ts',
  'src/lib/onboardingFormatters.ts',
  'src/lib/strategicPlanningFormatters.ts',
];

const allowedFileExt = new Set(['.ts', '.tsx', '.js', '.jsx', '.css']);
const disallowedColorPattern = /#(?:[0-9a-fA-F]{3,8})|rgba?\([^)]*\)/g;

function walkDir(dirPath, results) {
  if (!fs.existsSync(dirPath)) return;
  for (const entry of fs.readdirSync(dirPath, { withFileTypes: true })) {
    const absolute = path.join(dirPath, entry.name);
    if (entry.isDirectory()) {
      walkDir(absolute, results);
      continue;
    }
    const ext = path.extname(entry.name);
    if (allowedFileExt.has(ext)) {
      results.push(absolute);
    }
  }
}

function readScopedFiles() {
  const files = [];
  for (const rel of scopedDirs) {
    walkDir(path.join(root, rel), files);
  }
  for (const rel of scopedFiles) {
    const absolute = path.join(root, rel);
    if (fs.existsSync(absolute)) files.push(absolute);
  }
  return Array.from(new Set(files));
}

function auditFile(absolutePath) {
  const content = fs.readFileSync(absolutePath, 'utf8');
  const lines = content.split(/\r?\n/);
  const hits = [];
  lines.forEach((line, index) => {
    const matches = line.match(disallowedColorPattern);
    if (!matches) return;
    matches.forEach((match) => {
      hits.push({
        line: index + 1,
        match,
      });
    });
  });
  return hits;
}

const files = readScopedFiles();
const failures = [];

for (const file of files) {
  const hits = auditFile(file);
  if (!hits.length) continue;
  const rel = path.relative(root, file).replace(/\\/g, '/');
  for (const hit of hits) {
    failures.push(`${rel}:${hit.line} -> ${hit.match}`);
  }
}

if (failures.length > 0) {
  console.error('UI color audit failed. Replace hardcoded hex/rgba with design tokens.');
  failures.forEach((entry) => console.error(entry));
  process.exit(1);
}

console.log(`UI color audit passed for ${files.length} files.`);
