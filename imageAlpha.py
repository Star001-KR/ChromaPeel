from PIL import Image
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
from pathlib import Path
from typing import Callable, Optional

__version__ = "0.3.0"

logger = logging.getLogger(__name__)

RGB = tuple[int, int, int]

# (index, total, input_path, output_path or None, error or None)
# - On success: output_path is set, error is None.
# - On per-file failure: output_path is None, error holds the exception.
ProgressCallback = Callable[[int, int, str, Optional[str], Optional[BaseException]], None]

# CLI / GUI 공유 사용자 기본값 — 마젠타 크로마 키 시나리오에 튜닝된 값.
# `remove_color` / `process_folder` 의 함수-level default 는 라이브러리 호환을 위해
# 더 보수적인 값을 유지한다 (tolerance=30, feather=0, edge_erosion=0).
# GUI (`chromapeel_gui/app.py`) 도 이 상수를 import 해 동일 default 를 공유한다.
APP_DEFAULT_TARGET_COLOR: RGB = (255, 37, 255)
APP_DEFAULT_TOLERANCE = 20
APP_DEFAULT_FEATHER = 100
APP_DEFAULT_DECONTAMINATE = True
APP_DEFAULT_EDGE_EROSION = 1
APP_DEFAULT_AUTO_TRIM = False
APP_DEFAULT_TRIM_PADDING = 0


def detect_background_colors(
    data: np.ndarray,
    min_ratio: float = 0.05,
    max_k: int = 8,
) -> list[RGB]:
    """테두리에서 지배색을 빈도 내림차순으로 반환합니다 (동적 k).

    최빈색 1개는 비율과 무관하게 반드시 포함, 이후 색은 비율 >= min_ratio 인 것만
    max_k 개까지 채택합니다.

    정렬은 (count desc, R asc, G asc, B asc) 로 — JS 포트와 byte-for-byte 결과
    동등성을 위해 결정론적 tie-break 을 강제합니다.

    :param data: (H, W, 3+) 형태의 RGB 또는 RGBA 배열 (uint8 또는 float)
    :param min_ratio: 추가 색 채택을 위한 최소 비율 (테두리 픽셀 대비)
    :param max_k: 반환할 최대 색상 수 (>= 1)
    """
    rgb = data[..., :3].astype(np.uint8)
    # 첫/끝 행은 전체, 첫/끝 열은 코너 제외 — 그렇지 않으면 코너 4 픽셀이 2 번 집계된다.
    border = np.concatenate([
        rgb[0, :, :],
        rgb[-1, :, :],
        rgb[1:-1, 0, :],
        rgb[1:-1, -1, :],
    ])
    colors, counts = np.unique(border, axis=0, return_counts=True)
    total = int(counts.sum())

    # lexsort 는 마지막 key 가 primary. count desc(=-count asc) 가 primary,
    # 동률 시 R, G, B asc 순. uint64 → -count 의 wraparound 방지 위해 int64.
    order = np.lexsort((
        colors[:, 2], colors[:, 1], colors[:, 0],
        -counts.astype(np.int64),
    ))
    sorted_colors = colors[order]
    sorted_counts = counts[order]

    accepted: list[RGB] = []
    for c, cnt in zip(sorted_colors, sorted_counts):
        if accepted and (cnt / total) < min_ratio:
            break
        accepted.append((int(c[0]), int(c[1]), int(c[2])))
        if len(accepted) >= max_k:
            break
    return accepted


def detect_background_color(data: np.ndarray) -> RGB:
    """테두리 최빈 RGB 단일 색을 반환합니다 (역호환 wrapper).

    :param data: (H, W, 3+) 형태의 RGB 또는 RGBA 배열 (uint8 또는 float)
    """
    return detect_background_colors(data, min_ratio=0.0, max_k=1)[0]


def trim_transparent_edges(
    rgba: np.ndarray,
    alpha_threshold: int = 0,
    padding: int = 0,
) -> Optional[tuple[int, int, int, int]]:
    """알파 채널의 bbox를 계산해 (left, top, right, bottom) 튜플로 반환합니다.

    PIL.Image.crop과 동일한 (left, top, right, bottom) 형식 — right/bottom은 exclusive.
    `alpha_threshold` 초과 픽셀이 하나도 없으면 None을 반환합니다(전체 투명).

    :param rgba: (H, W, 4) uint8 RGBA 배열
    :param alpha_threshold: 이 값을 초과하는 알파를 가진 픽셀만 보존 대상으로 간주 (0=완전 투명만 자르기)
    :param padding: bbox 사방으로 추가할 여유 픽셀 (이미지 경계로 클램프)
    """
    alpha = rgba[..., 3]
    mask = alpha > alpha_threshold
    if not mask.any():
        return None

    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)
    ys = np.where(rows)[0]
    xs = np.where(cols)[0]
    top, bottom = int(ys[0]), int(ys[-1]) + 1
    left, right = int(xs[0]), int(xs[-1]) + 1

    h, w = rgba.shape[:2]
    if padding > 0:
        top = max(0, top - padding)
        left = max(0, left - padding)
        bottom = min(h, bottom + padding)
        right = min(w, right + padding)

    return left, top, right, bottom


