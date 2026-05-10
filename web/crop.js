// Crop mode — independent from chroma/grid: own private state, own canvas,
// own download path. Mouse/touch drag with 8-handle resize.
import { $, setCropStatus } from './dom.js';
import { sanitizeStem } from './util.js';

const CROP_HANDLE_DISPLAY_PX = 10;
const CROP_HANDLE_HIT_PX = 16;
const CROP_LINE_DISPLAY_PX = 2;

const HANDLE_CURSOR = {
  nw: 'nwse-resize', se: 'nwse-resize',
  ne: 'nesw-resize', sw: 'nesw-resize',
  n: 'ns-resize',    s: 'ns-resize',
  e: 'ew-resize',    w: 'ew-resize',
};

export const cropState = {
  image: null,
  filename: null,
  box: { x: 0, y: 0, w: 0, h: 0 },
  hasBox: false,
  drag: null,
  resultBlob: null,
  resultURL: null,
};

function updateCropCoords() {
  if (!cropState.hasBox) {
    $('cropCoords').textContent = 'x: 0, y: 0, w: 0, h: 0';
    return;
  }
  const b = cropState.box;
  $('cropCoords').textContent =
    `x: ${Math.round(b.x)}, y: ${Math.round(b.y)}, w: ${Math.round(b.w)}, h: ${Math.round(b.h)}`;
}

export function loadCropFile(file) {
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

export function drawCropCanvas() {
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

export function initCrop() {
  $('cropFileInput').addEventListener('change', (e) => {
    const file = e.target.files && e.target.files[0];
    if (file) loadCropFile(file);
  });

  const canvas = $('cropCanvas');
  canvas.addEventListener('pointerdown', (e) => {
    if (e.pointerId !== undefined && canvas.setPointerCapture) {
      try { canvas.setPointerCapture(e.pointerId); } catch (_) {}
    }
    startCropDrag(e);
  });
  canvas.addEventListener('pointermove', moveCropDrag);
  canvas.addEventListener('pointerup', (e) => {
    endCropDrag(e);
    if (e.pointerId !== undefined && canvas.releasePointerCapture) {
      try { canvas.releasePointerCapture(e.pointerId); } catch (_) {}
    }
  });
  canvas.addEventListener('pointercancel', endCropDrag);
  canvas.addEventListener('pointerleave', endCropDrag);

  $('cropApplyBtn').addEventListener('click', applyCrop);
  $('cropDownloadBtn').addEventListener('click', downloadCrop);

  $('cropEmptyHint').style.display = '';
  $('cropResultHint').style.display = '';
  $('cropApplyBtn').disabled = true;
  $('cropDownloadBtn').disabled = true;
  updateCropCoords();
  setCropStatus('이미지를 선택하세요');
}
