# ChromaPeel

**[한국어](README.md)** | [English](README.en.md)

[![Test](https://github.com/Star001-KR/ChromaPeel/actions/workflows/test.yml/badge.svg)](https://github.com/Star001-KR/ChromaPeel/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

PNG 이미지의 특정 배경색(크로마 키)을 투명하게 처리하는 배치 도구입니다. 안티앨리어싱된 엣지의 색상 프린지까지 깔끔하게 제거합니다.

## 사용 예시

타겟 색상 `(255, 37, 255)` 마젠타 배경의 스프라이트 시트를 처리한 결과입니다.

| Before (입력) | After (출력) |
|:---:|:---:|
| <img src="docs/before.png" width="400"/> | <img src="docs/after.png" width="400"/> |
| 마젠타 배경 포함 | 배경 투명 + 엣지 프린지 제거 |

> Feather 그라데이션 + Color Decontamination + Edge Erosion의 조합으로 안티앨리어싱된 엣지까지 깔끔하게 처리됩니다.

## 주요 기능

- **데스크톱 앱(Win/Mac/Linux)** + **웹 앱(모바일/PC 브라우저)** 두 가지 사용 방식
- **드래그앤드롭 GUI** — PNG를 창에 드래그해서 등록, 버튼 클릭으로 변환, 결과 썸네일을 탐색기로 드래그해서 가져가기
- **썸네일 상호작용** — 더블클릭으로 기본 뷰어에서 열기, 우클릭으로 클립보드 복사 / 경로 복사 / 탐색기에서 보기 / **(결과) 이름 변경** / (입력) 제거
- **배치 진행률 바** — 다중 파일 변환 시 N/M 진행 상황을 시각화
- **배경 자동 감지 (선택)** — 체크박스 하나로 각 이미지의 테두리에서 배경색을 자동 감지 → 파일마다 다른 배경색도 한 번에 처리
- 지정한 색상을 알파 채널로 변환 (크로마 키 제거)
- **Feather 그라데이션** — 엣지 픽셀을 부드럽게 페이드
- **Color Decontamination** — 반투명 픽셀에서 배경색 tint 제거
- **Edge Erosion** — 잔여 프린지 완전 제거
- **부분 실패 허용** — 한 파일이 깨져 있어도 나머지 파일을 계속 처리
- 폴더 단위 일괄 처리 (CLI 모드)

## 요구사항

- Python 3.8+
- Pillow, numpy, tkinterdnd2
- (Linux만 해당) 이미지 클립보드 복사를 사용하려면 `xclip`(X11) 또는 `wl-clipboard`(Wayland) 필요

## 설치

**Windows**: `setup.bat`을 더블클릭하거나 실행

```bat
setup.bat
```

**macOS / Linux**: 터미널에서 `setup.sh` 실행

```bash
./setup.sh
```

자동으로 다음을 수행합니다:

1. `.venv` 가상환경 생성 (없을 경우)
2. pip 업그레이드 및 의존성 설치
3. `base/`, `alpha/` 폴더 생성

**개발자 설치 (pip editable)**: 테스트 스위트나 `chromapeel` / `chromapeel-cli` 콘솔 스크립트를 사용하려면 다음을 실행합니다.

```bash
pip install -e ".[dev]"
```

## 사용법

### GUI 모드 (권장)

Windows는 `run.bat`을, macOS/Linux는 `./run.sh`를 실행하면 GUI가 열립니다.

1. 변환할 PNG 파일을 좌측 **입력 패널**로 드래그합니다.
2. 중앙 **[변환]** 버튼을 클릭합니다.
3. 우측 **결과 패널**에 나타난 썸네일을 탐색기/바탕화면으로 드래그해서 가져갑니다.

**썸네일 조작**: 더블클릭으로 기본 이미지 뷰어에서 열 수 있고, 우클릭 메뉴에서 이미지 클립보드 복사 · 파일 경로 복사 · 탐색기에서 보기 · **(결과 패널) 이름 변경...** · (입력 패널) 해당 입력 제거가 가능합니다. 이름 변경 시 `.png`는 자동으로 붙고 Windows 금지 문자는 차단됩니다.

"▸ 고급 설정" 토글을 열면 대상 색상 · Tolerance · Feather · Edge Erosion · Decontaminate를 GUI에서 조절할 수 있습니다. **"자동 감지"** 체크박스를 켜면 대상 색상을 수동으로 지정하는 대신 각 이미지의 테두리에서 자동으로 배경색을 추출합니다. "기본값 복원"으로 언제든 기본값으로 리셋됩니다.

> 내부적으로 입력은 `base/`에 스테이징되고 결과는 `alpha/`에 저장됩니다. "결과 폴더 열기" 버튼으로 `alpha/`를 탐색기에서 바로 확인할 수 있습니다.

### 웹 / 모바일 모드

`web/` 폴더에 있는 정적 웹 버전은 설치 없이 브라우저에서 바로 동작합니다.

- **온라인** — `main` 브랜치에 푸시되면 GitHub Pages에 자동 배포되며, `https://star001-kr.github.io/ChromaPeel/`에서 접속 가능합니다 (저장소 설정의 *Pages → Source* 를 *GitHub Actions* 로 한 번 켜야 합니다).
- **로컬** — `web/` 폴더에서 정적 서버 실행. 예: `python3 -m http.server -d web 8000` 후 브라우저에서 `http://localhost:8000`.
- **모바일** — 카메라롤에서 이미지를 선택하고, 슬라이더로 실시간 미리보기 후 **저장 / 공유** 버튼으로 결과 PNG를 사진앱·메신저 등으로 내보낼 수 있습니다.
- **결과 파일명** — 입력 이미지 이름에서 `{원본}_alpha`로 자동 채워지며, 저장 직전에 자유롭게 편집할 수 있습니다.
- **이미지 크기 제한** — 16MP(약 4096×4096)를 초과하는 이미지는 모바일 메모리 보호를 위해 거부합니다.

웹 버전은 단일 이미지 처리에 최적화되어 있고, 모든 처리는 브라우저 안에서만 이루어집니다(이미지가 서버로 업로드되지 않습니다).

### CLI 모드

1. 처리할 PNG 이미지를 `base/` 폴더에 넣습니다.
2. 스크립트 실행:

```bash
# Windows
.venv\Scripts\python.exe imageAlpha.py

# macOS / Linux
.venv/bin/python imageAlpha.py
```

3. `alpha/` 폴더에서 결과를 확인합니다.

## 파라미터

GUI 모드에서는 고급 설정 토글로 조절, CLI 모드에서는 `imageAlpha.py` 하단의 `process_folder()` 호출에서 조정합니다.

| 파라미터 | 설명 | 기본값 |
|----------|------|--------|
| `input_dir` | 입력 폴더 | `"base"` |
| `output_dir` | 출력 폴더 | `"alpha"` |
| `target_color` | 제거할 색상 (R, G, B). `None` 지정 시 각 이미지의 테두리에서 최빈 색상을 자동 감지 | `(255, 37, 255)` (마젠타) |
| `tolerance` | 완전 투명으로 처리할 허용 오차 | `20` |
| `feather` | 반투명 페이드 범위 | `100` |
| `decontaminate` | 배경색 tint 제거 여부 | `True` |
| `edge_erosion` | 엣지 침식 픽셀 수 | `1` |

## 동작 원리

1. **(선택) 자동 감지** — `target_color=None`인 경우 이미지 1픽셀 테두리의 최빈 RGB를 타겟 색상으로 사용
2. **거리 계산** — 각 픽셀 색상과 타겟 색상 간 L∞ 거리(채널별 최대 차이)
3. **완전 투명** — 거리 ≤ `tolerance`인 픽셀의 알파를 0으로 설정
4. **Feather 페이드** — 거리 `tolerance`~`tolerance+feather` 구간을 선형 그라데이션 알파로 설정
5. **Decontamination** — 반투명 픽셀에서 타겟 색상 성분을 수식 역산으로 제거
   - `observed = t·target + (1-t)·original` → `original = (observed - t·target) / (1-t)`
6. **Edge Erosion** — 3×3 min filter로 투명 영역에 인접한 불투명 픽셀을 N픽셀 깎아냄

## 수동 크롭

단일 사각형 영역을 골라 이미지를 잘라내는 **독립 도구**입니다. 크로마 키 제거와 무관하게 동작하며, 결과는 `alpha/{stem}_crop.png`에 저장됩니다.

### CLI 사용법

`chromapeel-crop` 콘솔 스크립트로 박스 좌표 4개(콤마 구분 정수)를 전달합니다.

```bash
chromapeel-crop INPUT --crop X,Y,W,H
```

- `X,Y`: 박스 좌상단 픽셀 좌표 (이미지 원점은 `(0, 0)`)
- `W,H`: 박스 너비 / 높이 (픽셀)
- 박스가 이미지 밖으로 벗어나면 이미지 경계로 자동 클램프되며, `W` 또는 `H`가 0 이하이면 에러로 종료합니다.

### 데스크톱 GUI

입력 패널의 썸네일을 **우클릭 → "크롭..."** 으로 모달을 엽니다. 모달에서는

- 마우스 드래그로 새 박스를 그리거나, 이미 그려진 박스를 잡고 끌어 이동
- 코너 4개 + 변 4개의 **8핸들**로 박스 크기 조정
- `X` / `Y` / `W` / `H` 입력 칸에 좌표를 직접 입력해 미세 조정

후 확인하면 결과가 `alpha/{stem}_crop.png`로 저장됩니다.

### 웹

상단 모드 스위치에서 **"크롭"** 을 선택하면 캔버스 위에 박스를 그릴 수 있습니다. 마우스 또는 터치 드래그로 새 박스를 만들고 8핸들로 크기를 조정한 뒤 **[잘라내기]** 버튼으로 결과 PNG를 저장합니다.

### 다중 영역

현재는 단일 영역만 지원하며, 다중 영역 선택은 후속 작업으로 검토할 수 있습니다.

> 자동 테스트는 코어 함수 단위 테스트만 포함하며, GUI / 웹 인터랙션(드래그·핸들·터치)은 수동 검증으로 확인합니다.

## 프로젝트 구조

```
ChromaPeel/
├── .venv/              # Python 가상환경 (git 추적 제외)
├── base/               # 입력 이미지 폴더 (GUI 드롭 시 자동 스테이징)
├── alpha/              # 출력 이미지 폴더
├── chromapeel_gui.py   # GUI 엔트리 (Tkinter + tkinterdnd2)
├── clipboard_utils.py  # 이미지 클립보드 복사 (Win ctypes / mac osascript / Linux xclip·wl-copy)
├── imageAlpha.py       # 처리 로직 (CLI 모드로도 실행 가능)
├── requirements.txt    # Python 의존성
├── setup.bat / setup.sh  # 자동 설치 스크립트 (Windows / macOS·Linux)
├── run.bat / run.sh      # GUI 원클릭 실행 (Windows / macOS·Linux)
├── web/                  # 모바일/브라우저용 웹 버전 (vanilla JS + Canvas)
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── tests/                # pytest + JS 패리티 테스트
│   ├── test_image_alpha.py
│   ├── test_js_parity.py
│   └── js_parity_runner.js
├── .github/workflows/deploy-web.yml  # GitHub Pages 자동 배포
└── .gitignore
```

## 파라미터 튜닝 가이드

| 증상 | 해결 |
|------|------|
| 엣지에 배경색 프린지가 남음 | `edge_erosion` 2 이상으로 증가 또는 `feather` 증가 |
| 얇은 피처(풀잎, 줄기)가 사라짐 | `edge_erosion=0`으로 침식 해제 |
| 스프라이트 본연 색상이 변경됨 | `decontaminate=False`로 디컨태미네이션 해제 |
| 배경이 덜 제거됨 | `tolerance` 증가 |

## 테스트

알고리즘 단위 테스트와 JS↔Python 바이트 단위 패리티 테스트가 `tests/`에 들어 있습니다.

```bash
pip install -e ".[dev]"   # pytest 포함 한 번만
pytest -v
```

JS 패리티 테스트는 `node`가 설치된 환경에서만 실행되며, 없으면 자동으로 스킵됩니다. 모든 푸시·PR은 GitHub Actions에서 Ubuntu / Windows / macOS × Python 3.8 / 3.10 / 3.12 매트릭스로 자동 검증됩니다.
