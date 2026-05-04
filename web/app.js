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

// Above ~16MP, mobile Safari often refuses to allocate the canvas
// or returns blank data, and processing a copy + erosion buffers
// would cost ~250MB+. Reject with a clear message instead of OOMing.
const MAX_PIXELS = 16 * 1024 * 1024;

let loadToken = 0;

function loadFile(file) {
  if (!file) return;
  const token = ++loadToken;
  state.sourceFilename = file.name || 'image.png';
  const stem = state.sourceFilename.replace(/\.[^./\\]+$/, '') || 'image';
  $('filenameInput').value = `${stem}_alpha`;
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => {
    URL.revokeObjectURL(url);
    if (token !== loadToken) return; // a newer load superseded this one

    const w = img.naturalWidth, h = img.naturalHeight;
    if (w * h > MAX_PIXELS) {
      const mp = (w * h / (1024 * 1024)).toFixed(1);
      setStatus(`이미지가 너무 큽니다 (${w}×${h}, ${mp}MP). 16MP 이하로 줄여 주세요.`);
      return;
    }

    let imageData;
    try {
      const canvas = document.createElement('canvas');
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0);
      imageData = ctx.getImageData(0, 0, w, h);
    } catch (e) {
      setStatus(`이미지 로드 실패 (${w}×${h}): ${e.message || e}`);
      return;
    }
    state.sourceImageData = imageData;

    drawSourcePreview();
    if (state.autoDetect) syncAutoDetectUI();
    state.processedBlob = null;
    $('saveBtn').disabled = true;
    schedule();
    $('emptyHint').style.display = 'none';
    setStatus(`${w}×${h} 로드됨`);
  };
  img.onerror = () => {
    URL.revokeObjectURL(url);
    if (token !== loadToken) return;
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
let dirty = false;

function schedule() {
  if (!state.sourceImageData) return;
  if (processing) {
    // Param changed mid-flight; runProcess will reschedule itself once done.
    dirty = true;
    return;
  }
  if (scheduleTimer !== null) clearTimeout(scheduleTimer);
  scheduleTimer = setTimeout(runProcess, 80);
}

function runProcess() {
  scheduleTimer = null;
  if (!state.sourceImageData || processing) return;
  processing = true;
  dirty = false;
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
      $('saveBtn').disabled = !blob;
      processing = false;
      const dt = Math.round(performance.now() - t0);
      setStatus(`처리 완료 (${dt}ms)`);
      if (dirty) {
        dirty = false;
        schedule();
      }
    }, 'image/png');
  });
}

// ---------- Save / Share ----------

