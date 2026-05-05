// ChromaPeel — web version
// 1) 크로마 제거 (imageAlpha.py 포팅): 자동 배경 감지 + L∞ 거리 + Feather + Decontamination + Edge Erosion
// 2) 격자 분할 (grid_split.py 포팅): rows×cols / cell W×H 두 모드, 잔여 픽셀 clip, ZIP 일괄 다운로드
// 의존성: 외부 라이브러리 없음 (vanilla JS, Store-mode ZIP 자체 구현)

const $ = (id) => document.getElementById(id);

const state = {
  mode: 'chroma',  // 'chroma' | 'grid' | 'crop'
  sourceImageData: null,
  sourceFilename: null,
  processedBlob: null,
  processedURL: null,
  // chroma params
  autoDetect: false,
  targetColor: [255, 37, 255],
  tolerance: 20,
  feather: 100,
  decontaminate: true,
  edgeErosion: 1,
  autoTrim: false,
  trimPadding: 0,
  // grid params
  gridSubMode: 'rowsCols',  // 'rowsCols' | 'cellWH'
  gridRows: 2,
  gridCols: 2,
  gridCellW: 64,
  gridCellH: 64,
  gridResults: [],          // [{name, blob, url, row, col}]
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

  let result = new ImageData(out, width, height);

  if (params.autoTrim) {
    const trimmed = trimTransparentEdges(
      result,
      params.trimAlphaThreshold || 0,
      params.trimPadding || 0,
    );
    if (trimmed === null) {
      // Match Python: skip with warning, keep original
      console.warn('자동 트림 스킵: 모든 픽셀이 투명입니다');
    } else {
      result = trimmed;
    }
  }

  return result;
}

function trimTransparentEdges(imageData, alphaThreshold, padding) {
  const { data, width, height } = imageData;
  let top = -1, bottom = -1, left = width, right = -1;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const a = data[(y * width + x) * 4 + 3];
      if (a > alphaThreshold) {
        if (top === -1) top = y;
        bottom = y;
        if (x < left) left = x;
        if (x > right) right = x;
      }
    }
  }
  if (top === -1) return null;

  // Match PIL.Image.crop: right/bottom are exclusive.
  let l = left, t = top, r = right + 1, b = bottom + 1;
  if (padding > 0) {
    l = Math.max(0, l - padding);
    t = Math.max(0, t - padding);
    r = Math.min(width, r + padding);
    b = Math.min(height, b + padding);
  }
  const newW = r - l, newH = b - t;
  const out = new Uint8ClampedArray(newW * newH * 4);
  for (let y = 0; y < newH; y++) {
    const srcRow = ((t + y) * width + l) * 4;
    const dstRow = y * newW * 4;
    out.set(data.subarray(srcRow, srcRow + newW * 4), dstRow);
  }
  return new ImageData(out, newW, newH);
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

    // Chroma-mode setup (always runs so switching modes after load works)
    drawSourcePreview();
    if (state.autoDetect) syncAutoDetectUI();
    state.processedBlob = null;
    $('saveBtn').disabled = true;
    if (state.mode === 'chroma') schedule();
    $('emptyHint').style.display = 'none';

    // Grid-mode setup
    $('gridEmptyHint').style.display = 'none';
    clearGridResults();
    drawGridPreview();
    updateGridControlsAvailability();

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
      autoTrim: state.autoTrim,
      trimPadding: state.trimPadding,
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

// ---------- Grid split: geometry & filenames ----------

function computeGrid(width, height) {
  let cellW, cellH, rows, cols;
  if (state.gridSubMode === 'rowsCols') {
    rows = state.gridRows | 0;
    cols = state.gridCols | 0;
    if (rows <= 0 || cols <= 0) return { error: 'Rows / Cols는 1 이상이어야 합니다.' };
    if (cols > width || rows > height) {
      return { error: `이미지(${width}×${height})보다 행/열이 많습니다.` };
    }
    cellW = Math.floor(width / cols);
    cellH = Math.floor(height / rows);
  } else {
    cellW = state.gridCellW | 0;
    cellH = state.gridCellH | 0;
    if (cellW <= 0 || cellH <= 0) return { error: 'Cell W / H는 1 이상이어야 합니다.' };
    if (cellW > width || cellH > height) {
      return { error: `셀(${cellW}×${cellH})이 이미지(${width}×${height})보다 큽니다.` };
    }
    rows = Math.floor(height / cellH);
    cols = Math.floor(width / cellW);
  }
  if (cellW <= 0 || cellH <= 0 || rows <= 0 || cols <= 0) {
    return { error: '유효한 격자를 만들 수 없습니다.' };
  }
  const clipW = width - cellW * cols;
  const clipH = height - cellH * rows;
  return { rows, cols, cellW, cellH, clipW, clipH };
}

