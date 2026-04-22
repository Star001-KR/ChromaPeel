# ChromaPeel

PNG 이미지의 특정 배경색(크로마 키)을 투명하게 처리하는 배치 도구입니다. 안티앨리어싱된 엣지의 색상 프린지까지 깔끔하게 제거합니다.

## 주요 기능

- 지정한 색상을 알파 채널로 변환 (크로마 키 제거)
- **Feather 그라데이션** — 엣지 픽셀을 부드럽게 페이드
- **Color Decontamination** — 반투명 픽셀에서 배경색 tint 제거
- **Edge Erosion** — 잔여 프린지 완전 제거
- 폴더 단위 일괄 처리

## 요구사항

- Python 3.8+
- Pillow, numpy

## 설치

Windows에서 `setup.bat`을 더블클릭하거나 실행:

```bash
setup.bat
```

자동으로 다음을 수행합니다:

1. `.venv` 가상환경 생성 (없을 경우)
2. pip 업그레이드 및 의존성 설치
3. `base/`, `alpha/` 폴더 생성

## 사용법

1. 처리할 PNG 이미지를 `base/` 폴더에 넣습니다.
2. 스크립트 실행:

```bash
.venv\Scripts\python.exe imageAlpha.py
```

3. `alpha/` 폴더에서 결과를 확인합니다.

## 파라미터

`imageAlpha.py` 하단의 `process_folder()` 호출에서 조정 가능합니다.

| 파라미터 | 설명 | 기본값 |
|----------|------|--------|
| `input_dir` | 입력 폴더 | `"base"` |
| `output_dir` | 출력 폴더 | `"alpha"` |
| `target_color` | 제거할 색상 (R, G, B) | `(255, 37, 255)` (마젠타) |
| `tolerance` | 완전 투명으로 처리할 허용 오차 | `20` |
| `feather` | 반투명 페이드 범위 | `100` |
| `decontaminate` | 배경색 tint 제거 여부 | `True` |
| `edge_erosion` | 엣지 침식 픽셀 수 | `1` |

## 동작 원리

1. **거리 계산** — 각 픽셀 색상과 타겟 색상 간 L∞ 거리(채널별 최대 차이)
2. **완전 투명** — 거리 ≤ `tolerance`인 픽셀의 알파를 0으로 설정
3. **Feather 페이드** — 거리 `tolerance`~`tolerance+feather` 구간을 선형 그라데이션 알파로 설정
4. **Decontamination** — 반투명 픽셀에서 타겟 색상 성분을 수식 역산으로 제거
   - `observed = t·target + (1-t)·original` → `original = (observed - t·target) / (1-t)`
5. **Edge Erosion** — 3×3 min filter로 투명 영역에 인접한 불투명 픽셀을 N픽셀 깎아냄

## 프로젝트 구조

```
ChromaPeel/
├── .venv/              # Python 가상환경 (git 추적 제외)
├── base/               # 입력 이미지 폴더
├── alpha/              # 출력 이미지 폴더
├── imageAlpha.py       # 메인 스크립트
├── requirements.txt    # Python 의존성
├── setup.bat           # Windows 자동 설치 스크립트
└── .gitignore
```

## 파라미터 튜닝 가이드

| 증상 | 해결 |
|------|------|
| 엣지에 배경색 프린지가 남음 | `edge_erosion` 2 이상으로 증가 또는 `feather` 증가 |
| 얇은 피처(풀잎, 줄기)가 사라짐 | `edge_erosion=0`으로 침식 해제 |
| 스프라이트 본연 색상이 변경됨 | `decontaminate=False`로 디컨태미네이션 해제 |
| 배경이 덜 제거됨 | `tolerance` 증가 |
