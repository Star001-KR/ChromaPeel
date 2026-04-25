// ChromaPeel — web version
// Port of imageAlpha.py: 자동 배경 감지 + L∞ 거리 + Feather + Decontamination + Edge Erosion

const $ = (id) => document.getElementById(id);

const state = {
  sourceImageData: null,
  sourceFilename: null,
  processedBlob: null,
  processedURL: null,
  // params
  autoDetect: false,
  targetColor: [255, 37, 255],
  tolerance: 20,
  feather: 100,
  decontaminate: true,
  edgeErosion: 1,
};

// ---------- Algorithm ----------

function detectBackgroundColor(imageData) {
  const { data, width, height } = imageData;
  const counts = new Map();
  const tally = (idx) => {
    const key = (data[idx] << 16) | (data[idx + 1] << 8) | data[idx + 2];
    counts.set(key, (counts.get(key) || 0) + 1);
  };
  for (let x = 0; x < width; x++) {
    tally((0 * width + x) * 4);
    tally(((height - 1) * width + x) * 4);
  }
  for (let y = 0; y < height; y++) {
    tally((y * width + 0) * 4);
    tally((y * width + (width - 1)) * 4);
  }
  let bestKey = 0, bestCount = -1;
  for (const [k, c] of counts) {
    if (c > bestCount) { bestCount = c; bestKey = k; }
  }
  return [(bestKey >> 16) & 0xff, (bestKey >> 8) & 0xff, bestKey & 0xff];
}

function clampToInt(v) {
  // Match Python's np.clip(...).astype(np.uint8) — clamp then truncate.
  // Uint8ClampedArray would otherwise round to nearest even, off by 1 from Python.
  if (v < 0) return 0;
  if (v > 255) return 255;
  return v | 0;
}

function processImage(srcImageData, params) {
  const { width, height } = srcImageData;
  const src = srcImageData.data;
  const out = new Uint8ClampedArray(src);
  const [tr, tg, tb] = params.targetColor;
  const tol = params.tolerance;
  const feather = params.feather;
  const decon = params.decontaminate;
  const erosion = params.edgeErosion;
  const n = width * height;

  const alphaMul = new Float32Array(n);

  for (let i = 0; i < n; i++) {
    const o = i * 4;
    const r = src[o], g = src[o + 1], b = src[o + 2];
    const dr = r > tr ? r - tr : tr - r;
    const dg = g > tg ? g - tg : tg - g;
    const db = b > tb ? b - tb : tb - b;
    const dist = dr > dg ? (dr > db ? dr : db) : (dg > db ? dg : db);

    let m = 1.0;
    if (dist <= tol) {
      m = 0.0;
    } else if (feather > 0 && dist <= tol + feather) {
      m = (dist - tol) / feather;
      if (decon) {
        const t = 1.0 - m;
        const denom = 1.0 - t < 1e-6 ? 1e-6 : 1.0 - t;
        out[o]     = clampToInt((r - t * tr) / denom);
        out[o + 1] = clampToInt((g - t * tg) / denom);
        out[o + 2] = clampToInt((b - t * tb) / denom);
      }
    }
    alphaMul[i] = m;
  }

  for (let i = 0; i < n; i++) {
    out[i * 4 + 3] = (src[i * 4 + 3] * alphaMul[i]) | 0;
  }

  if (erosion > 0) {
    let cur = new Uint8ClampedArray(n);
    let nxt = new Uint8ClampedArray(n);
    for (let i = 0; i < n; i++) cur[i] = out[i * 4 + 3];
    const w = width, h = height;
    for (let pass = 0; pass < erosion; pass++) {
      for (let y = 0; y < h; y++) {
        const yUp = y === 0 ? 0 : y - 1;
        const yDn = y === h - 1 ? h - 1 : y + 1;
        for (let x = 0; x < w; x++) {
          const xL = x === 0 ? 0 : x - 1;
          const xR = x === w - 1 ? w - 1 : x + 1;
          let mn = cur[yUp * w + xL];
          let v;
          v = cur[yUp * w + x];  if (v < mn) mn = v;
          v = cur[yUp * w + xR]; if (v < mn) mn = v;
          v = cur[y   * w + xL]; if (v < mn) mn = v;
          v = cur[y   * w + x];  if (v < mn) mn = v;
          v = cur[y   * w + xR]; if (v < mn) mn = v;
          v = cur[yDn * w + xL]; if (v < mn) mn = v;
          v = cur[yDn * w + x];  if (v < mn) mn = v;
          v = cur[yDn * w + xR]; if (v < mn) mn = v;
          nxt[y * w + x] = mn;
        }
      }
      const tmp = cur; cur = nxt; nxt = tmp;
    }
    for (let i = 0; i < n; i++) out[i * 4 + 3] = cur[i];
  }

  return new ImageData(out, width, height);
}

// ---------- UI helpers ----------

function rgbToHex([r, g, b]) {
  const h = (v) => v.toString(16).padStart(2, '0');
  return `#${h(r)}${h(g)}${h(b)}`;
}

function hexToRgb(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return [0, 0, 0];
  const v = parseInt(m[1], 16);
  return [(v >> 16) & 0xff, (v >> 8) & 0xff, v & 0xff];
}

function setStatus(text) {
  $('status').textContent = text;
}