function formatGridFilename(stem, row, col, maxDim) {
  let pad = 1;
  if (maxDim >= 100) pad = 3;
  else if (maxDim >= 10) pad = 2;
  const r = String(row).padStart(pad, '0');
  const c = String(col).padStart(pad, '0');
  return `${stem}_r${r}c${c}.png`;
}

function gridStem() {
  const name = state.sourceFilename || 'image.png';
  const dot = name.lastIndexOf('.');
  const stem = dot > 0 ? name.slice(0, dot) : name;
  return sanitizeStem(stem) || 'image';
}

// ---------- Grid split: preview ----------

const GRID_PREVIEW_MAX = 720;

function drawGridPreview() {
  const canvas = $('gridPreviewCanvas');
  if (!state.sourceImageData) {
    const ctx = canvas.getContext('2d');
    canvas.width = 0;
    canvas.height = 0;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    updateGridClipInfo(null);
    return;
  }
  const img = state.sourceImageData;
  const W = img.width, H = img.height;
  // Scale preview down if huge (for layout / line crispness)
  const scale = Math.min(1, GRID_PREVIEW_MAX / Math.max(W, H));
  const cw = Math.max(1, Math.round(W * scale));
  const ch = Math.max(1, Math.round(H * scale));
  canvas.width = cw;
  canvas.height = ch;
  const ctx = canvas.getContext('2d');

  // Draw scaled source via temp canvas
  const tmp = document.createElement('canvas');
  tmp.width = W; tmp.height = H;
  tmp.getContext('2d').putImageData(img, 0, 0);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(tmp, 0, 0, W, H, 0, 0, cw, ch);

  const grid = computeGrid(W, H);
  if (grid.error) {
    updateGridClipInfo(grid);
    return;
  }

  const sx = cw / W, sy = ch / H;

  // Grid lines (red, dashed, 1px)
  ctx.save();
  ctx.strokeStyle = '#e63946';
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 3]);
  ctx.beginPath();
  for (let c = 1; c < grid.cols; c++) {
    const x = Math.round(c * grid.cellW * sx) + 0.5;
    ctx.moveTo(x, 0);
    ctx.lineTo(x, ch);
  }
  for (let r = 1; r < grid.rows; r++) {
    const y = Math.round(r * grid.cellH * sy) + 0.5;
    ctx.moveTo(0, y);
    ctx.lineTo(cw, y);
  }
  ctx.stroke();
  // Outer border (solid)
  ctx.setLineDash([]);
  const usedW = grid.cellW * grid.cols;
  const usedH = grid.cellH * grid.rows;
  ctx.strokeRect(0.5, 0.5, Math.round(usedW * sx) - 1, Math.round(usedH * sy) - 1);
  ctx.restore();

  // Clip overlay (grey 50% on right / bottom strip)
  if (grid.clipW > 0 || grid.clipH > 0) {
    ctx.save();
    ctx.fillStyle = 'rgba(80, 80, 80, 0.45)';
    if (grid.clipW > 0) {
      const x = Math.round(usedW * sx);
      ctx.fillRect(x, 0, cw - x, ch);
    }
    if (grid.clipH > 0) {
      const y = Math.round(usedH * sy);
      const wRect = Math.round(usedW * sx);
      ctx.fillRect(0, y, wRect, ch - y);
    }
    ctx.restore();
  }

  updateGridClipInfo(grid);
}

