// Helper invoked by test_js_parity.py.
// Imports processImage from web/algorithm.js (pure ESM, no DOM),
// reads raw RGBA from `<tmpdir>/in.rgba` + meta.json, writes
// `<tmpdir>/js.rgba` and js_meta.json.
//
// algorithm.js is DOM-free, so this runner needs no globalThis shims —
// only ImageData, which we polyfill since it's a browser global.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

globalThis.ImageData = class {
  constructor(data, width, height) {
    this.data = data;
    this.width = width;
    this.height = height;
  }
};

const { processImage } = await import(
  path.join(__dirname, '..', 'web', 'algorithm.js')
);

const tmpDir = process.argv[2];
if (!tmpDir) {
  console.error('usage: node js_parity_runner.mjs <tmpdir>');
  process.exit(2);
}

const meta = JSON.parse(fs.readFileSync(path.join(tmpDir, 'meta.json'), 'utf8'));
const buf = fs.readFileSync(path.join(tmpDir, 'in.rgba'));
const data = new Uint8ClampedArray(buf.buffer, buf.byteOffset, buf.byteLength);

const result = processImage(new ImageData(data, meta.w, meta.h), {
  targetColor: meta.target_color,
  targetColors: meta.target_colors,
  tolerance: meta.tolerance,
  feather: meta.feather,
  decontaminate: meta.decontaminate,
  edgeErosion: meta.edge_erosion,
  autoTrim: meta.auto_trim || false,
  trimPadding: meta.trim_padding || 0,
});

fs.writeFileSync(path.join(tmpDir, 'js.rgba'), Buffer.from(result.data.buffer));
fs.writeFileSync(
  path.join(tmpDir, 'js_meta.json'),
  JSON.stringify({ w: result.width, h: result.height }),
);
