// ChromaPeel — web entry point.
//
// 모듈 트리:
//   algorithm.js ── 크로마 키 알고리즘 코어 (Python parity)
//   zip.js       ── Store-mode ZIP 빌더
//   util.js      ── 파일명 sanitisation
//   state.js     ── chroma + grid 공유 state (싱글턴)
//   dom.js       ── $ helper, setStatus / setCropStatus
//   chroma.js    ── 크로마 모드 (loadFile, schedule, saveOrShare, initChroma)
//   grid.js      ── 격자 분할 모드 (drawGridPreview, runGridSplit, initGrid)
//   crop.js      ── 수동 크롭 모드 (drag/resize, applyCrop, initCrop)
//   clipboard.js ── 전역 paste + 📋 버튼 (활성 모드로 라우팅)
//   mode.js      ── 모드 전환 wire-up (chroma / grid / crop 탭)
//   main.js      ── 이 파일 — DOMContentLoaded → init*() 호출
//
// 모든 모듈은 단방향 의존: 상위 모듈이 하위 모듈을 import 한다.
// state 는 ESM 싱글턴이라 모든 import 자가 같은 참조를 공유한다.

import { initChroma } from './chroma.js';
import { initGrid } from './grid.js';
import { initCrop } from './crop.js';
import { initClipboard } from './clipboard.js';
import { initMode } from './mode.js';
import { initHistory } from './history.js';

function init() {
  initChroma();
  initGrid();
  initCrop();
  initClipboard();
  initMode();
  initHistory();
}

document.addEventListener('DOMContentLoaded', init);
