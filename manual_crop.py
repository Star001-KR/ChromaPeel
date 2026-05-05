"""수동 크롭 — 사각형 영역을 잘라내 저장하는 독립 도구."""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def crop_image(
    input_path: str,
    x: int,
    y: int,
    w: int,
    h: int,
    out_dir: str = "alpha",
) -> Path:
    """이미지의 (x, y, w, h) 영역을 잘라내 PNG로 저장합니다.

    :param input_path: 입력 이미지 경로
    :param x: 좌상단 x 좌표 (픽셀, 좌상단 원점 0,0)
    :param y: 좌상단 y 좌표 (픽셀)
    :param w: 영역 너비 (양수)
    :param h: 영역 높이 (양수)
    :param out_dir: 출력 폴더 (없으면 자동 생성). 기본 "alpha"
    :return: 저장된 출력 파일 경로
    :raises ValueError: w/h가 0 이하이거나, 클램프 후 영역이 비는 경우
    """
    if w <= 0 or h <= 0:
        raise ValueError("width/height must be positive")

    img = Image.open(input_path)

    left = max(0, x)
    top = max(0, y)
    right = min(img.width, x + w)
    bottom = min(img.height, y + h)

    if right - left <= 0 or bottom - top <= 0:
        raise ValueError("width/height must be positive")

    cropped = img.crop((left, top, right, bottom))

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    stem = Path(input_path).stem
    out_file = out_path / f"{stem}_crop.png"
    cropped.save(out_file, "PNG")
    return out_file


def _parse_crop(value: str) -> tuple:
    parts = value.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            "--crop must be 4 comma-separated integers: X,Y,W,H"
        )
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "--crop must be 4 comma-separated integers: X,Y,W,H"
        )


def _run_cli() -> None:
    parser = argparse.ArgumentParser(
        prog="chromapeel-crop",
        description="이미지에서 직사각형 영역을 잘라냅니다.",
    )
    parser.add_argument("input", help="입력 이미지 경로")
    parser.add_argument(
        "--crop",
        required=True,
        type=_parse_crop,
        metavar="X,Y,W,H",
        help="크롭 영역 (콤마 구분 4개 정수)",
    )
    parser.add_argument(
        "--out-dir",
        default="alpha",
        help='출력 폴더 (기본 "alpha")',
    )
    args = parser.parse_args()

    x, y, w, h = args.crop
    out_file = crop_image(args.input, x, y, w, h, out_dir=args.out_dir)
    print(f"saved: {out_file}")


if __name__ == "__main__":
    _run_cli()