function setColorUI(rgb) {
  state.targetColor = rgb;
  $('colorPicker').value = rgbToHex(rgb);
  $('colorLabel').textContent = `(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
}

function syncAutoDetectUI() {
  const auto = state.autoDetect;
  $('colorPicker').disabled = auto;
  $('colorLabel').classList.toggle('muted', auto);
  if (auto && state.sourceImageData) {
    const detected = detectBackgroundColor(state.sourceImageData);
    setColorUI(detected);
    $('colorLabel').textContent = `(${detected[0]}, ${detected[1]}, ${detected[2]}) — 자동`;
  }
}

// ---------- File loading ----------

function loadFile(file) {
  if (!file) return;
  state.sourceFilename = file.name || 'image.png';
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => {
    URL.revokeObjectURL(url);
    const canvas = document.createElement('canvas');
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0);
    state.sourceImageData = ctx.getImageData(0, 0, canvas.width, canvas.height);

    drawSourcePreview();
    if (state.autoDetect) syncAutoDetectUI();
    schedule();
    $('saveBtn').disabled = false;
    $('emptyHint').style.display = 'none';
    setStatus(`${img.naturalWidth}×${img.naturalHeight} 로드됨`);
  };
  img.onerror = () => {
    URL.revokeObjectURL(url);
    setStatus('이미지를 열 수 없습니다');
  };
  img.src = url;
}

function drawSourcePreview() {
  const canvas = $('sourceCanvas');
  const data = state.sourceImageData;
  canvas.width = data.width;
  canvas.height = data.height;
  canvas.getContext('2d').putImageData(data, 0, 0);
}

// ---------- Processing pipeline ----------

let scheduleTimer = null;
let processing = false;

function schedule() {
  if (!state.sourceImageData) return;
  if (scheduleTimer !== null) clearTimeout(scheduleTimer);
  scheduleTimer = setTimeout(runProcess, 80);
}

function runProcess() {
  scheduleTimer = null;
  if (!state.sourceImageData || processing) return;
  processing = true;
  setStatus('처리 중...');

  // Yield to the UI before heavy work
  requestAnimationFrame(() => {
    const t0 = performance.now();
    const result = processImage(state.sourceImageData, {
      targetColor: state.targetColor,
      tolerance: state.tolerance,
      feather: state.feather,
      decontaminate: state.decontaminate,
      edgeErosion: state.edgeErosion,
    });

    const canvas = $('resultCanvas');
    canvas.width = result.width;
    canvas.height = result.height;
    canvas.getContext('2d').putImageData(result, 0, 0);

    canvas.toBlob((blob) => {
      if (state.processedURL) URL.revokeObjectURL(state.processedURL);
      state.processedBlob = blob;
      state.processedURL = blob ? URL.createObjectURL(blob) : null;
      processing = false;
      const dt = Math.round(performance.now() - t0);
      setStatus(`처리 완료 (${dt}ms)`);
    }, 'image/png');
  });
}

// ---------- Save / Share ----------

function outputFilename() {
  const name = state.sourceFilename || 'image.png';
  const dot = name.lastIndexOf('.');
  const stem = dot > 0 ? name.slice(0, dot) : name;
  return `${stem}_alpha.png`;
}

async function saveOrShare() {
  if (!state.processedBlob) return;
  const filename = outputFilename();
  const file = new File([state.processedBlob], filename, { type: 'image/png' });

  if (navigator.canShare && navigator.canShare({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: 'ChromaPeel' });
      setStatus(`공유됨: ${filename}`);
      return;
    } catch (e) {
      if (e.name === 'AbortError') return;
      // fall through to download
    }
  }
  const a = document.createElement('a');
  a.href = state.processedURL;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setStatus(`다운로드: ${filename}`);
}

// ---------- Wire up controls ----------

function bindRange(rangeId, valueId, key, parser) {
  const range = $(rangeId);
  const valueLabel = $(valueId);
  const update = () => {
    const v = parser(range.value);
    state[key] = v;
    valueLabel.textContent = String(v);
    schedule();
  };
  range.addEventListener('input', update);
  update();
}

function init() {
  $('fileInput').addEventListener('change', (e) => {
    const file = e.target.files && e.target.files[0];
    if (file) loadFile(file);
  });

  // Drag-drop on the page
  const dropZone = document.body;
  dropZone.addEventListener('dragover', (e) => { e.preventDefault(); });
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (file) loadFile(file);
  });

  $('colorPicker').addEventListener('input', (e) => {
    setColorUI(hexToRgb(e.target.value));
    schedule();
  });

  $('autoDetect').addEventListener('change', (e) => {
    state.autoDetect = e.target.checked;
    syncAutoDetectUI();
    schedule();
  });

  $('decontaminate').addEventListener('change', (e) => {
    state.decontaminate = e.target.checked;
    schedule();
  });

  bindRange('tolerance', 'toleranceVal', 'tolerance', (v) => parseInt(v, 10));
  bindRange('feather', 'featherVal', 'feather', (v) => parseInt(v, 10));
  bindRange('edgeErosion', 'edgeErosionVal', 'edgeErosion', (v) => parseInt(v, 10));

  $('resetBtn').addEventListener('click', () => {
    state.tolerance = 20;
    state.feather = 100;
    state.decontaminate = true;
    state.edgeErosion = 1;
    state.autoDetect = false;
    state.targetColor = [255, 37, 255];
    $('tolerance').value = 20; $('toleranceVal').textContent = '20';
    $('feather').value = 100; $('featherVal').textContent = '100';
    $('edgeErosion').value = 1; $('edgeErosionVal').textContent = '1';
    $('decontaminate').checked = true;
    $('autoDetect').checked = false;
    setColorUI([255, 37, 255]);
    syncAutoDetectUI();
    schedule();
    setStatus('기본값으로 복원');
  });

  $('saveBtn').addEventListener('click', saveOrShare);

  setColorUI(state.targetColor);
  setStatus('PNG / JPG / WebP 이미지를 선택하거나 드래그하세요');
}

document.addEventListener('DOMContentLoaded', init);
