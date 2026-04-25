# ChromaPeel

**[한국어](README.md)** | [English](README.en.md)

PNG 이미지의 특정 배경색(크로마 키)을 투명하게 처리하는 배치 도구입니다. 안티앨리어싱된 엣지의 색상 프린지까지 깔끔하게 제거합니다.

## 사용 예시

타겟 색상 `(255, 37, 255)` 마젠타 배경의 스프라이트 시트를 처리한 결과입니다.

| Before (입력) | After (출력) |
|:---:|:---:|
| <img src="docs/before.png" width="400"/> | <img src="docs/after.png" width="400"/> |
| 마젠타 배경 포함 | 배경 투명 + 엣지 프린지 제거 |

> Feather 그라데이션 + Color Decontamination + Edge Erosion의 조합으로 안티앨리어싱된 엣지까지 깔끔하게 처리됩니다.

## 주요 기능

- **드래그앤드롭 GUI** — PNG를 창에 드래그해서 등록, 버튼 클릭으로 변환, 결과 썸네일을 탐색기로 드래그해서 가져가기
- **썸네일 상호작용** — 더블클릭으로 기본 뷰어에서 열기, 우클릭으로 클립보드 복사 / 경로 복사 / 탐색기에서 보기 / (입력) 제거
- **배경 자동 감지 (선택)** — 체크박스 하나로 각 이미지의 테두리에서 배경색을 자동 감지 → 파일마다 다른 배경색도 한 번에 처리
- 지정한 색상을 알파 채널로 변환 (크로마 키 제거)
- **Feather 그라데이션** — 엣지 픽셀을 부드럽게 페이드
- **Color Decontamination** — 반투명 픽셀에서 배경색 tint 제거
- **Edge Erosion** — 잔여 프린지 완전 제거
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

## 사용법

### GUI 모드 (권장)

Windows는 `run.bat`을, macOS/Linux는 `./run.sh`를 실행하면 GUI가 열립니다.

1. 변환할 PNG 파일을 좌측 **입력 패널**로 드래그합니다.
2. 중앙 **[변환]** 버튼을 클릭합니다.
3. 우측 **결과 패널**에 나타난 썸네일을 탐색기/바탕화면으로 드래그해서 가져갑니다.

**썸네일 조작**: 더블클릭으로 기본 이미지 뷰어에서 열 수 있고, 우클릭 메뉴에서 이미지 클립보드 복사 · 파일 경로 복사 · 탐색기에서 보기 · (입력 패널만) 해당 입력 제거가 가능합니다.

"▸ 고급 설정" 토글을 열면 대상 색상 · Tolerance · Feather · Edge Erosion · Decontaminate를 GUI에서 조절할 수 있습니다. **"자동 감지"** 체크박스를 켜면 대상 색상을 수동으로 지정하는 대신 각 이미지의 테두리에서 자동으로 배경색을 추출합니다. "기본값 복원"으로 언제든 기본값으로 리셋됩니다.

> 내부적으로 입력은 `base/`에 스테이징되고 결과는 `alpha/`에 저장됩니다. "결과 폴더 열기" 버튼으로 `alpha/`를 탐색기에서 바로 확인할 수 있습니다.

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
└── .gitignore
```

## 파라미터 튜닝 가이드

| 증상 | 해결 |
|------|------|
| 엣지에 배경색 프린지가 남음 | `edge_erosion` 2 이상으로 증가 또는 `feather` 증가 |
| 얇은 피처(풀잎, 줄기)가 사라짐 | `edge_erosion=0`으로 침식 해제 |
| 스프라이트 본연 색상이 변경됨 | `decontaminate=False`로 디컨태미네이션 해제 |
| 배경이 덜 제거됨 | `tolerance` 증가 |
