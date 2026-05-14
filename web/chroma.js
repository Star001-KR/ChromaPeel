// Chroma-key removal mode — file load, parameter wire-up, debounced
// reprocess pipeline, save/share. Cross-mode call: loadFile primes both
// chroma and grid views since the source image is shared via state.
import { state } from './state.js';
import { $, setStatus } from './dom.js';
import { detectBackgroundColors, processImage } from './algorithm.js';
import { sanitizeStem } from './util.js';
import {
  drawGridPreview,
  clearGridResults,
  updateGridControlsAvailability,
} from './grid.js';

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

function renderColorRows() {
  const container = $('colorsContainer');
  container.innerHTML = '';
  const colors = state.targetColors;
  colors.forEach((rgb, idx) => {
    const chip = document.createElement('div');
    chip.className = 'color-chip';
    const picker = document.createElement('input');
    picker.type = 'color';
    picker.value = rgbToHex(rgb);
    picker.dataset.idx = String(idx);
    picker.addEventListener('input', (e) => {
      state.targetColors[idx] = hexToRgb(e.target.value);
      // 라벨만 in-place 갱신해 reflow 최소화
      label.textContent = `(${state.targetColors[idx].join(', ')})`;
      schedule();
    });
    chip.appendChild(picker);
    const label = document.createElement('span');
    label.className = 'color-label muted';
    label.textContent = `(${rgb.join(', ')})`;
    chip.appendChild(label);
    if (colors.length > 1) {
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'color-remove ghost';
      remove.setAttribute('aria-label', '색상 제거');
      remove.textContent = '✕';
      remove.addEventListener('click', () => {
        state.targetColors.splice(idx, 1);
        renderColorRows();
        schedule();
      });
      chip.appendChild(remove);
    }
    container.appendChild(chip);
  });
}

// 자동 감지 ON 직전의 수동 선택 색상. OFF 토글 시 복원해 사용자가
// 직접 고른 색이 자동 감지 결과로 영구 손실되지 않도록 한다.
let savedManualColors = null;

function syncAutoDetectUI() {
  const auto = state.autoDetect;
  $('colorsContainer').classList.toggle('disabled', auto);
  $('addColorBtn').disabled = auto;
  if (auto) {
    if (savedManualColors === null) {
      savedManualColors = state.targetColors.map((c) => [...c]);
    }
    if (state.sourceImageData) {
      state.targetColors = detectBackgroundColors(state.sourceImageData);
      renderColorRows();
    }
  } else if (savedManualColors !== null) {
    state.targetColors = savedManualColors;
    savedManualColors = null;
    renderColorRows();
  }
}

// ---------- File loading ----------

// Above ~16MP, mobile Safari often refuses to allocate the canvas
// or returns blank data, and processing a copy + erosion buffers
// would cost ~250MB+. Reject with a clear message instead of OOMing.
const MAX_PIXELS = 16 * 1024 * 1024;

let loadToken = 0;

export function loadFile(file) {
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

export function schedule() {
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
      targetColors: state.targetColors,
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

// ---------- Wire-up ----------

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

export function initChroma() {
  $('fileInput').addEventListener('change', (e) => {
    const file = e.target.files && e.target.files[0];
    if (file) loadFile(file);
  });

  // Drag-drop on the page (page-wide, since the canvas wrap is small)
  const dropZone = document.body;
  dropZone.addEventListener('dragover', (e) => { e.preventDefault(); });
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (file) loadFile(file);
  });

  $('addColorBtn').addEventListener('click', () => {
    if (state.autoDetect) return;
    const seed = state.targetColors.length
      ? state.targetColors[state.targetColors.length - 1]
      : [255, 37, 255];
    state.targetColors.push([...seed]);
    renderColorRows();
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
    state.targetColors = [[255, 37, 255]];
    state.autoTrim = false;
    state.trimPadding = 0;
    savedManualColors = null;
    $('tolerance').value = 20; $('toleranceVal').textContent = '20';
    $('feather').value = 100; $('featherVal').textContent = '100';
    $('edgeErosion').value = 1; $('edgeErosionVal').textContent = '1';
    $('decontaminate').checked = true;
    $('autoDetect').checked = false;
    $('autoTrim').checked = false;
    $('trimPadding').value = 0; $('trimPaddingVal').textContent = '0';
    renderColorRows();
    syncAutoDetectUI();
    schedule();
    setStatus('기본값으로 복원');
  });

  $('saveBtn').addEventListener('click', saveOrShare);

  renderColorRows();
  setStatus('PNG / JPG / WebP 이미지를 선택하거나 드래그하세요');
}
