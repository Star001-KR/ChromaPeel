// Web golden-path e2e tests: drives the actual UI flows that the boot smoke
// test cannot — file injection, drag interaction, mode switching, downloads.
//
// Catches regressions like: drag not firing, download button stuck disabled,
// state bleed when switching tabs after work in another tab.
//
// Local run:
//   npm install --no-save playwright@1.48.0
//   npx playwright install chromium
//   node tests/web_e2e.js
//
// PNG fixtures are generated at runtime via Canvas API inside page.evaluate,
// so no binary files are committed.

const { chromium } = require('playwright');
const path = require('path');
const { pathToFileURL } = require('url');

const INDEX_PATH = path.resolve(__dirname, '..', 'web', 'index.html');
const URL_STR = pathToFileURL(INDEX_PATH).toString();

// ---------- Test runner ----------

const tests = [];
function test(name, fn) { tests.push({ name, fn }); }

async function run() {
  const browser = await chromium.launch();
  let failed = 0;
  for (const t of tests) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
    page.on('console', (m) => { if (m.type() === 'error') errors.push(`console.error: ${m.text()}`); });
    try {
      await page.goto(URL_STR, { waitUntil: 'load' });
      await page.waitForFunction(() => !!document.getElementById('fileInput'));
      await t.fn(page);
      // autoTrim console.warn fires by design when image goes fully transparent;
      // but we never trigger that path. Treat any console.error as failure.
      if (errors.length) throw new Error('Unexpected console errors:\n  - ' + errors.join('\n  - '));
      console.log(`  ✓ ${t.name}`);
    } catch (e) {
      failed++;
      console.error(`  ✗ ${t.name}\n    ${e.stack || e.message || e}`);
    } finally {
      await ctx.close();
    }
  }
  await browser.close();
  if (failed > 0) {
    console.error(`\nWeb e2e FAILED: ${failed}/${tests.length} test(s) failed`);
    process.exit(1);
  }
  console.log(`\nWeb e2e PASSED: ${tests.length}/${tests.length} test(s) passed`);
}

// ---------- Fixture injection ----------

// Draws a w×h PNG inside the page (chroma key border around a solid inner box),
// then injects it into a file <input> via DataTransfer + change event.
// `chroma`/`fill` are CSS color strings. `inner` is [x, y, w, h] inside the canvas.
async function injectFixture(page, inputSelector, opts) {
  const { w, h, chroma, fill, inner, filename } = opts;
  await page.evaluate(async ({ selector, w, h, chroma, fill, inner, filename }) => {
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = chroma;
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = fill;
    ctx.fillRect(inner[0], inner[1], inner[2], inner[3]);
    const blob = await new Promise((r) => canvas.toBlob(r, 'image/png'));
    const file = new File([blob], filename, { type: 'image/png' });
    const dt = new DataTransfer();
    dt.items.add(file);
    const input = document.querySelector(selector);
    input.files = dt.files;
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }, { selector: inputSelector, w, h, chroma, fill, inner, filename });
}

// ---------- Helpers ----------

async function canvasNonEmpty(page, canvasSelector) {
  return page.evaluate((sel) => {
    const c = document.querySelector(sel);
    if (!c || c.width === 0 || c.height === 0) return false;
    const ctx = c.getContext('2d');
    const { data } = ctx.getImageData(0, 0, c.width, c.height);
    for (let i = 3; i < data.length; i += 4) if (data[i] !== 0) return true;
    return false;
  }, canvasSelector);
}

async function canvasSize(page, canvasSelector) {
  return page.evaluate((sel) => {
    const c = document.querySelector(sel);
    return { w: c.width, h: c.height };
  }, canvasSelector);
}

async function clickMode(page, btnId) {
  await page.click('#' + btnId);
}

// ---------- Scenarios ----------

// Auto-trim is the chroma mode with autoTrim checkbox: chroma key fills the
// border, the inner box survives. After processing+trim, the result canvas
// should match the inner box size exactly (default tolerance 20 covers
// 0xff25ff exactly, padding=0).
test('auto-trim: chroma + autoTrim crops to inner box', async (page) => {
  // Default mode is chroma.
  await injectFixture(page, '#fileInput', {
    w: 32, h: 32,
    chroma: 'rgb(255,37,255)',
    fill: 'rgb(0,200,0)',
    inner: [8, 8, 16, 16],
    filename: 'autotrim-fixture.png',
  });
  await page.waitForFunction(() => {
    const c = document.getElementById('sourceCanvas');
    return c && c.width === 32 && c.height === 32;
  });

  // edgeErosion default is 1, which shrinks the surviving alpha mask by 1px
  // on each side; zero it out so the trimmed result matches the inner box exactly.
  await page.fill('#edgeErosion', '0');
  await page.dispatchEvent('#edgeErosion', 'input');

  // Enable autoTrim, then wait for processing to settle (saveBtn re-enables).
  await page.check('#autoTrim');
  await page.waitForFunction(() => !document.getElementById('saveBtn').disabled, null, { timeout: 5000 });

  const size = await canvasSize(page, '#resultCanvas');
  if (size.w !== 16 || size.h !== 16) {
    throw new Error(`expected trimmed result 16×16, got ${size.w}×${size.h}`);
  }
  if (!(await canvasNonEmpty(page, '#resultCanvas'))) {
    throw new Error('result canvas is fully transparent after trim');
  }
});