function updateGridClipInfo(grid) {
  const el = $('gridClipInfo');
  el.classList.remove('is-warning', 'is-error');
  if (!state.sourceImageData) {
    el.textContent = '이미지를 선택하세요.';
    return;
  }
  if (!grid || grid.error) {
    el.textContent = grid && grid.error ? grid.error : '격자를 계산할 수 없습니다.';
    el.classList.add('is-error');
    return;
  }
  const total = grid.rows * grid.cols;
  let msg = `${grid.rows} × ${grid.cols} = ${total}장 · 셀 ${grid.cellW}×${grid.cellH}px`;
  if (grid.clipW > 0 || grid.clipH > 0) {
    msg += ` · 마지막 ${grid.clipW}×${grid.clipH}px가 잘려나감`;
    el.classList.add('is-warning');
  } else {
    msg += ' · 정확히 나누어떨어짐';
  }
  el.textContent = msg;
}

function updateGridControlsAvailability() {
  const isRC = state.gridSubMode === 'rowsCols';
  $('gridRows').disabled = !isRC;
  $('gridCols').disabled = !isRC;
  $('gridCellW').disabled = isRC;
  $('gridCellH').disabled = isRC;

  const grid = state.sourceImageData
    ? computeGrid(state.sourceImageData.width, state.sourceImageData.height)
    : null;
  $('splitBtn').disabled = !state.sourceImageData || !grid || !!grid.error;
}

// ---------- Grid split: execute ----------

function clearGridResults() {
  for (const r of state.gridResults) {
    if (r.url) URL.revokeObjectURL(r.url);
  }
  state.gridResults = [];
  $('gridResultsContainer').innerHTML = '';
  $('gridResultCount').textContent = '결과 없음';
  $('gridDownloadZipBtn').disabled = true;
}

async function runGridSplit() {
  if (!state.sourceImageData) return;
  const img = state.sourceImageData;
  const grid = computeGrid(img.width, img.height);
  if (grid.error) {
    setStatus(grid.error);
    return;
  }
  clearGridResults();
  setStatus('격자 분할 중...');

  const { rows, cols, cellW, cellH } = grid;
  const stem = gridStem();
  const maxDim = Math.max(rows, cols);

  const tile = document.createElement('canvas');
  tile.width = cellW;
  tile.height = cellH;
  const tctx = tile.getContext('2d');

  const srcArr = img.data;
  const srcW = img.width;
  const rowBytes = cellW * 4;

  const t0 = performance.now();
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const cellData = tctx.createImageData(cellW, cellH);
      const dst = cellData.data;
      for (let y = 0; y < cellH; y++) {
        const srcOff = ((r * cellH + y) * srcW + c * cellW) * 4;
        dst.set(srcArr.subarray(srcOff, srcOff + rowBytes), y * rowBytes);
      }
      tctx.putImageData(cellData, 0, 0);
      // eslint-disable-next-line no-await-in-loop
      const blob = await new Promise((resolve) =>
        tile.toBlob(resolve, 'image/png')
      );
      if (!blob) continue;
      const url = URL.createObjectURL(blob);
      const name = formatGridFilename(stem, r, c, maxDim);
      state.gridResults.push({ name, blob, url, row: r, col: c });
    }
  }
  renderGridResults();
  const dt = Math.round(performance.now() - t0);
  setStatus(`분할 완료: ${state.gridResults.length}장 (${dt}ms)`);
}

function renderGridResults() {
  const container = $('gridResultsContainer');
  container.innerHTML = '';
  if (state.gridResults.length === 0) {
    $('gridResultCount').textContent = '결과 없음';
    $('gridDownloadZipBtn').disabled = true;
    return;
  }
  const frag = document.createDocumentFragment();
  for (const r of state.gridResults) {
    const wrap = document.createElement('div');
    wrap.className = 'grid-thumb';
    const a = document.createElement('a');
    a.href = r.url;
    a.download = r.name;
    a.title = `${r.name} 다운로드`;
    const img = document.createElement('img');
    img.className = 'thumb-img';
    img.src = r.url;
    img.alt = r.name;
    img.loading = 'lazy';
    const label = document.createElement('div');
    label.className = 'thumb-name';
    label.textContent = r.name;
    a.appendChild(img);
    wrap.appendChild(a);
    wrap.appendChild(label);
    frag.appendChild(wrap);
  }
  container.appendChild(frag);
  $('gridResultCount').textContent = `${state.gridResults.length}장 · 클릭하여 개별 다운로드`;
  $('gridDownloadZipBtn').disabled = false;
}

