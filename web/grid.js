// Grid split mode — slice a sprite sheet into N×M cells or fixed cells.
// Mirrors grid_split.py: integer division, clip the trailing row/col,
// 0-indexed filename pattern padded to max(rows, cols) digits.
import { state } from './state.js';
import { $, setStatus } from './dom.js';
import { sanitizeStem } from './util.js';
import { buildZip } from './zip.js';

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

export function drawGridPreview() {
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

export function updateGridControlsAvailability() {
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

export function clearGridResults() {
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

export function initGrid() {
  // Grid sub-mode (rows×cols vs cell W×H)
  document.querySelectorAll('input[name="gridMode"]').forEach((el) => {
    el.addEventListener('change', () => {
      if (el.checked) state.gridSubMode = el.value;
      updateGridControlsAvailability();
      drawGridPreview();
    });
  });

  // Grid number inputs — input fires while typing, change fires on blur.
  // We handle both because we want live preview AND clamping on blur.
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

  // Disabled until image loaded
  updateGridControlsAvailability();
}