function sanitizeStem(s) {
  // strip path separators and characters illegal in Windows filenames
  return s.replace(/[/\\:*?"<>|\x00-\x1f]/g, '').replace(/\.+$/, '').trim();
}

function outputFilename() {
  const raw = ($('filenameInput').value || '').trim();
  if (raw) {
    const stem = sanitizeStem(raw.replace(/\.png$/i, ''));
    if (stem) return `${stem}.png`;
  }
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

// ---------- Crop mode ----------
// Independent from chroma mode: own state, own canvas, own download.

const CROP_HANDLE_DISPLAY_PX = 10;
const CROP_HANDLE_HIT_PX = 16;
const CROP_LINE_DISPLAY_PX = 2;

const HANDLE_CURSOR = {
  nw: 'nwse-resize', se: 'nwse-resize',
  ne: 'nesw-resize', sw: 'nesw-resize',
  n: 'ns-resize',    s: 'ns-resize',
  e: 'ew-resize',    w: 'ew-resize',
};

const cropState = {
  image: null,
  filename: null,
  box: { x: 0, y: 0, w: 0, h: 0 },
  hasBox: false,
  drag: null,
  resultBlob: null,
  resultURL: null,
};

function setCropStatus(text) {
  $('cropStatus').textContent = text;
}

function updateCropCoords() {
  if (!cropState.hasBox) {
    $('cropCoords').textContent = 'x: 0, y: 0, w: 0, h: 0';
    return;
  }
  const b = cropState.box;
  $('cropCoords').textContent =
    `x: ${Math.round(b.x)}, y: ${Math.round(b.y)}, w: ${Math.round(b.w)}, h: ${Math.round(b.h)}`;
}

function loadCropFile(file) {
  if (!file) return;
  cropState.filename = file.name || 'image.png';
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => {
    URL.revokeObjectURL(url);
    cropState.image = img;
    cropState.box = { x: 0, y: 0, w: 0, h: 0 };
    cropState.hasBox = false;
    cropState.drag = null;

    const canvas = $('cropCanvas');
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    drawCropCanvas();

    $('cropEmptyHint').style.display = 'none';
    $('cropApplyBtn').disabled = true;
    $('cropDownloadBtn').disabled = true;
    if (cropState.resultURL) {
      URL.revokeObjectURL(cropState.resultURL);
      cropState.resultURL = null;
    }
    cropState.resultBlob = null;
    const resultCanvas = $('cropResultCanvas');
    resultCanvas.width = 0;
    resultCanvas.height = 0;
    $('cropResultHint').style.display = '';

    updateCropCoords();
    setCropStatus(`${img.naturalWidth}×${img.naturalHeight} 로드됨 — 드래그로 영역을 선택하세요`);
  };
  img.onerror = () => {
    URL.revokeObjectURL(url);
    setCropStatus('이미지를 열 수 없습니다');
  };
  img.src = url;
}

// Display→image scale (canvas pixels per CSS pixel).
// Large because mobile may render the canvas smaller than image px.
function getCropDisplayScale() {
  const canvas = $('cropCanvas');
  const rect = canvas.getBoundingClientRect();
  if (rect.width === 0) return 1;
  return canvas.width / rect.width;
}

function computeHandlePositions(box) {
  const { x, y, w, h } = box;
  return [
    { name: 'nw', cx: x,         cy: y         },
    { name: 'n',  cx: x + w / 2, cy: y         },
    { name: 'ne', cx: x + w,     cy: y         },
    { name: 'e',  cx: x + w,     cy: y + h / 2 },
    { name: 'se', cx: x + w,     cy: y + h     },
    { name: 's',  cx: x + w / 2, cy: y + h     },
    { name: 'sw', cx: x,         cy: y + h     },
    { name: 'w',  cx: x,         cy: y + h / 2 },
  ];
}

function drawCropCanvas() {
  const canvas = $('cropCanvas');
  const ctx = canvas.getContext('2d');
  const img = cropState.image;
  if (!img) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0);
  if (!cropState.hasBox) return;

  const b = cropState.box;
  const scale = getCropDisplayScale();
  const lineW = Math.max(1, CROP_LINE_DISPLAY_PX * scale);
  const handleSize = CROP_HANDLE_DISPLAY_PX * scale;
  const dash = 6 * scale;

  // Box outline: black halo + white dashed for contrast on any background
  ctx.lineWidth = lineW;
  ctx.setLineDash([]);
  ctx.strokeStyle = 'rgba(0,0,0,0.7)';
  ctx.strokeRect(b.x, b.y, b.w, b.h);
  ctx.setLineDash([dash, dash]);
  ctx.strokeStyle = '#fff';
  ctx.strokeRect(b.x, b.y, b.w, b.h);
  ctx.setLineDash([]);

  // Handles
  ctx.lineWidth = Math.max(1, scale);
  for (const h of computeHandlePositions(b)) {
    const hx = h.cx - handleSize / 2;
    const hy = h.cy - handleSize / 2;
    ctx.fillStyle = '#fff';
    ctx.fillRect(hx, hy, handleSize, handleSize);
    ctx.strokeStyle = '#000';
    ctx.strokeRect(hx, hy, handleSize, handleSize);
  }
}

function eventToImageCoord(e) {
  const canvas = $('cropCanvas');
  const rect = canvas.getBoundingClientRect();
  const point = (e.touches && e.touches[0])
              || (e.changedTouches && e.changedTouches[0])
              || e;
  const cx = point.clientX - rect.left;
  const cy = point.clientY - rect.top;
  const sx = canvas.width / (rect.width || 1);
  const sy = canvas.height / (rect.height || 1);
  return { x: cx * sx, y: cy * sy };
}

function hitTestCropBox(p) {
  if (!cropState.hasBox) return null;
  const scale = getCropDisplayScale();
  const hit = CROP_HANDLE_HIT_PX * scale;
  const half = hit / 2;
  for (const h of computeHandlePositions(cropState.box)) {
    if (Math.abs(p.x - h.cx) <= half && Math.abs(p.y - h.cy) <= half) {
      return { kind: 'resize', handle: h.name };
    }
  }
  const b = cropState.box;
  const x1 = Math.min(b.x, b.x + b.w);
  const x2 = Math.max(b.x, b.x + b.w);
  const y1 = Math.min(b.y, b.y + b.h);
  const y2 = Math.max(b.y, b.y + b.h);
  if (p.x >= x1 && p.x <= x2 && p.y >= y1 && p.y <= y2) {
    return { kind: 'move' };
  }
  return null;
}

function setCropCursor(hit) {
  const canvas = $('cropCanvas');
  if (!hit) canvas.style.cursor = 'crosshair';
  else if (hit.kind === 'resize') canvas.style.cursor = HANDLE_CURSOR[hit.handle] || 'default';
  else canvas.style.cursor = 'move';
}

function normalizeBox(box) {
  let { x, y, w, h } = box;
  if (w < 0) { x += w; w = -w; }
  if (h < 0) { y += h; h = -h; }
  return { x, y, w, h };
}

function clampBoxToImage(box) {
  const img = cropState.image;
  if (!img) return box;
  const W = img.naturalWidth, H = img.naturalHeight;
  let { x, y, w, h } = normalizeBox(box);
  if (x < 0) { w += x; x = 0; }
  if (y < 0) { h += y; y = 0; }
  if (x + w > W) w = W - x;
  if (y + h > H) h = H - y;
  if (w < 0) w = 0;
  if (h < 0) h = 0;
  return { x, y, w, h };
}

function startCropDrag(e) {
  if (!cropState.image) return;
  e.preventDefault();
  const p = eventToImageCoord(e);
  const hit = hitTestCropBox(p);
  if (hit) {
    cropState.drag = {
      kind: hit.kind,
      handle: hit.handle,
      startX: p.x,
      startY: p.y,
      startBox: { ...cropState.box },
    };
  } else {
    cropState.box = { x: p.x, y: p.y, w: 0, h: 0 };
    cropState.hasBox = true;
    cropState.drag = {
      kind: 'create',
      startX: p.x,
      startY: p.y,
      startBox: { ...cropState.box },
    };
    drawCropCanvas();
    updateCropCoords();
  }
  setCropCursor(hit || { kind: 'move' });
}

function resizeBox(sb, handle, dx, dy) {
  let { x, y, w, h } = sb;
  switch (handle) {
    case 'nw': x += dx; y += dy; w -= dx; h -= dy; break;
    case 'n':           y += dy;          h -= dy; break;
    case 'ne':          y += dy; w += dx; h -= dy; break;
    case 'e':                    w += dx;          break;
    case 'se':                   w += dx; h += dy; break;
    case 's':                             h += dy; break;
    case 'sw': x += dx;          w -= dx; h += dy; break;
    case 'w':  x += dx;          w -= dx;          break;
  }
  return { x, y, w, h };
}

function moveCropDrag(e) {
  const drag = cropState.drag;
  if (!drag) return;
  e.preventDefault();
  const p = eventToImageCoord(e);
  const dx = p.x - drag.startX;
  const dy = p.y - drag.startY;
  const sb = drag.startBox;

  if (drag.kind === 'create') {
    cropState.box = { x: sb.x, y: sb.y, w: dx, h: dy };
  } else if (drag.kind === 'move') {
    cropState.box = { x: sb.x + dx, y: sb.y + dy, w: sb.w, h: sb.h };
  } else if (drag.kind === 'resize') {
    cropState.box = resizeBox(sb, drag.handle, dx, dy);
  }
  drawCropCanvas();
  updateCropCoords();
}

function endCropDrag(e) {
  if (!cropState.drag) return;
  if (e && e.preventDefault) e.preventDefault();
  cropState.drag = null;

  const clamped = clampBoxToImage(cropState.box);
  cropState.box = clamped;
  if (clamped.w < 1 || clamped.h < 1) {
    cropState.hasBox = false;
  }
  drawCropCanvas();
  updateCropCoords();
  $('cropApplyBtn').disabled = !cropState.hasBox;
}

function applyCrop() {
  if (!cropState.hasBox || !cropState.image) return;
  const img = cropState.image;
  let x = Math.max(0, Math.round(cropState.box.x));
  let y = Math.max(0, Math.round(cropState.box.y));
  let w = Math.round(cropState.box.w);
  let h = Math.round(cropState.box.h);
  if (x + w > img.naturalWidth) w = img.naturalWidth - x;
  if (y + h > img.naturalHeight) h = img.naturalHeight - y;
  if (w <= 0 || h <= 0) {
    alert('잘라낼 영역이 너무 작습니다');
    return;
  }

  const resultCanvas = $('cropResultCanvas');
  resultCanvas.width = w;
  resultCanvas.height = h;
  const ctx = resultCanvas.getContext('2d');
  ctx.clearRect(0, 0, w, h);
  ctx.drawImage(img, x, y, w, h, 0, 0, w, h);
  $('cropResultHint').style.display = 'none';

  resultCanvas.toBlob((blob) => {
    if (cropState.resultURL) URL.revokeObjectURL(cropState.resultURL);
    cropState.resultBlob = blob;
    cropState.resultURL = blob ? URL.createObjectURL(blob) : null;
    $('cropDownloadBtn').disabled = !blob;
    setCropStatus(blob ? `잘라내기 완료 (${w}×${h})` : '잘라내기 실패');
  }, 'image/png');
}

function downloadCrop() {
  if (!cropState.resultBlob || !cropState.resultURL) return;
  const raw = (cropState.filename || 'image').replace(/\.[^./\\]+$/, '') || 'image';
  const stem = sanitizeStem(raw) || 'image';
  const filename = `${stem}_crop.png`;
  const a = document.createElement('a');
  a.href = cropState.resultURL;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setCropStatus(`다운로드: ${filename}`);
}

function setMode(mode) {
  document.querySelectorAll('.mode-pane').forEach((pane) => {
    pane.hidden = pane.dataset.mode !== mode;
  });
}

function initCrop() {
  $('cropFileInput').addEventListener('change', (e) => {
    const file = e.target.files && e.target.files[0];
    if (file) loadCropFile(file);
  });

  const canvas = $('cropCanvas');

  // Mouse: down on canvas, move/up on window so drags don't get lost off-canvas
  canvas.addEventListener('mousedown', startCropDrag);
  canvas.addEventListener('mousemove', (e) => {
    if (cropState.drag || !cropState.image) return;
    setCropCursor(hitTestCropBox(eventToImageCoord(e)));
  });
  window.addEventListener('mousemove', (e) => {
    if (cropState.drag) moveCropDrag(e);
  });
  window.addEventListener('mouseup', (e) => {
    if (cropState.drag) endCropDrag(e);
  });

  // Touch: explicit non-passive so preventDefault stops page scroll/pinch
  canvas.addEventListener('touchstart', startCropDrag, { passive: false });
  canvas.addEventListener('touchmove',  moveCropDrag,  { passive: false });
  canvas.addEventListener('touchend',   endCropDrag,   { passive: false });
  canvas.addEventListener('touchcancel', endCropDrag,  { passive: false });

  $('cropApplyBtn').addEventListener('click', applyCrop);
  $('cropDownloadBtn').addEventListener('click', downloadCrop);

  // Display size may change with viewport; redraw so handles/lines stay sized correctly.
  window.addEventListener('resize', () => {
    if (cropState.image) drawCropCanvas();
  });

  setCropStatus('이미지를 선택하면 영역을 드래그할 수 있습니다');
}

function initModeSwitch() {
  document.querySelectorAll('input[name="mode"]').forEach((radio) => {
    radio.addEventListener('change', (e) => {
      if (e.target.checked) setMode(e.target.value);
    });
  });
  setMode('chroma');
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

  initCrop();
  initModeSwitch();
}

document.addEventListener('DOMContentLoaded', init);