// ---------- ZIP builder (Store mode, no compression) ----------
// PKZIP APPNOTE: local file header + central directory + EOCD.
// 압축 없이 저장만 함 (PNG는 이미 압축됨). UTF-8 파일명 지원 (GPB flag bit 11).

const CRC32_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let k = 0; k < 8; k++) {
      c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
    }
    t[i] = c >>> 0;
  }
  return t;
})();

function crc32(bytes) {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) {
    c = CRC32_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

async function buildZip(files) {
  const encoder = new TextEncoder();
  const parts = [];
  const central = [];
  let offset = 0;

  for (const f of files) {
    const data = new Uint8Array(await f.blob.arrayBuffer());
    const nameBytes = encoder.encode(f.name);
    const crc = crc32(data);
    const size = data.length;

    const lh = new ArrayBuffer(30 + nameBytes.length);
    const lhV = new DataView(lh);
    lhV.setUint32(0, 0x04034b50, true);
    lhV.setUint16(4, 20, true);          // version needed
    lhV.setUint16(6, 0x0800, true);      // GPB flag: UTF-8 filename
    lhV.setUint16(8, 0, true);           // method: store
    lhV.setUint16(10, 0, true);          // mod time
    lhV.setUint16(12, 0x0021, true);     // mod date (1996-01-01)
    lhV.setUint32(14, crc, true);
    lhV.setUint32(18, size, true);       // compressed size
    lhV.setUint32(22, size, true);       // uncompressed size
    lhV.setUint16(26, nameBytes.length, true);
    lhV.setUint16(28, 0, true);          // extra len
    new Uint8Array(lh, 30).set(nameBytes);

    parts.push(new Uint8Array(lh));
    parts.push(data);

    const ch = new ArrayBuffer(46 + nameBytes.length);
    const chV = new DataView(ch);
    chV.setUint32(0, 0x02014b50, true);
    chV.setUint16(4, 20, true);          // version made by
    chV.setUint16(6, 20, true);          // version needed
    chV.setUint16(8, 0x0800, true);
    chV.setUint16(10, 0, true);
    chV.setUint16(12, 0, true);
    chV.setUint16(14, 0x0021, true);
    chV.setUint32(16, crc, true);
    chV.setUint32(20, size, true);
    chV.setUint32(24, size, true);
    chV.setUint16(28, nameBytes.length, true);
    chV.setUint16(30, 0, true);          // extra
    chV.setUint16(32, 0, true);          // comment
    chV.setUint16(34, 0, true);          // disk number
    chV.setUint16(36, 0, true);          // internal attrs
    chV.setUint32(38, 0, true);          // external attrs
    chV.setUint32(42, offset, true);     // local header offset
    new Uint8Array(ch, 46).set(nameBytes);
    central.push(new Uint8Array(ch));

    offset += 30 + nameBytes.length + size;
  }

  let centralSize = 0;
  for (const c of central) centralSize += c.length;

  const eocd = new ArrayBuffer(22);
  const eV = new DataView(eocd);
  eV.setUint32(0, 0x06054b50, true);
  eV.setUint16(4, 0, true);
  eV.setUint16(6, 0, true);
  eV.setUint16(8, files.length, true);
  eV.setUint16(10, files.length, true);
  eV.setUint32(12, centralSize, true);
  eV.setUint32(16, offset, true);
  eV.setUint16(20, 0, true);

  return new Blob([...parts, ...central, new Uint8Array(eocd)], {
    type: 'application/zip',
  });
}

async function downloadGridZip() {
  if (state.gridResults.length === 0) return;
  setStatus('ZIP 생성 중...');
  const t0 = performance.now();
  const blob = await buildZip(
    state.gridResults.map((r) => ({ name: r.name, blob: r.blob }))
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${gridStem()}_split.zip`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Defer revoke so the browser can start the download
  setTimeout(() => URL.revokeObjectURL(url), 4000);
  const dt = Math.round(performance.now() - t0);
  setStatus(`ZIP 다운로드 (${state.gridResults.length}장, ${dt}ms)`);
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

// ---------- Mode switch ----------

function setMode(mode) {
  if (mode !== 'chroma' && mode !== 'grid' && mode !== 'crop') return;
  state.mode = mode;
  document.body.classList.toggle('mode-chroma', mode === 'chroma');
  document.body.classList.toggle('mode-grid', mode === 'grid');
  document.body.classList.toggle('mode-crop', mode === 'crop');
  $('modeChromaBtn').classList.toggle('is-active', mode === 'chroma');
  $('modeGridBtn').classList.toggle('is-active', mode === 'grid');
  $('modeCropBtn').classList.toggle('is-active', mode === 'crop');
  $('modeChromaBtn').setAttribute('aria-selected', mode === 'chroma' ? 'true' : 'false');
  $('modeGridBtn').setAttribute('aria-selected', mode === 'grid' ? 'true' : 'false');
  $('modeCropBtn').setAttribute('aria-selected', mode === 'crop' ? 'true' : 'false');
  if (mode === 'grid' && state.sourceImageData) {
    drawGridPreview();
    updateGridControlsAvailability();
  }
  if (mode === 'chroma' && state.sourceImageData && !state.processedBlob) {
    schedule();
  }
  if (mode === 'crop' && cropState.image) {
    drawCropCanvas();
  }
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

  $('autoTrim').addEventListener('change', (e) => {
    state.autoTrim = e.target.checked;
    schedule();
  });

  $('trimPadding').addEventListener('input', (e) => {
    const v = parseInt(e.target.value, 10) || 0;
    state.trimPadding = v;
    $('trimPaddingVal').textContent = String(v);
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
    state.autoTrim = false;
    state.trimPadding = 0;
    $('tolerance').value = 20; $('toleranceVal').textContent = '20';
    $('feather').value = 100; $('featherVal').textContent = '100';
    $('edgeErosion').value = 1; $('edgeErosionVal').textContent = '1';
    $('decontaminate').checked = true;
    $('autoDetect').checked = false;
    $('autoTrim').checked = false;
    $('trimPadding').value = 0; $('trimPaddingVal').textContent = '0';
    setColorUI([255, 37, 255]);
    syncAutoDetectUI();
    schedule();
    setStatus('기본값으로 복원');
  });

  $('saveBtn').addEventListener('click', saveOrShare);

  // Mode switch
  $('modeChromaBtn').addEventListener('click', () => setMode('chroma'));
  $('modeGridBtn').addEventListener('click', () => setMode('grid'));
  $('modeCropBtn').addEventListener('click', () => setMode('crop'));

  // Grid sub-mode (rows×cols vs cell W×H)
  document.querySelectorAll('input[name="gridMode"]').forEach((el) => {
    el.addEventListener('change', () => {
      if (el.checked) state.gridSubMode = el.value;
      updateGridControlsAvailability();
      drawGridPreview();
    });
  });

  // Grid number inputs
  const bindGridNum = (id, key, min, max) => {
    const el = $(id);
    const update = () => {
      let v = parseInt(el.value, 10);
      if (!Number.isFinite(v)) v = min;
      if (v < min) v = min;
      if (v > max) v = max;
      state[key] = v;
      drawGridPreview();
      updateGridControlsAvailability();
    };
    el.addEventListener('input', update);
    el.addEventListener('change', () => {
      // Clamp visible value on blur/change
      let v = parseInt(el.value, 10);
      if (!Number.isFinite(v)) v = min;
      if (v < min) v = min;
      if (v > max) v = max;
      el.value = String(v);
      state[key] = v;
      drawGridPreview();
      updateGridControlsAvailability();
    });
  };
  bindGridNum('gridRows', 'gridRows', 1, 999);
  bindGridNum('gridCols', 'gridCols', 1, 999);
  bindGridNum('gridCellW', 'gridCellW', 1, 9999);
  bindGridNum('gridCellH', 'gridCellH', 1, 9999);

  $('splitBtn').addEventListener('click', runGridSplit);
  $('gridDownloadZipBtn').addEventListener('click', downloadGridZip);

  // Initialise grid availability (disabled until image loaded)
  updateGridControlsAvailability();

  setColorUI(state.targetColor);
  setStatus('PNG / JPG / WebP 이미지를 선택하거나 드래그하세요');

  initCrop();
}

document.addEventListener('DOMContentLoaded', init);
