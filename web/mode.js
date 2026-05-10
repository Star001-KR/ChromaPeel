// Mode switch — chroma / grid / crop 탭 전환.
// state.mode 갱신 + body class · 버튼 aria-selected 토글 + 모드별 재렌더 트리거.
import { state } from './state.js';
import { $ } from './dom.js';
import { schedule } from './chroma.js';
import { drawGridPreview, updateGridControlsAvailability } from './grid.js';
import { drawCropCanvas, cropState } from './crop.js';

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

export function initMode() {
  $('modeChromaBtn').addEventListener('click', () => setMode('chroma'));
  $('modeGridBtn').addEventListener('click', () => setMode('grid'));
  $('modeCropBtn').addEventListener('click', () => setMode('crop'));
}