// Grid split: 32×32 image, 4×4 grid → exactly 16 cell thumbnails + ZIP enabled.
test('grid-split: 4×4 produces 16 cells, ZIP enabled', async (page) => {
  await injectFixture(page, '#fileInput', {
    w: 32, h: 32,
    chroma: 'rgb(50,50,200)',
    fill: 'rgb(220,220,80)',
    inner: [4, 4, 24, 24],
    filename: 'grid-fixture.png',
  });
  await page.waitForFunction(() => {
    const c = document.getElementById('sourceCanvas');
    return c && c.width === 32;
  });

  await clickMode(page, 'modeGridBtn');
  await page.waitForFunction(() => document.body.classList.contains('mode-grid'));

  // Set rows × cols = 4 × 4. The rowsCols radio is the default.
  await page.fill('#gridRows', '4');
  await page.fill('#gridCols', '4');
  // Trigger change event explicitly (fill dispatches input but blur clamping
  // also runs on change; either way splitBtn must be enabled).
  await page.dispatchEvent('#gridRows', 'change');
  await page.dispatchEvent('#gridCols', 'change');

  await page.waitForFunction(() => !document.getElementById('splitBtn').disabled);
  await page.click('#splitBtn');

  await page.waitForFunction(
    () => document.getElementById('gridResultsContainer').children.length === 16,
    null,
    { timeout: 10000 },
  );
  const zipDisabled = await page.evaluate(() => document.getElementById('gridDownloadZipBtn').disabled);
  if (zipDisabled) throw new Error('gridDownloadZipBtn still disabled after split');

  const countText = await page.textContent('#gridResultCount');
  if (!/16/.test(countText)) {
    throw new Error(`gridResultCount text missing "16": ${JSON.stringify(countText)}`);
  }
});

// Manual crop: switch to crop mode, inject a separate fixture, drag a box
// across the canvas, apply, verify result canvas + download enabled.
test('manual-crop: drag selection → apply → result+download', async (page) => {
  await clickMode(page, 'modeCropBtn');
  await page.waitForFunction(() => document.body.classList.contains('mode-crop'));

  await injectFixture(page, '#cropFileInput', {
    w: 64, h: 64,  // a bit larger so the canvas has room to drag inside
    chroma: 'rgb(30,30,30)',
    fill: 'rgb(255,180,40)',
    inner: [16, 16, 32, 32],
    filename: 'crop-fixture.png',
  });
  await page.waitForFunction(() => {
    const c = document.getElementById('cropCanvas');
    return c && c.width === 64 && c.height === 64;
  });

  // Get bounding rect of the displayed canvas and drag from ~20% to ~80%.
  const rect = await page.evaluate(() => {
    const r = document.getElementById('cropCanvas').getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height };
  });
  if (rect.w < 4 || rect.h < 4) {
    throw new Error(`cropCanvas too small to drag: ${rect.w}×${rect.h}`);
  }
  const x1 = rect.x + rect.w * 0.2;
  const y1 = rect.y + rect.h * 0.2;
  const x2 = rect.x + rect.w * 0.8;
  const y2 = rect.y + rect.h * 0.8;

  await page.mouse.move(x1, y1);
  await page.mouse.down();
  // Move in a few steps so pointermove fires during the drag.
  await page.mouse.move((x1 + x2) / 2, (y1 + y2) / 2, { steps: 5 });
  await page.mouse.move(x2, y2, { steps: 5 });
  await page.mouse.up();

  await page.waitForFunction(() => !document.getElementById('cropApplyBtn').disabled, null, { timeout: 5000 });
  await page.click('#cropApplyBtn');
  await page.waitForFunction(() => !document.getElementById('cropDownloadBtn').disabled, null, { timeout: 5000 });

  const size = await canvasSize(page, '#cropResultCanvas');
  if (size.w < 1 || size.h < 1) {
    throw new Error(`cropResultCanvas empty: ${size.w}×${size.h}`);
  }
  if (!(await canvasNonEmpty(page, '#cropResultCanvas'))) {
    throw new Error('cropResultCanvas has no opaque pixels');
  }
});

// Cross-tab regression: do work in chroma, switch to grid (which shares
// sourceImageData), switch back, ensure each mode still produces output.
// Catches partial-state bugs where mode-switch broke the other tab's wiring.
test('cross-tab: chroma → grid → chroma stays functional', async (page) => {
  await injectFixture(page, '#fileInput', {
    w: 32, h: 32,
    chroma: 'rgb(255,37,255)',
    fill: 'rgb(0,150,255)',
    inner: [8, 8, 16, 16],
    filename: 'cross-fixture.png',
  });
  // Initial chroma processing.
  await page.waitForFunction(() => !document.getElementById('saveBtn').disabled, null, { timeout: 5000 });

  // Switch to grid; the previously-loaded image must populate grid preview.
  await clickMode(page, 'modeGridBtn');
  await page.waitForFunction(() => !document.getElementById('splitBtn').disabled);
  await page.fill('#gridRows', '2');
  await page.fill('#gridCols', '2');
  await page.dispatchEvent('#gridRows', 'change');
  await page.dispatchEvent('#gridCols', 'change');
  await page.click('#splitBtn');
  await page.waitForFunction(
    () => document.getElementById('gridResultsContainer').children.length === 4,
    null,
    { timeout: 10000 },
  );

  // Switch back to chroma; toggle a param and confirm reprocessing happens.
  await clickMode(page, 'modeChromaBtn');
  await page.waitForFunction(() => document.body.classList.contains('mode-chroma'));
  // Force a reprocess by toggling tolerance — saveBtn should re-enable.
  await page.evaluate(() => {
    const t = document.getElementById('tolerance');
    t.value = '40';
    t.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await page.waitForFunction(() => !document.getElementById('saveBtn').disabled, null, { timeout: 5000 });
  if (!(await canvasNonEmpty(page, '#resultCanvas'))) {
    throw new Error('resultCanvas empty after returning to chroma mode');
  }
});

run().catch((err) => {
  console.error('e2e harness crashed:', err);
  process.exit(1);
});
