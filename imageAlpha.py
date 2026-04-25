from PIL import Image
import numpy as np
from pathlib import Path
from typing import Callable, Optional, Tuple

RGB = Tuple[int, int, int]

# (index, total, input_path, output_path or None, error or None)
# - On success: output_path is set, error is None.
# - On per-file failure: output_path is None, error holds the exception.
ProgressCallback = Callable[[int, int, str, Optional[str], Optional[BaseException]], None]


def detect_background_color(data: np.ndarray) -> RGB:
    """이미지의 1픽셀 테두리에서 최빈 RGB 색상을 반환합니다.

    :param data: (H, W, 3+) 형태의 RGB 또는 RGBA 배열 (uint8 또는 float)
    """
    rgb = data[..., :3].astype(np.uint8)
    border = np.concatenate([
        rgb[0, :, :],
        rgb[-1, :, :],
        rgb[:, 0, :],
        rgb[:, -1, :],
    ])
    colors, counts = np.unique(border, axis=0, return_counts=True)
    best = colors[counts.argmax()]
    return (int(best[0]), int(best[1]), int(best[2]))


def remove_color(
    input_path: str,
    output_path: str,
    target_color: Optional[RGB],
    tolerance: int = 30,
    feather: int = 0,
    decontaminate: bool = True,
    edge_erosion: int = 0,
) -> None:
    """
    특정 색상을 투명하게 처리합니다. feather + color decontamination + 엣지 침식 지원.

    :param input_path: 입력 이미지 경로
    :param output_path: 출력 이미지 경로 (PNG 권장)
    :param target_color: 제거할 색상 (R, G, B) 튜플. 예: (255, 255, 255) = 흰색. None이면 이미지 테두리에서 자동 감지
    :param tolerance: 완전 투명으로 처리할 색상 허용 오차 (0~255)
    :param feather: 반투명 페이드 범위. tolerance~(tolerance+feather) 구간은 선형 그라데이션으로 알파 적용
    :param decontaminate: True면 반투명 엣지 픽셀에서 타겟 색상 성분을 빼서 핑크/컬러 프린지 제거
    :param edge_erosion: 투명 영역과 인접한 불투명 픽셀을 N픽셀만큼 깎음 (잔여 프린지 제거). 얇은 피처 유실 주의.
    """
    img = Image.open(input_path).convert("RGBA")
    data = np.array(img).astype(np.float32)

    if target_color is None:
        target_color = detect_background_color(data)

    r, g, b, a = data[..., 0], data[..., 1], data[..., 2], data[..., 3]
    tr, tg, tb = target_color

    distance = np.maximum.reduce([np.abs(r - tr), np.abs(g - tg), np.abs(b - tb)])

    alpha_mult = np.ones_like(distance, dtype=np.float32)
    alpha_mult[distance <= tolerance] = 0.0

    if feather > 0:
        feather_zone = (distance > tolerance) & (distance <= tolerance + feather)
        alpha_mult[feather_zone] = (distance[feather_zone] - tolerance) / feather

        if decontaminate:
            # observed = t * target + (1-t) * original,  where t = 1 - alpha_mult
            t = 1.0 - alpha_mult[feather_zone]
            denom = np.maximum(1.0 - t, 1e-6)
            for ch, tc in zip((0, 1, 2), (tr, tg, tb)):
                observed = data[..., ch][feather_zone]
                data[..., ch][feather_zone] = np.clip((observed - t * tc) / denom, 0, 255)

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

    result = Image.fromarray(np.clip(data, 0, 255).astype(np.uint8))
    result.save(output_path, "PNG")

def process_folder(
    input_dir: str,
    output_dir: str,
    target_color: Optional[RGB],
    tolerance: int = 30,
    feather: int = 0,
    decontaminate: bool = True,
    edge_erosion: int = 0,
    progress_callback: Optional[ProgressCallback] = None,
) -> None:
    """
    input_dir 내 모든 PNG 이미지에 알파 처리를 적용해 output_dir에 저장합니다.

    :param input_dir: 입력 폴더 경로
    :param output_dir: 출력 폴더 경로 (없으면 자동 생성)
    :param target_color: 제거할 색상 (R, G, B) 튜플. None이면 파일별로 테두리 기반 자동 감지
    :param tolerance: 완전 투명 처리할 색상 허용 오차 (0~255)
    :param feather: 반투명 페이드 범위
    :param decontaminate: 엣지 색상 프린지 제거 여부
    :param edge_erosion: 엣지 침식 픽셀 수 (잔여 프린지 제거)
    :param progress_callback: 각 파일 처리 후 호출. 시그니처:
        (index, total, input_path, output_path or None, error or None).
        한 파일이 실패해도 다음 파일을 계속 처리합니다.
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
    for i, file in enumerate(png_files, 1):
        out_file = output_path / file.name
        try:
            remove_color(str(file), str(out_file), target_color, tolerance,
                         feather, decontaminate, edge_erosion)
        except Exception as e:
            if progress_callback is not None:
                progress_callback(i, total, str(file), None, e)
            continue
        if progress_callback is not None:
            progress_callback(i, total, str(file), str(out_file), None)


if __name__ == "__main__":
    def _cli_progress(i, total, in_path, out_path, error):
        name = Path(in_path).name
        if error is not None:
            print(f"[{i}/{total}] 실패: {name} — {error}")
        else:
            print(f"[{i}/{total}] 완료: {name}")

    process_folder(
        input_dir="base",
        output_dir="alpha",
        target_color=(255, 37, 255),
        tolerance=20,
        feather=100,
        decontaminate=True,
        edge_erosion=1,
        progress_callback=_cli_progress,
    )