def remove_color(
    input_path: str,
    output_path: str,
    target_color: Optional[RGB] = None,
    tolerance: int = 30,
    feather: int = 0,
    decontaminate: bool = True,
    edge_erosion: int = 0,
    auto_trim: bool = False,
    trim_padding: int = 0,
    trim_alpha_threshold: int = 0,
    target_colors: Optional[list[RGB]] = None,
) -> None:
    """
    특정 색상(들)을 투명하게 처리합니다. feather + color decontamination + 엣지 침식 + 자동 트림 지원.

    :param input_path: 입력 이미지 경로
    :param output_path: 출력 이미지 경로 (PNG 권장)
    :param target_color: 단일 제거 색상 (R, G, B). target_colors 와 동시 지정 불가. 둘 다 None 이면 테두리에서 자동 다색 감지.
    :param tolerance: 완전 투명으로 처리할 색상 허용 오차 (0~255)
    :param feather: 반투명 페이드 범위. tolerance~(tolerance+feather) 구간은 선형 그라데이션으로 알파 적용
    :param decontaminate: True면 반투명 엣지 픽셀에서 (가장 가까운) 타겟 색상 성분을 빼서 핑크/컬러 프린지 제거
    :param edge_erosion: 투명 영역과 인접한 불투명 픽셀을 N픽셀만큼 깎음 (잔여 프린지 제거). 얇은 피처 유실 주의.
    :param auto_trim: True면 저장 직전에 알파 bbox로 잘라 투명 외곽을 제거합니다.
    :param trim_padding: auto_trim bbox 사방에 추가할 여유 픽셀 수.
    :param trim_alpha_threshold: 이 값을 초과하는 알파만 bbox 계산에 포함 (기본 0 = 완전 투명만 자르기).
    :param target_colors: 다색 제거 — RGB 튜플 리스트. 각 픽셀은 가장 가까운 타겟 색상 기준으로 판정.
        target_color 와 동시 지정 불가. 둘 다 None 이면 detect_background_colors 로 자동 다색 감지.
    """
    if target_color is not None and target_colors is not None:
        raise ValueError("target_color 와 target_colors 는 동시에 지정할 수 없습니다.")

    img = Image.open(input_path).convert("RGBA")
    data = np.array(img).astype(np.float32)

    if target_colors is not None:
        if len(target_colors) == 0:
            raise ValueError("target_colors 가 비어 있습니다.")
        colors: list[RGB] = [(int(c[0]), int(c[1]), int(c[2])) for c in target_colors]
    elif target_color is not None:
        colors = [(int(target_color[0]), int(target_color[1]), int(target_color[2]))]
    else:
        colors = detect_background_colors(data)

    r, g, b, a = data[..., 0], data[..., 1], data[..., 2], data[..., 3]

    # 각 타겟 색마다 max-channel distance 를 stack → (K, H, W).
    # K=1 일 때 단일-색 경로와 byte-for-byte 동일 (argmin 결과 모두 0).
    dist_stack = np.stack([
        np.maximum.reduce([np.abs(r - tc[0]), np.abs(g - tc[1]), np.abs(b - tc[2])])
        for tc in colors
    ])
    nearest_idx = np.argmin(dist_stack, axis=0)
    distance = np.take_along_axis(dist_stack, nearest_idx[None, ...], axis=0)[0]

    alpha_mult = np.ones_like(distance, dtype=np.float32)
    alpha_mult[distance <= tolerance] = 0.0

    if feather > 0:
        feather_zone = (distance > tolerance) & (distance <= tolerance + feather)
        alpha_mult[feather_zone] = (distance[feather_zone] - tolerance) / feather

        if decontaminate:
            # observed = t * target + (1-t) * original,  where t = 1 - alpha_mult.
            # 다색일 땐 픽셀마다 nearest target 색상으로 분리해 decontaminate.
            t = 1.0 - alpha_mult[feather_zone]
            denom = np.maximum(1.0 - t, 1e-6)
            colors_arr = np.array(colors, dtype=np.float32)   # (K, 3)
            nearest_colors = colors_arr[nearest_idx]          # (H, W, 3)
            for ch in (0, 1, 2):
                tc_at_pixel = nearest_colors[..., ch][feather_zone]
                observed = data[..., ch][feather_zone]
                data[..., ch][feather_zone] = np.clip(
                    (observed - t * tc_at_pixel) / denom, 0, 255
                )

    data[..., 3] = a * alpha_mult

    if edge_erosion > 0:
        alpha = data[..., 3]
        for _ in range(edge_erosion):
            padded = np.pad(alpha, 1, mode="edge")
            alpha = np.minimum.reduce([
                padded[:-2, :-2], padded[:-2, 1:-1], padded[:-2, 2:],
                padded[1:-1, :-2], padded[1:-1, 1:-1], padded[1:-1, 2:],
                padded[2:, :-2], padded[2:, 1:-1], padded[2:, 2:],
            ])
        data[..., 3] = alpha

    final = np.clip(data, 0, 255).astype(np.uint8)

    if auto_trim:
        bbox = trim_transparent_edges(final, alpha_threshold=trim_alpha_threshold,
                                      padding=trim_padding)
        if bbox is None:
            logger.warning("자동 트림 스킵: 모든 픽셀이 투명입니다 — %s", input_path)
        else:
            left, top, right, bottom = bbox
            final = final[top:bottom, left:right]

    Image.fromarray(final).save(output_path, "PNG")

