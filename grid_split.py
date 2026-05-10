"""격자 분할(grid split): PNG를 균등 셀 격자로 자른다.

두 가지 모드:
- Mode A — Rows × Cols: 이미지를 N×M 격자로 균등 분할 (셀 크기는 이미지 크기에서 유도).
- Mode B — Cell W × H: 고정 크기 셀로 타일링 (rows/cols는 이미지 크기에서 유도).

두 모드 모두 우/하단 잔여 픽셀은 잘라낸다(clip). 리사이즈는 하지 않는다.
"""
from pathlib import Path
from typing import List, Optional, Tuple, TypedDict

import argparse
import sys

from PIL import Image

__version__ = "0.2.0"


class GridSplitResult(TypedDict):
    files: List[Path]
    rows: int
    cols: int
    cell_w: int
    cell_h: int
    clipped: Tuple[int, int]


def _validate_mode(
    rows: Optional[int],
    cols: Optional[int],
    cell_w: Optional[int],
    cell_h: Optional[int],
) -> str:
    a_set = rows is not None or cols is not None
    b_set = cell_w is not None or cell_h is not None
    if a_set and b_set:
        raise ValueError(
            "Mode A(rows/cols)와 Mode B(cell_w/cell_h)를 함께 지정할 수 없습니다"
        )
    if not a_set and not b_set:
        raise ValueError(
            "rows/cols 또는 cell_w/cell_h 중 하나의 모드를 지정해야 합니다"
        )
    if a_set:
        if rows is None or cols is None:
            raise ValueError("Mode A는 rows와 cols를 둘 다 지정해야 합니다")
        if rows <= 0 or cols <= 0:
            raise ValueError("rows, cols는 1 이상이어야 합니다")
        return "A"
    if cell_w is None or cell_h is None:
        raise ValueError("Mode B는 cell_w와 cell_h를 둘 다 지정해야 합니다")
    if cell_w <= 0 or cell_h <= 0:
        raise ValueError("cell_w, cell_h는 1 이상이어야 합니다")
    return "B"


def split_image_grid(
    image_path: str,
    output_dir: str,
    *,
    rows: Optional[int] = None,
    cols: Optional[int] = None,
    cell_w: Optional[int] = None,
    cell_h: Optional[int] = None,
) -> GridSplitResult:
    """입력 PNG를 격자 분할해 output_dir에 저장한다.

    Mode A — rows와 cols 둘 다 지정 (cell_w/cell_h는 None):
        cell_w = W // cols, cell_h = H // rows. 우/하단 잔여는 clip.
    Mode B — cell_w와 cell_h 둘 다 지정 (rows/cols는 None):
        rows = H // cell_h, cols = W // cell_w. 우/하단 잔여는 clip.

    혼합/미지정/0이하 인자는 ValueError. Mode B에서 이미지가 셀보다 작으면 ValueError.
    """
    mode = _validate_mode(rows, cols, cell_w, cell_h)

    img = Image.open(image_path)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    W, H = img.size
    if W == 0 or H == 0:
        raise ValueError(f"입력 이미지 크기가 유효하지 않습니다: {W}x{H}")

    if mode == "A":
        n_rows, n_cols = rows, cols  # type: ignore[assignment]
        c_w = W // n_cols
        c_h = H // n_rows
        if c_w == 0 or c_h == 0:
            raise ValueError(
                f"이미지({W}x{H})가 격자({n_rows}x{n_cols})를 만들기에 너무 작습니다"
            )
    else:
        c_w, c_h = cell_w, cell_h  # type: ignore[assignment]
        n_cols = W // c_w
        n_rows = H // c_h
        if n_rows == 0 or n_cols == 0:
            raise ValueError(
                f"이미지({W}x{H})가 셀 크기({c_w}x{c_h})보다 작습니다"
            )

    clipped = (W - c_w * n_cols, H - c_h * n_rows)

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    stem = Path(image_path).stem
    pad = len(str(max(n_rows, n_cols)))

    files: List[Path] = []
    for r in range(n_rows):
        for c in range(n_cols):
            x0 = c * c_w
            y0 = r * c_h
            cell = img.crop((x0, y0, x0 + c_w, y0 + c_h))
            name = f"{stem}_r{r:0{pad}d}c{c:0{pad}d}.png"
            target = out_path / name
            cell.save(target, "PNG")
            files.append(target)

    return {
        "files": files,
        "rows": n_rows,
        "cols": n_cols,
        "cell_w": c_w,
        "cell_h": c_h,
        "clipped": clipped,
    }


