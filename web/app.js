// ChromaPeel — web entry point.
//
// 알고리즘 / 유틸리티 / 모드 코어는 algorithm.js · zip.js · state.js · util.js
// · chroma.js · grid.js · crop.js 로 분리되어 있다. 이 파일은 init() 에서 각
// 모듈의 init*() 를 호출하고 clipboard 라우팅 + 모드 전환 wire-up 만 담당한다
// (Phase 4 에서 clipboard.js / mode.js / main.js 로 더 분리 예정).

import { state } from './state.js';
import { $, setStatus, setCropStatus } from './dom.js';
import { initChroma, loadFile, schedule } from './chroma.js';
import {
  initGrid,
  drawGridPreview,
  updateGridControlsAvailability,
} from './grid.js';
import {
  initCrop,
  loadCropFile,
  drawCropCanvas,
  cropState,
} from './crop.js';

// ---------- Clipboard input ----------
// 두 가지 트리거: 전역 paste 이벤트 + "📋 붙여넣기" 버튼.
// 활성 모드 (state.mode) 에 따라 chroma/grid 는 loadFile, crop 은 loadCropFile 로 라우팅.

function statusForActiveMode(text, mode) {
  const target = mode || state.mode;
  if (target === 'crop') setCropStatus(text);
  else setStatus(text);
}

function handleClipboardImage(blob, mode) {
  if (!blob) return;
  const subtype = (blob.type && blob.type.split('/')[1]) || 'png';
  const ext = subtype.split(';')[0] || 'png';
  const ts = Date.now();
  const file = new File([blob], `clipboard_${ts}.${ext}`, {
    type: blob.type || 'image/png',
  });
  // mode 는 paste 트리거 시점의 값을 잠가서 전달 받는다 — 사용자가 paste 진행 중에
  // 모드를 토글해도 의도치 않은 모드로 라우팅되지 않게 한다.
  const target = mode || state.mode;
  if (target === 'crop') loadCropFile(file);
  else loadFile(file);
}

function tryConsumeClipboardItems(items) {
  if (!items) return false;
  // paste 이벤트는 동기 path 라 race 우려 없음 — state.mode 그대로 전달.
  const targetMode = state.mode;
  for (const item of items) {
    if (item.kind === 'file' && item.type && item.type.startsWith('image/')) {
      const blob = item.getAsFile();
      if (blob) {
        handleClipboardImage(blob, targetMode);
        return true;
      }
    }
  }
  return false;
}

// blob 이 실제로 디코딩 가능한 이미지인지 동기적으로 검증.
// 미지원 환경에선 true (검증 skip — 기존 동작과 동일).
// pasteFromClipboard 의 fallback chain 이 손상된 type 하나로 멈추지 않도록,
// loadFile 의 비동기 img.onerror 이전에 여기서 한 번 가린다.
async function decodeBlobIsImage(blob) {
  if (!blob || typeof createImageBitmap !== 'function') return Boolean(blob);
  try {
    const bitmap = await createImageBitmap(blob);
    if (bitmap && typeof bitmap.close === 'function') bitmap.close();
    return true;
  } catch (e) {
    return false;
  }
}

async function pasteFromClipboard() {
  if (!navigator.clipboard || typeof navigator.clipboard.read !== 'function') {
    statusForActiveMode('이 브라우저는 클립보드 이미지 읽기를 지원하지 않습니다.');
    return;
  }
  // 비동기 await 가 끼어들기 전에 현재 모드를 잠근다. 이후 사용자가 모드를 토글해도
  // 본 paste 호출은 트리거 시점의 모드로 일관 라우팅된다.
  const targetMode = state.mode;
  let items;
  try {
    items = await navigator.clipboard.read();
  } catch (err) {
    if (err && err.name === 'NotAllowedError') {
      statusForActiveMode('클립보드 접근 권한이 거부되었습니다.', targetMode);
    } else {
      statusForActiveMode(`클립보드 읽기 실패: ${(err && err.message) || err}`, targetMode);
    }
    return;
  }
  // 한 item 안에 여러 image type 이 공존할 수 있고 (예: png + svg+xml),
  // 또 여러 item 이 stage 될 수도 있다. 첫 매치만 시도하던 기존 구현은
  // 부분 손상된 type 하나로 paste 전체가 실패했고, getType() 성공만 본 직전 구현은
  // 비동기 디코드 실패 시 다음 후보를 시도하지 못했다 — 그래서 createImageBitmap
  // 으로 디코드 가능 여부를 사전 검증하고, 검증 실패 시 다음 후보로 넘어간다.
  let lastError = null;
  let sawImage = false;
  for (const item of items) {
    const imageTypes = item.types ? item.types.filter((t) => t.startsWith('image/')) : [];
    for (const imageType of imageTypes) {
      sawImage = true;
      let blob;
      try {
        blob = await item.getType(imageType);
      } catch (err) {
        lastError = err;
        continue;
      }
      if (await decodeBlobIsImage(blob)) {
        handleClipboardImage(blob, targetMode);
        return;
      }
      lastError = new Error(`디코드 실패: ${imageType}`);
    }
  }
  if (sawImage && lastError) {
    statusForActiveMode(
      `클립보드 이미지 읽기 실패: ${(lastError && lastError.message) || lastError}`,
      targetMode,
    );
  } else {
    statusForActiveMode('클립보드에 이미지가 없습니다.', targetMode);
  }
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

// ---------- Init ----------

function init() {
  initChroma();
  initGrid();
  initCrop();

  // Clipboard paste — global event + explicit buttons (active-mode-aware).
  document.addEventListener('paste', (e) => {
    const items = e.clipboardData && e.clipboardData.items;
    if (!items) return;
    if (tryConsumeClipboardItems(items)) e.preventDefault();
  });
  $('pasteBtnChromaGrid').addEventListener('click', pasteFromClipboard);
  $('pasteBtnCrop').addEventListener('click', pasteFromClipboard);

  // Mode switch
  $('modeChromaBtn').addEventListener('click', () => setMode('chroma'));
  $('modeGridBtn').addEventListener('click', () => setMode('grid'));
  $('modeCropBtn').addEventListener('click', () => setMode('crop'));
}

document.addEventListener('DOMContentLoaded', init);
