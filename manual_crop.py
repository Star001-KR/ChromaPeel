"""수동 크롭 — 사각형 영역을 잘라내 저장하는 독립 도구."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image


def _stage_clipboard_image(staging_dir: str = "base") -> Path:
    from datetime import datetime
    from clipboard_utils import read_image_from_clipboard

    img = read_image_from_clipboard()
    if img is None:
        print("클립보드에 이미지가 없습니다.", file=sys.stderr)
        sys.exit(1)
    out_dir = Path(staging_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"clipboard_{ts}.png"
    img.save(out, "PNG")
    return out


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
    parser.add_argument("input", nargs="?", default=None, help="입력 이미지 경로")
    parser.add_argument(
        "--from-clipboard", action="store_true", dest="from_clipboard",
        help="클립보드의 이미지를 base/ 에 저장한 뒤 크롭 입력으로 사용합니다.",
    )
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

    input_set = args.input is not None
    if args.from_clipboard and input_set:
        parser.error("input과 --from-clipboard를 함께 지정할 수 없습니다")
    if not args.from_clipboard and not input_set:
        parser.error("input 또는 --from-clipboard 중 하나를 지정해야 합니다")

    if args.from_clipboard:
        args.input = str(_stage_clipboard_image("base"))

    x, y, w, h = args.crop
    out_file = crop_image(args.input, x, y, w, h, out_dir=args.out_dir)
    print(f"saved: {out_file}")


if __name__ == "__main__":
    _run_cli()