def _stage_clipboard_image(staging_dir: str = "base") -> Path:
    """CLI 진입점에서 호출. 실패 시 사용자 메시지 출력 후 sys.exit(1)."""
    from clipboard_utils import ClipboardImageError, stage_clipboard_image

    try:
        return stage_clipboard_image(staging_dir)
    except ClipboardImageError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chromapeel-split",
        description="PNG 이미지를 균등 셀 격자로 분할합니다.",
    )
    parser.add_argument("input_path", nargs="?", default=None, help="입력 PNG 경로")
    parser.add_argument(
        "--from-clipboard", action="store_true", dest="from_clipboard",
        help="클립보드의 이미지를 base/ 에 저장한 뒤 분할 입력으로 사용합니다.",
    )
    parser.add_argument(
        "-o", "--output", default="alpha",
        help="출력 디렉토리 (기본: alpha). 내부에 {stem}_split/ 하위 폴더가 생성됩니다.",
    )
    parser.add_argument("--rows", type=int, default=None, help="Mode A 행 수")
    parser.add_argument("--cols", type=int, default=None, help="Mode A 열 수")
    parser.add_argument(
        "--cell-w", type=int, default=None, dest="cell_w",
        help="Mode B 셀 너비 (픽셀)",
    )
    parser.add_argument(
        "--cell-h", type=int, default=None, dest="cell_h",
        help="Mode B 셀 높이 (픽셀)",
    )
    return parser


def _run_cli(argv: Optional[List[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    input_set = args.input_path is not None
    if args.from_clipboard and input_set:
        parser.error("input_path와 --from-clipboard를 함께 지정할 수 없습니다")
    if not args.from_clipboard and not input_set:
        parser.error("input_path 또는 --from-clipboard 중 하나를 지정해야 합니다")

    a_set = args.rows is not None or args.cols is not None
    b_set = args.cell_w is not None or args.cell_h is not None
    if a_set and b_set:
        parser.error("--rows/--cols와 --cell-w/--cell-h를 함께 지정할 수 없습니다")
    if not a_set and not b_set:
        parser.error("--rows/--cols 또는 --cell-w/--cell-h 중 하나를 지정해야 합니다")
    if a_set and (args.rows is None or args.cols is None):
        parser.error("Mode A는 --rows와 --cols를 둘 다 지정해야 합니다")
    if b_set and (args.cell_w is None or args.cell_h is None):
        parser.error("Mode B는 --cell-w와 --cell-h를 둘 다 지정해야 합니다")

    if args.from_clipboard:
        args.input_path = str(_stage_clipboard_image("base"))

    stem = Path(args.input_path).stem
    out_dir = Path(args.output) / f"{stem}_split"

    try:
        result = split_image_grid(
            args.input_path,
            str(out_dir),
            rows=args.rows,
            cols=args.cols,
            cell_w=args.cell_w,
            cell_h=args.cell_h,
        )
    except ValueError as e:
        print(f"인자 오류: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1

    cw, ch = result["clipped"]
    print(
        f"완료: {len(result['files'])}개 파일을 {out_dir} 에 저장했습니다. "
        f"격자: {result['rows']}×{result['cols']}, "
        f"셀: {result['cell_w']}×{result['cell_h']}px. "
        f"잔여: {cw}×{ch}px."
    )
    return 0


if __name__ == "__main__":
    sys.exit(_run_cli())