def process_folder(
    input_dir: str,
    output_dir: str,
    target_color: Optional[RGB] = None,
    tolerance: int = 30,
    feather: int = 0,
    decontaminate: bool = True,
    edge_erosion: int = 0,
    auto_trim: bool = False,
    trim_padding: int = 0,
    trim_alpha_threshold: int = 0,
    progress_callback: Optional[ProgressCallback] = None,
    max_workers: Optional[int] = None,
    target_colors: Optional[list[RGB]] = None,
) -> None:
    """
    input_dir 내 모든 PNG 이미지에 알파 처리를 적용해 output_dir에 저장합니다.

    :param input_dir: 입력 폴더 경로
    :param output_dir: 출력 폴더 경로 (없으면 자동 생성)
    :param target_color: 단일 제거 색상. target_colors 와 동시 지정 불가. 둘 다 None 이면 파일별 자동 다색 감지.
    :param tolerance: 완전 투명 처리할 색상 허용 오차 (0~255)
    :param feather: 반투명 페이드 범위
    :param decontaminate: 엣지 색상 프린지 제거 여부 (다색이면 픽셀별 nearest target 으로 적용)
    :param edge_erosion: 엣지 침식 픽셀 수 (잔여 프린지 제거)
    :param auto_trim: True면 저장 직전 알파 bbox로 투명 외곽을 잘라냄 (전체 투명 시 원본 유지)
    :param trim_padding: auto_trim bbox 사방으로 추가할 여유 픽셀 수
    :param trim_alpha_threshold: 이 값을 초과하는 알파만 auto_trim bbox 계산에 포함
        (기본 0 = 완전 투명만 자르기). auto_trim=False면 무시됨.
    :param progress_callback: 각 파일 처리 후 호출. 시그니처:
        (index, total, input_path, output_path or None, error or None).
        index는 "N번째 완료"를 의미하며, 병렬 모드에서는 입력 순서와 다를 수 있습니다.
        한 파일이 실패해도 다음 파일을 계속 처리합니다.
    :param max_workers: 동시 처리 워커 수.
        None(기본) — `min(os.cpu_count(), 파일 수)` 자동 결정.
        1 — 순차 처리 (입력 순서대로 콜백 보장; 결정적 동작이 필요할 때).
        N — N개 스레드로 병렬 처리.
    :param target_colors: 다색 제거 — RGB 튜플 리스트. target_color 와 동시 지정 불가.
        둘 다 None 이면 파일별로 detect_background_colors 자동 감지.
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    if not input_path.is_dir():
        raise FileNotFoundError(f"입력 폴더를 찾을 수 없습니다: {input_dir}")

    output_path.mkdir(parents=True, exist_ok=True)

    png_files = sorted([f for f in input_path.iterdir()
                        if f.is_file() and f.suffix.lower() == ".png"])

    if not png_files:
        return

    total = len(png_files)
    if max_workers is None:
        workers = min(os.cpu_count() or 4, total)
    else:
        workers = max(1, max_workers)

    logger.info("배치 처리 시작: %d개 파일, 워커 %d", total, workers)

    def _process_one(file: Path) -> tuple[Path, Optional[Path], Optional[BaseException]]:
        out_file = output_path / file.name
        try:
            remove_color(str(file), str(out_file), target_color, tolerance,
                         feather, decontaminate, edge_erosion,
                         auto_trim=auto_trim, trim_padding=trim_padding,
                         trim_alpha_threshold=trim_alpha_threshold,
                         target_colors=target_colors)
            return file, out_file, None
        except Exception as e:
            logger.warning("처리 실패: %s — %s", file, e, exc_info=True)
            return file, None, e

    def _emit(i: int, in_file: Path, out_file: Optional[Path], err: Optional[BaseException]) -> None:
        if progress_callback is not None:
            progress_callback(i, total, str(in_file),
                              str(out_file) if out_file is not None else None, err)

    if workers == 1:
        # Sequential path keeps submission order — needed by callers that
        # rely on deterministic callback ordering (e.g. some tests).
        for i, file in enumerate(png_files, 1):
            in_file, out_file, err = _process_one(file)
            _emit(i, in_file, out_file, err)
        return

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_process_one, f) for f in png_files]
        for i, future in enumerate(as_completed(futures), 1):
            in_file, out_file, err = future.result()
            _emit(i, in_file, out_file, err)


def _parse_rgb(s: str) -> RGB:
    """CLI 의 'R,G,B' 문자열을 (int, int, int) 로 파싱."""
    parts = s.split(",")
    if len(parts) != 3:
        raise ValueError(f"색상 형식이 잘못됨: {s!r} (예: '255,37,255')")
    try:
        r, g, b = (int(p.strip()) for p in parts)
    except ValueError:
        raise ValueError(f"색상 값은 정수여야 함: {s!r}")
    if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
        raise ValueError(f"색상 값은 0~255 범위여야 함: {s!r}")
    return (r, g, b)


def _run_cli() -> None:
    import argparse
    from clipboard_utils import stage_clipboard_image_or_exit

    parser = argparse.ArgumentParser(
        prog="chromapeel-cli",
        description="base/ 폴더의 PNG에서 크로마 키를 제거해 alpha/ 폴더로 저장합니다.",
    )
    parser.add_argument(
        "--target-color", "-t",
        action="append", default=None, metavar="R,G,B",
        help='제거할 색상 ("R,G,B" 형식). 여러 번 지정하면 다색 제거. '
             '미지정 시 기본 마젠타 (255,37,255) 사용.',
    )
    parser.add_argument(
        "--auto", action="store_true",
        help="대상 색상을 이미지 테두리에서 자동 감지 (다색 가능). "
             "--target-color 와 동시 지정 불가.",
    )
    parser.add_argument("--auto-trim", action="store_true",
                        help="저장 직전에 알파 bbox로 투명 외곽을 잘라냅니다.")
    parser.add_argument("--trim-padding", type=int, default=0, metavar="N",
                        help="--auto-trim bbox 사방으로 추가할 여유 픽셀 수 (기본 0).")
    parser.add_argument("--from-clipboard", action="store_true", dest="from_clipboard",
                        help="클립보드의 이미지를 base/ 에 저장한 뒤 그 파일만 처리합니다.")
    args = parser.parse_args()

    if args.target_color and args.auto:
        parser.error("--target-color 와 --auto 는 동시에 지정할 수 없습니다.")

    if args.auto:
        target_colors: Optional[list[RGB]] = None
    elif args.target_color:
        try:
            target_colors = [_parse_rgb(s) for s in args.target_color]
        except ValueError as e:
            parser.error(str(e))
    else:
        target_colors = [APP_DEFAULT_TARGET_COLOR]

    common_kwargs = dict(
        tolerance=APP_DEFAULT_TOLERANCE,
        feather=APP_DEFAULT_FEATHER,
        decontaminate=APP_DEFAULT_DECONTAMINATE,
        edge_erosion=APP_DEFAULT_EDGE_EROSION,
        auto_trim=args.auto_trim,
        trim_padding=args.trim_padding,
        target_colors=target_colors,
    )

    if args.from_clipboard:
        in_path = stage_clipboard_image_or_exit("base")
        out_dir = Path("alpha")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / in_path.name
        remove_color(str(in_path), str(out_path), **common_kwargs)
        print(f"완료: {out_path.name}")
        return

    def _cli_progress(i, total, in_path, out_path, error):
        name = Path(in_path).name
        if error is not None:
            print(f"[{i}/{total}] 실패: {name} — {error}")
        else:
            print(f"[{i}/{total}] 완료: {name}")

    process_folder(
        input_dir="base",
        output_dir="alpha",
        progress_callback=_cli_progress,
        **common_kwargs,
    )


if __name__ == "__main__":
    _run_cli()