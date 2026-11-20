const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { isolatedHtml, stripRemoteFonts } = require('./isolated-resources.cjs');
test('isolated HTML excludes inherited telemetry and fonts without changing source template', () => {
  const file = path.join(__dirname, '../public/index.html');
  const source = fs.readFileSync(file, 'utf8');
  const result = isolatedHtml(source);
  assert.doesNotMatch(result, /posthog\.init|fonts\.googleapis\.com|fonts\.gstatic\.com/);
  assert.match(result, /id="root"/);
  assert.match(result, /PerformanceServerTiming/);
  assert.equal(fs.readFileSync(file, 'utf8'), source);
  assert.match(source, /posthog\.init/);
});
test('isolated CSS excludes remote font import and retains original rules', async () => {
  const source = fs.readFileSync(path.join(__dirname, '../src/index.css'), 'utf8');
  const result = {css: stripRemoteFonts(source)};
  assert.doesNotMatch(result.css, /fonts\.googleapis\.com/);
  assert.match(result.css, /font-family: "Manrope"/);
  assert.match(result.css, /@tailwind base/);
  const local = fs.readFileSync(path.join(__dirname, '../src/offline-fonts.css'), 'utf8');
  const assets = [...local.matchAll(/url\('([^']+)'\)/g)];
  assert.equal(assets.length, 11);
  for (const [, asset] of assets) assert.ok(fs.statSync(require.resolve(asset)).size > 0);
});
