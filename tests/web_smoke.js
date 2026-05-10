// Web boot smoke test: load web/index.html in headless Chromium and assert
// no pageerror events and no console.error messages fire during init.
// Catches runtime regressions (e.g. ReferenceError) that `node --check` cannot.

const { chromium } = require('playwright');
const path = require('path');
const { startServer } = require('./_web_server');

const WEB_DIR = path.resolve(__dirname, '..', 'web');
const SETTLE_MS = 500;

(async () => {
  const server = await startServer(WEB_DIR);
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  const errors = [];
  page.on('pageerror', (err) => {
    errors.push(`pageerror: ${err.message}`);
  });
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      errors.push(`console.error: ${msg.text()}`);
    }
  });

  await page.goto(server.url, { waitUntil: 'load' });
  await page.waitForTimeout(SETTLE_MS);

  await browser.close();
  await server.close();

  if (errors.length > 0) {
    console.error('Web boot smoke test FAILED:');
    for (const e of errors) console.error('  - ' + e);
    process.exit(1);
  }
  console.log('Web boot smoke test PASSED (0 pageerror, 0 console.error).');
})().catch((err) => {
  console.error('Smoke test crashed:', err);
  process.exit(1);
});
