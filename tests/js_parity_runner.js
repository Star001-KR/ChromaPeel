// Helper invoked by test_js_parity.py.
// Loads web/app.js in node, runs processImage on raw RGBA from
// `<tmpdir>/in.rgba` + meta.json, writes `<tmpdir>/js.rgba`.
const fs = require('fs');
const path = require('path');

// DOM/browser shims that satisfy the import-time wiring in app.js.
globalThis.ImageData = class {
  constructor(data, width, height) {
    this.data = data;
    this.width = width;
    this.height = height;
  }
};
globalThis.document = {
  addEventListener() {},
  getElementById() {
    return { addEventListener() {}, classList: { toggle() {} } };
  },
  createElement() {
    return { appendChild() {}, click() {}, remove() {} };
  },
  body: { addEventListener() {} },
};
globalThis.window = globalThis;
globalThis.URL = { createObjectURL: () => '', revokeObjectURL: () => {} };
globalThis.performance = { now: () => 0 };
globalThis.requestAnimationFrame = (cb) => cb();
globalThis.navigator = {};

const tmpDir = process.argv[2];
if (!tmpDir) {
  console.error('usage: node js_parity_runner.js <tmpdir>');
  process.exit(2);
}

const appJs = path.join(__dirname, '..', 'web', 'app.js');
eval(fs.readFileSync(appJs, 'utf8'));

const meta = JSON.parse(fs.readFileSync(path.join(tmpDir, 'meta.json'), 'utf8'));
const buf = fs.readFileSync(path.join(tmpDir, 'in.rgba'));
const data = new Uint8ClampedArray(buf.buffer, buf.byteOffset, buf.byteLength);

const result = processImage(new ImageData(data, meta.w, meta.h), {
  targetColor: meta.target_color,
  tolerance: meta.tolerance,
  feather: meta.feather,
  decontaminate: meta.decontaminate,
  edgeErosion: meta.edge_erosion,
});

fs.writeFileSync(path.join(tmpDir, 'js.rgba'), Buffer.from(result.data.buffer));
