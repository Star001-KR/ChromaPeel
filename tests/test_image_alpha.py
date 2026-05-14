"""Unit tests for imageAlpha — algorithm correctness and folder workflow."""
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import imageAlpha


def _solid(color, size=(8, 8)):
    h, w = size
    arr = np.full((h, w, 4), [*color, 255], dtype=np.uint8)
    return arr


def _save(arr, path):
    Image.fromarray(arr).save(path)


# ---------- detect_background_color ----------

def test_detect_background_solid_border():
    arr = _solid((255, 37, 255), (10, 10))
    arr[3:7, 3:7] = [50, 200, 100, 255]  # interior differs but border is uniform
    assert imageAlpha.detect_background_color(arr) == (255, 37, 255)


def test_detect_background_picks_mode_when_border_mixed():
    """A border with mostly white and a few magenta pixels should pick white."""
    arr = _solid((255, 255, 255), (10, 10))
    # Inject a few magenta pixels on the border (count is less than white)
    arr[0, 0:3] = [255, 0, 255, 255]
    assert imageAlpha.detect_background_color(arr) == (255, 255, 255)


def test_detect_background_accepts_float_input():
    arr = _solid((10, 20, 30), (6, 6)).astype(np.float32)
    assert imageAlpha.detect_background_color(arr) == (10, 20, 30)


# ---------- detect_background_colors (multi-color, dynamic k) ----------

def test_detect_colors_single_color_returns_one():
    arr = _solid((10, 20, 30), (10, 10))
    arr[3:7, 3:7] = [50, 200, 100, 255]  # 내부만 다름
    assert imageAlpha.detect_background_colors(arr) == [(10, 20, 30)]


def test_detect_colors_two_color_border():
    """테두리가 두 색 → 두 색 모두 반환, 빈도 desc 정렬."""
    arr = np.zeros((10, 10, 4), dtype=np.uint8)
    arr[..., 3] = 255
    arr[..., :3] = [10, 20, 30]          # 전체 A 로 초기화
    arr[0, :, :3] = [200, 100, 50]       # 상단 행 1줄: 10px 가 B
    arr[-1, :, :3] = [200, 100, 50]      # 하단 행 1줄: 10px 가 B
    # 테두리 픽셀 총 36 (10+10+8+8). B = 20, A = 16 → [B, A]
    colors = imageAlpha.detect_background_colors(arr, min_ratio=0.1)
    assert colors[0] == (200, 100, 50)
    assert (10, 20, 30) in colors


def test_detect_colors_filters_below_min_ratio():
    """min_ratio 미만 색은 제외, 최빈 1개는 비율 무관 포함."""
    arr = _solid((255, 255, 255), (20, 20))
    arr[0, 0:2, :3] = [255, 37, 255]      # 마젠타 ~2/76 ≈ 2.6%
    colors = imageAlpha.detect_background_colors(arr, min_ratio=0.1)
    assert colors == [(255, 255, 255)]


def test_detect_colors_always_returns_at_least_one():
    """min_ratio 가 100% 라도 최빈 1개는 반드시 반환."""
    arr = _solid((255, 255, 255), (10, 10))
    arr[0, 0:2, :3] = [0, 0, 0]
    colors = imageAlpha.detect_background_colors(arr, min_ratio=2.0)
    assert colors == [(255, 255, 255)]


def test_detect_colors_respects_max_k():
    arr = np.zeros((9, 9, 4), dtype=np.uint8)
    arr[..., 3] = 255
    arr[:, 0:3, :3] = [10, 20, 30]
    arr[:, 3:6, :3] = [40, 50, 60]
    arr[:, 6:9, :3] = [70, 80, 90]
    colors = imageAlpha.detect_background_colors(arr, min_ratio=0.0, max_k=2)
    assert len(colors) == 2


# ---------- remove_color ----------

def test_target_color_becomes_transparent(tmp_path):
    arr = _solid((255, 37, 255), (8, 8))
    arr[3:5, 3:5] = [50, 200, 100, 255]
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)

    imageAlpha.remove_color(str(in_p), str(out_p),
                            target_color=(255, 37, 255), tolerance=10,
                            feather=0, decontaminate=False, edge_erosion=0)
    out = np.array(Image.open(out_p))
    assert out[0, 0, 3] == 0  # background became transparent
    assert out[3, 3, 3] == 255  # foreground kept opaque
    assert tuple(out[3, 3, :3]) == (50, 200, 100)  # color preserved


def test_auto_detect_when_target_is_none(tmp_path):
    arr = _solid((10, 20, 30), (8, 8))
    arr[3:5, 3:5] = [200, 200, 200, 255]
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)

    imageAlpha.remove_color(str(in_p), str(out_p),
                            target_color=None, tolerance=5,
                            feather=0, decontaminate=False, edge_erosion=0)
    out = np.array(Image.open(out_p))
    assert out[0, 0, 3] == 0  # auto-detected (10,20,30) → transparent


def test_feather_creates_partial_alpha(tmp_path):
    """A pixel whose distance is mid-feather should get an intermediate alpha."""
    arr = _solid((255, 37, 255), (4, 4))
    # Put one pixel at distance 50 from target (tolerance=10, feather=80
    # → m = (50-10)/80 = 0.5)
    arr[1, 1] = [205, 87, 205, 255]  # max channel diff = 50
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)

    imageAlpha.remove_color(str(in_p), str(out_p),
                            target_color=(255, 37, 255), tolerance=10,
                            feather=80, decontaminate=False, edge_erosion=0)
    out = np.array(Image.open(out_p))
    # 0.5 * 255 = 127.5 → truncated to 127 by .astype(uint8)
    assert out[1, 1, 3] == 127


def test_edge_erosion_eats_into_opaque(tmp_path):
    """An opaque pixel adjacent to transparent area gets erased after one pass."""
    arr = _solid((255, 37, 255), (5, 5))
    arr[2, 2] = [50, 200, 100, 255]  # single opaque pixel surrounded by background
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)

    # Without erosion, the center pixel survives.
    no_erosion_p = imageAlpha.remove_color(str(in_p), str(out_p),
                            target_color=(255, 37, 255), tolerance=10,
                            feather=0, decontaminate=False, edge_erosion=0)
    no_erosion = np.array(Image.open(no_erosion_p))
    assert no_erosion[2, 2, 3] == 255

    # With erosion=1, the center pixel is eaten. (자동 _01 회피 — 동일 경로 재사용 금지)
    eroded_p = imageAlpha.remove_color(str(in_p), str(out_p),
                            target_color=(255, 37, 255), tolerance=10,
                            feather=0, decontaminate=False, edge_erosion=1)
    eroded = np.array(Image.open(eroded_p))
    assert eroded[2, 2, 3] == 0


# ---------- remove_color: multi-color (target_colors) ----------

def test_remove_color_with_two_target_colors(tmp_path):
    """두 배경색 + 다른 전경 → 두 배경 모두 투명, 전경 보존."""
    arr = np.zeros((6, 6, 4), dtype=np.uint8)
    arr[..., 3] = 255
    arr[:3, :, :3] = [10, 20, 30]         # 상단: 색 A
    arr[3:, :, :3] = [200, 100, 50]       # 하단: 색 B
    arr[2:4, 2:4, :3] = [80, 80, 80]      # 중앙: 전경 C
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)

    imageAlpha.remove_color(str(in_p), str(out_p),
                            target_colors=[(10, 20, 30), (200, 100, 50)],
                            tolerance=5, feather=0,
                            decontaminate=False, edge_erosion=0)
    out = np.array(Image.open(out_p))
    assert out[0, 0, 3] == 0       # 색 A 영역 투명
    assert out[5, 5, 3] == 0       # 색 B 영역 투명
    assert out[2, 2, 3] == 255     # 전경 보존
    assert tuple(out[2, 2, :3]) == (80, 80, 80)


def test_remove_color_rejects_both_target_arguments(tmp_path):
    arr = _solid((255, 37, 255), (4, 4))
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)
    with pytest.raises(ValueError, match="동시"):
        imageAlpha.remove_color(str(in_p), str(out_p),
                                target_color=(255, 37, 255),
                                target_colors=[(255, 37, 255)])


def test_remove_color_rejects_empty_target_colors(tmp_path):
    arr = _solid((255, 37, 255), (4, 4))
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)
    with pytest.raises(ValueError, match="비어"):
        imageAlpha.remove_color(str(in_p), str(out_p), target_colors=[])


def test_remove_color_auto_detects_multi_colors_when_both_none(tmp_path):
    """둘 다 None → 자동 다색 감지 후 두 색 모두 투명화."""
    arr = np.zeros((10, 10, 4), dtype=np.uint8)
    arr[..., 3] = 255
    arr[:5, :, :3] = [10, 20, 30]
    arr[5:, :, :3] = [200, 100, 50]
    arr[4:6, 4:6, :3] = [80, 80, 80]
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)

    imageAlpha.remove_color(str(in_p), str(out_p),
                            target_color=None, target_colors=None,
                            tolerance=5, feather=0,
                            decontaminate=False, edge_erosion=0)
    out = np.array(Image.open(out_p))
    assert out[0, 0, 3] == 0
    assert out[9, 9, 3] == 0


def test_remove_color_decontaminate_uses_nearest_color(tmp_path):
    """다색 + feather + decontaminate 가 픽셀별 nearest target 으로 동작하는지 검증.

    상단 픽셀(색 A 근처)은 A 기준으로, 하단 픽셀(색 B 근처)은 B 기준으로
    decontamination 이 일어나야 한다.
    """
    arr = np.zeros((4, 4, 4), dtype=np.uint8)
    arr[..., 3] = 255
    arr[..., :3] = [128, 128, 128]   # 중립 회색 — A/B 양쪽 모두에서 distance 큼
    # A 와 B 양 끝 색을 직접 박아 nearest 판정을 가르도록
    arr[0, 0, :3] = [10, 20, 30]      # 색 A 자체
    arr[3, 3, :3] = [200, 100, 50]    # 색 B 자체
    # feather zone 안에 들어올 픽셀: A 에서 거리 ~30 인 픽셀
    arr[0, 1, :3] = [40, 20, 30]      # A 와 거리 30 (≤ tol+feather)
    # B 와 거리 ~30 인 픽셀
    arr[3, 2, :3] = [200, 100, 80]    # B 와 거리 30
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)

    imageAlpha.remove_color(str(in_p), str(out_p),
                            target_colors=[(10, 20, 30), (200, 100, 50)],
                            tolerance=10, feather=50,
                            decontaminate=True, edge_erosion=0)
    out = np.array(Image.open(out_p))
    # 핵심: feather 픽셀에서 nearest 색의 채널이 빠져야 함.
    # arr[0,1] 은 A 와 가깝다 → A 기준 decontaminate → R 채널이 (40 - t*10)/(1-t) 로 보정
    # arr[3,2] 는 B 와 가깝다 → B 기준 decontaminate → B 채널이 (80 - t*50)/(1-t) 로 보정
    # 두 픽셀의 alpha 가 partial (0 < α < 255) 이고 RGB 가 원본과 달라야 한다.
    assert 0 < out[0, 1, 3] < 255
    assert 0 < out[3, 2, 3] < 255
    # nearest 가 잘못 갈리면 RGB 가 원본과 동일(=영향 없음)하거나 엉뚱한 색 빠짐
    assert tuple(out[0, 1, :3]) != (40, 20, 30)
    assert tuple(out[3, 2, :3]) != (200, 100, 80)


# ---------- process_folder ----------

def test_process_folder_processes_all_pngs(tmp_path):
    in_dir, out_dir = tmp_path / "in", tmp_path / "out"
    in_dir.mkdir()
    for name in ("a.png", "b.png"):
        _save(_solid((255, 37, 255)), in_dir / name)

    events = []
    imageAlpha.process_folder(
        str(in_dir), str(out_dir),
        target_color=(255, 37, 255), tolerance=10,
        progress_callback=lambda i, n, ip, op, err: events.append((i, n, Path(ip).name, op is not None, err)),
    )
    assert (out_dir / "a.png").exists()
    assert (out_dir / "b.png").exists()
    # Default mode is parallel; completion order is non-deterministic.
    # Verify the set of events instead of strict order.
    assert {e[2] for e in events} == {"a.png", "b.png"}
    assert all(e[1] == 2 and e[3] is True and e[4] is None for e in events)
    assert sorted(e[0] for e in events) == [1, 2]


def test_process_folder_max_workers_one_preserves_order(tmp_path):
    """max_workers=1 falls back to sequential processing with deterministic callback order."""
    in_dir, out_dir = tmp_path / "in", tmp_path / "out"
    in_dir.mkdir()
    for name in ("a.png", "b.png", "c.png"):
        _save(_solid((255, 37, 255)), in_dir / name)

    events = []
    imageAlpha.process_folder(
        str(in_dir), str(out_dir),
        target_color=(255, 37, 255), tolerance=10,
        progress_callback=lambda i, n, ip, op, err: events.append((i, Path(ip).name)),
        max_workers=1,
    )
    assert events == [(1, "a.png"), (2, "b.png"), (3, "c.png")]


def test_process_folder_parallel_correctness(tmp_path):
    """Many files in parallel: every input produces an output and a success callback."""
    in_dir, out_dir = tmp_path / "in", tmp_path / "out"
    in_dir.mkdir()
    names = [f"f{i:02d}.png" for i in range(8)]
    for name in names:
        _save(_solid((255, 37, 255)), in_dir / name)

    events = []
    imageAlpha.process_folder(
        str(in_dir), str(out_dir),
        target_color=(255, 37, 255), tolerance=10,
        progress_callback=lambda i, n, ip, op, err: events.append((i, n, Path(ip).name, op is not None, err)),
        # Force >1 workers even when cpu_count is low (e.g. CI runners).
        max_workers=4,
    )
    # Every file produced an output
    for name in names:
        assert (out_dir / name).exists()
    # Every file emitted exactly one success event
    assert {e[2] for e in events} == set(names)
    assert all(e[1] == len(names) and e[3] is True and e[4] is None for e in events)
    # Indices cover 1..len(names) exactly
    assert sorted(e[0] for e in events) == list(range(1, len(names) + 1))


def test_process_folder_continues_on_per_file_failure(tmp_path):
    """A corrupt file fails its own callback but the next file still runs."""
    in_dir, out_dir = tmp_path / "in", tmp_path / "out"
    in_dir.mkdir()
    # Valid file
    _save(_solid((255, 37, 255)), in_dir / "good.png")
    # Bogus file with .png extension
    (in_dir / "bad.png").write_bytes(b"this is not a png")

    events = []
    imageAlpha.process_folder(
        str(in_dir), str(out_dir),
        target_color=(255, 37, 255), tolerance=10,
        progress_callback=lambda *args: events.append(args),
    )

    # Both files reported, bad with error, good with success
    assert len(events) == 2
    by_name = {Path(e[2]).name: e for e in events}
    assert by_name["bad.png"][3] is None       # out_path None on failure
    assert by_name["bad.png"][4] is not None   # error set
    assert by_name["good.png"][3] is not None  # out_path set on success
    assert by_name["good.png"][4] is None      # no error
    assert (out_dir / "good.png").exists()


def test_process_folder_missing_input_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        imageAlpha.process_folder(
            str(tmp_path / "does_not_exist"),
            str(tmp_path / "out"),
            target_color=(0, 0, 0),
        )


def test_process_folder_empty_input_is_noop(tmp_path):
    in_dir, out_dir = tmp_path / "in", tmp_path / "out"
    in_dir.mkdir()
    events = []
    imageAlpha.process_folder(
        str(in_dir), str(out_dir),
        target_color=(0, 0, 0),
        progress_callback=lambda *args: events.append(args),
    )
    assert events == []
    assert out_dir.is_dir()  # still created


# ---------- trim_transparent_edges (helper) ----------

def test_trim_bbox_finds_opaque_region():
    # 10x10 fully transparent canvas with a 2x2 opaque block at (3,4)..(4,5)
    arr = np.zeros((10, 10, 4), dtype=np.uint8)
    arr[4:6, 3:5, :] = [10, 20, 30, 255]
    bbox = imageAlpha.trim_transparent_edges(arr)
    assert bbox == (3, 4, 5, 6)  # (left, top, right, bottom), exclusive


def test_trim_bbox_returns_none_when_all_transparent():
    arr = np.zeros((4, 4, 4), dtype=np.uint8)
    assert imageAlpha.trim_transparent_edges(arr) is None


def test_trim_bbox_padding_clamped_to_image():
    arr = np.zeros((6, 6, 4), dtype=np.uint8)
    arr[2:4, 2:4, :] = [10, 20, 30, 255]
    # padding=1 should give (1, 1, 5, 5)
    assert imageAlpha.trim_transparent_edges(arr, padding=1) == (1, 1, 5, 5)
    # padding=10 (huge) should clamp to image bounds
    assert imageAlpha.trim_transparent_edges(arr, padding=10) == (0, 0, 6, 6)


def test_trim_bbox_alpha_threshold():
    arr = np.zeros((6, 6, 4), dtype=np.uint8)
    arr[2, 2, :] = [10, 20, 30, 50]   # semi-transparent
    arr[3, 3, :] = [10, 20, 30, 200]  # more opaque
    # threshold=0: both pixels qualify → bbox covers (2,2)..(3,3)
    assert imageAlpha.trim_transparent_edges(arr, alpha_threshold=0) == (2, 2, 4, 4)
    # threshold=100: only the 200-alpha pixel qualifies
    assert imageAlpha.trim_transparent_edges(arr, alpha_threshold=100) == (3, 3, 4, 4)


# ---------- remove_color with auto_trim ----------

def test_auto_trim_crops_transparent_edges(tmp_path):
    """An image with a small opaque region surrounded by background → output is cropped."""
    arr = _solid((255, 37, 255), (12, 12))  # all magenta background
    arr[4:7, 5:8] = [50, 200, 100, 255]  # 3x3 opaque block in the middle
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)

    imageAlpha.remove_color(str(in_p), str(out_p),
                            target_color=(255, 37, 255), tolerance=10,
                            feather=0, decontaminate=False, edge_erosion=0,
                            auto_trim=True, trim_padding=0)
    out = np.array(Image.open(out_p))
    # Cropped to the 3x3 opaque region
    assert out.shape == (3, 3, 4)
    assert (out[..., 3] == 255).all()
    assert (out[..., :3] == [50, 200, 100]).all()


def test_auto_trim_with_padding(tmp_path):
    arr = _solid((255, 37, 255), (12, 12))
    arr[4:7, 5:8] = [50, 200, 100, 255]
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)

    imageAlpha.remove_color(str(in_p), str(out_p),
                            target_color=(255, 37, 255), tolerance=10,
                            feather=0, decontaminate=False, edge_erosion=0,
                            auto_trim=True, trim_padding=1)
    out = np.array(Image.open(out_p))
    # 3x3 opaque + 1px padding on each side = 5x5
    assert out.shape == (5, 5, 4)
    # The padding ring is transparent (was magenta → alpha=0)
    assert out[0, 0, 3] == 0
    # Original opaque block sits at (1,1)..(3,3)
    assert (out[1:4, 1:4, 3] == 255).all()


def test_auto_trim_skipped_when_all_transparent(tmp_path, caplog):
    """All-transparent result should keep original dimensions and emit a warning."""
    arr = _solid((255, 37, 255), (8, 8))  # entirely background → fully transparent after removal
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)

    with caplog.at_level("WARNING"):
        imageAlpha.remove_color(str(in_p), str(out_p),
                                target_color=(255, 37, 255), tolerance=10,
                                feather=0, decontaminate=False, edge_erosion=0,
                                auto_trim=True, trim_padding=0)

    out = np.array(Image.open(out_p))
    assert out.shape == (8, 8, 4)  # not cropped
    assert (out[..., 3] == 0).all()
    assert any("자동 트림 스킵" in r.message for r in caplog.records)


def test_auto_trim_off_keeps_full_dimensions(tmp_path):
    arr = _solid((255, 37, 255), (8, 8))
    arr[3:5, 3:5] = [50, 200, 100, 255]
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)

    imageAlpha.remove_color(str(in_p), str(out_p),
                            target_color=(255, 37, 255), tolerance=10,
                            feather=0, decontaminate=False, edge_erosion=0,
                            auto_trim=False)
    out = np.array(Image.open(out_p))
    assert out.shape == (8, 8, 4)  # original size preserved


# ---------- process_folder with auto_trim ----------

def test_process_folder_propagates_auto_trim(tmp_path):
    in_dir, out_dir = tmp_path / "in", tmp_path / "out"
    in_dir.mkdir()
    arr = _solid((255, 37, 255), (10, 10))
    arr[4:6, 4:6] = [50, 200, 100, 255]
    _save(arr, in_dir / "a.png")

    imageAlpha.process_folder(
        str(in_dir), str(out_dir),
        target_color=(255, 37, 255), tolerance=10,
        auto_trim=True, trim_padding=0,
        max_workers=1,
    )
    out = np.array(Image.open(out_dir / "a.png"))
    assert out.shape == (2, 2, 4)  # cropped to the 2x2 opaque region


def test_process_folder_propagates_target_colors(tmp_path):
    """배치 API 가 target_colors 를 remove_color 까지 전달하는지 회귀 방지.

    두 배경색이 있는 이미지에서 두 색 모두 투명화, 전경은 보존되어야 한다.
    이전에 target_color (단일) 만 검증해 다색 경로가 무방비 상태였다.
    """
    in_dir, out_dir = tmp_path / "in", tmp_path / "out"
    in_dir.mkdir()
    arr = np.zeros((6, 6, 4), dtype=np.uint8)
    arr[..., 3] = 255
    arr[:3, :, :3] = [10, 20, 30]          # 상단: 색 A
    arr[3:, :, :3] = [200, 100, 50]        # 하단: 색 B
    arr[2:4, 2:4, :3] = [80, 80, 80]       # 중앙: 전경 C
    _save(arr, in_dir / "a.png")

    imageAlpha.process_folder(
        str(in_dir), str(out_dir),
        target_colors=[(10, 20, 30), (200, 100, 50)],
        tolerance=5, feather=0, decontaminate=False, edge_erosion=0,
        max_workers=1,
    )
    out = np.array(Image.open(out_dir / "a.png"))
    assert out[0, 0, 3] == 0           # 색 A 영역 투명
    assert out[5, 5, 3] == 0           # 색 B 영역 투명
    assert out[2, 2, 3] == 255         # 전경 보존
    assert tuple(out[2, 2, :3]) == (80, 80, 80)


def test_process_folder_propagates_trim_alpha_threshold(tmp_path):
    """배치 API 가 trim_alpha_threshold 를 remove_color 까지 전달하는지 회귀 방지.

    같은 입력에 대해 threshold=0 vs threshold=100 이 서로 다른 bbox 를 만들어야
    한다 — 즉 process_folder 가 인자를 단순 무시하지 않는다는 증거. 이전에는
    process_folder 시그니처에 매개변수가 없어서 항상 default 0 으로 고정됐다.
    """
    in_dir = tmp_path / "in"
    in_dir.mkdir()

    # 10x10 magenta 배경에 두 개의 부분 투명 픽셀을 직접 박는다.
    # remove_color 는 magenta 픽셀의 alpha 만 0 으로 만들고, 색상이 다른
    # 두 픽셀은 alpha 를 그대로 유지한다 → trim_alpha_threshold 만이
    # bbox 크기를 갈라놓는 변수가 된다.
    arr = _solid((255, 37, 255), (10, 10))
    arr[3, 3] = [50, 200, 100, 50]    # alpha=50 (낮음)
    arr[7, 7] = [50, 200, 100, 200]   # alpha=200 (높음)
    _save(arr, in_dir / "a.png")

    out_low = tmp_path / "out_low"
    out_high = tmp_path / "out_high"

    imageAlpha.process_folder(
        str(in_dir), str(out_low),
        target_color=(255, 37, 255), tolerance=10,
        feather=0, decontaminate=False, edge_erosion=0,
        auto_trim=True, trim_padding=0, trim_alpha_threshold=0,
        max_workers=1,
    )
    imageAlpha.process_folder(
        str(in_dir), str(out_high),
        target_color=(255, 37, 255), tolerance=10,
        feather=0, decontaminate=False, edge_erosion=0,
        auto_trim=True, trim_padding=0, trim_alpha_threshold=100,
        max_workers=1,
    )

    low = np.array(Image.open(out_low / "a.png"))
    high = np.array(Image.open(out_high / "a.png"))

    # threshold=0: 두 픽셀 모두 bbox 에 포함 → (3,3)..(7,7) inclusive → 5x5
    assert low.shape == (5, 5, 4)
    # threshold=100: alpha=50 픽셀 제외, alpha=200 픽셀만 → 1x1
    assert high.shape == (1, 1, 4)


# ---------- CLI --from-clipboard ----------

def test_cli_from_clipboard_stages_and_processes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "clipboard_utils.read_image_from_clipboard",
        lambda: Image.new("RGB", (8, 8), (255, 37, 255)),
    )
    monkeypatch.setattr(sys, "argv", ["chromapeel-cli", "--from-clipboard"])

    imageAlpha._run_cli()

    staged = list((tmp_path / "base").glob("clipboard_*.png"))
    assert len(staged) == 1
    processed = list((tmp_path / "alpha").glob("clipboard_*.png"))
    assert len(processed) == 1
    assert processed[0].name == staged[0].name
    out = np.array(Image.open(processed[0]))
    # Full magenta input → fully transparent after crop
    assert (out[..., 3] == 0).all()


def test_cli_from_clipboard_errors_when_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("clipboard_utils.read_image_from_clipboard", lambda: None)
    monkeypatch.setattr(sys, "argv", ["chromapeel-cli", "--from-clipboard"])

    with pytest.raises(SystemExit) as ei:
        imageAlpha._run_cli()
    assert ei.value.code != 0
    assert "클립보드" in capsys.readouterr().err


# ---------- CLI --target-color / --auto ----------

def test_parse_rgb_valid():
    assert imageAlpha._parse_rgb("255,37,255") == (255, 37, 255)
    assert imageAlpha._parse_rgb(" 0 , 0 , 0 ") == (0, 0, 0)


def test_parse_rgb_rejects_bad_format():
    with pytest.raises(ValueError, match="형식"):
        imageAlpha._parse_rgb("255,37")
    with pytest.raises(ValueError, match="정수"):
        imageAlpha._parse_rgb("a,b,c")
    with pytest.raises(ValueError, match="0~255"):
        imageAlpha._parse_rgb("300,0,0")


def test_cli_target_color_single(tmp_path, monkeypatch):
    """--target-color 한 번 지정 시 그 색만 제거."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path / "base"
    base.mkdir()
    _save(_solid((10, 20, 30)), base / "a.png")
    monkeypatch.setattr(
        sys, "argv", ["chromapeel-cli", "--target-color", "10,20,30"],
    )
    imageAlpha._run_cli()
    out = np.array(Image.open(tmp_path / "alpha" / "a.png"))
    assert (out[..., 3] == 0).all()  # 지정 색이 모두 투명


def test_cli_target_color_multi(tmp_path, monkeypatch):
    """--target-color 두 번 → 두 색 모두 제거."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path / "base"
    base.mkdir()
    arr = np.zeros((6, 6, 4), dtype=np.uint8)
    arr[..., 3] = 255
    arr[:3, :, :3] = [10, 20, 30]
    arr[3:, :, :3] = [200, 100, 50]
    _save(arr, base / "a.png")
    monkeypatch.setattr(
        sys, "argv",
        ["chromapeel-cli", "-t", "10,20,30", "-t", "200,100,50"],
    )
    imageAlpha._run_cli()
    out = np.array(Image.open(tmp_path / "alpha" / "a.png"))
    assert (out[..., 3] == 0).all()  # 두 색 모두 투명


def test_cli_auto_detects_background(tmp_path, monkeypatch):
    """--auto 는 테두리에서 자동 다색 감지."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path / "base"
    base.mkdir()
    arr = _solid((123, 45, 67), (10, 10))
    # 전경은 (a) tolerance+feather 밖이고 (b) edge_erosion=1 에서 살아남도록 충분히 크게.
    arr[2:8, 2:8] = [0, 255, 0, 255]
    _save(arr, base / "a.png")
    monkeypatch.setattr(sys, "argv", ["chromapeel-cli", "--auto"])
    imageAlpha._run_cli()
    out = np.array(Image.open(tmp_path / "alpha" / "a.png"))
    assert out[0, 0, 3] == 0      # 테두리 색은 자동 감지되어 투명
    assert out[5, 5, 3] == 255    # 전경 중앙 보존


def test_cli_rejects_target_color_with_auto(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "base").mkdir()
    monkeypatch.setattr(
        sys, "argv",
        ["chromapeel-cli", "--auto", "-t", "10,20,30"],
    )
    with pytest.raises(SystemExit):
        imageAlpha._run_cli()
    assert "동시에" in capsys.readouterr().err


def test_cli_rejects_invalid_target_color(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "base").mkdir()
    monkeypatch.setattr(
        sys, "argv", ["chromapeel-cli", "-t", "not,a,color"],
    )
    with pytest.raises(SystemExit):
        imageAlpha._run_cli()
    assert "정수" in capsys.readouterr().err


def test_cli_from_clipboard_handles_pil_exception(tmp_path, monkeypatch, capsys):
    """ImageGrab 예외도 traceback 없이 사용자 메시지로 종료 — 회귀 방지."""
    monkeypatch.chdir(tmp_path)

    def _raise():
        raise OSError("xclip not installed")
    import clipboard_utils
    monkeypatch.setattr(clipboard_utils.ImageGrab, "grabclipboard", _raise)
    monkeypatch.setattr(sys, "argv", ["chromapeel-cli", "--from-clipboard"])

    with pytest.raises(SystemExit) as ei:
        imageAlpha._run_cli()
    assert ei.value.code == 1
    err = capsys.readouterr().err
    assert "클립보드 읽기 실패" in err


# ---------- resolve_unique_path (자동 번호 부여 정책) ----------

def test_resolve_unique_path_returns_target_when_absent(tmp_path):
    """파일 없음 → 그대로 반환."""
    target = tmp_path / "photo.png"
    assert imageAlpha.resolve_unique_path(target) == target


def test_resolve_unique_path_first_collision_returns_01(tmp_path):
    """1 개 충돌 → _01 반환."""
    target = tmp_path / "photo.png"
    target.write_bytes(b"")
    assert imageAlpha.resolve_unique_path(target) == tmp_path / "photo_01.png"


def test_resolve_unique_path_skips_to_next_free_slot(tmp_path):
    """기존 _01..._50 점유 → _51 반환."""
    (tmp_path / "photo.png").write_bytes(b"")
    for i in range(1, 51):
        (tmp_path / f"photo_{i:02d}.png").write_bytes(b"")
    assert imageAlpha.resolve_unique_path(tmp_path / "photo.png") == \
        tmp_path / "photo_51.png"


def test_resolve_unique_path_raises_when_all_slots_taken(tmp_path):
    """_01..._99 까지 모두 존재 시 OutputNameExhaustedError raise.

    덮어쓰기 옵션은 없다 — 사용자 정책 결정 (정리 후 재시도 안내).
    """
    (tmp_path / "photo.png").write_bytes(b"")
    for i in range(1, 100):
        (tmp_path / f"photo_{i:02d}.png").write_bytes(b"")
    with pytest.raises(imageAlpha.OutputNameExhaustedError) as ei:
        imageAlpha.resolve_unique_path(tmp_path / "photo.png")
    msg = str(ei.value)
    assert "photo.png" in msg
    assert "photo_01.png" in msg
    assert "photo_99.png" in msg


def test_resolve_unique_path_preserves_multi_dot_extension(tmp_path):
    """photo.tar.gz 형태도 stem(photo.tar) + suffix(.gz) 기준으로 안전 동작."""
    target = tmp_path / "photo.tar.gz"
    target.write_bytes(b"")
    assert imageAlpha.resolve_unique_path(target) == tmp_path / "photo.tar_01.gz"


# ---------- is_output_name_exhausted (GUI 사전 체크용) ----------

def test_is_output_name_exhausted_false_when_target_absent(tmp_path):
    """파일이 아예 없으면 한계가 아님."""
    assert imageAlpha.is_output_name_exhausted(tmp_path / "photo.png") is False


def test_is_output_name_exhausted_false_with_partial_occupancy(tmp_path):
    """_01..._50 만 점유 → 51 슬롯 있음 → 한계 아님."""
    (tmp_path / "photo.png").write_bytes(b"")
    for i in range(1, 51):
        (tmp_path / f"photo_{i:02d}.png").write_bytes(b"")
    assert imageAlpha.is_output_name_exhausted(tmp_path / "photo.png") is False


def test_is_output_name_exhausted_true_when_all_slots_taken(tmp_path):
    """_99 까지 모두 점유 → 한계."""
    (tmp_path / "photo.png").write_bytes(b"")
    for i in range(1, 100):
        (tmp_path / f"photo_{i:02d}.png").write_bytes(b"")
    assert imageAlpha.is_output_name_exhausted(tmp_path / "photo.png") is True


def test_is_output_name_exhausted_consistent_with_resolve_raise(tmp_path):
    """is_output_name_exhausted=True 인 경로는 resolve_unique_path 가 raise 해야 한다."""
    (tmp_path / "photo.png").write_bytes(b"")
    for i in range(1, 100):
        (tmp_path / f"photo_{i:02d}.png").write_bytes(b"")
    target = tmp_path / "photo.png"
    assert imageAlpha.is_output_name_exhausted(target) is True
    with pytest.raises(imageAlpha.OutputNameExhaustedError):
        imageAlpha.resolve_unique_path(target)


def test_exhausted_user_message_format():
    """GUI / dialogs 가 동일한 양식을 공유하는지 — 양식 변경 시 동시에 갱신되도록."""
    msg = imageAlpha.EXHAUSTED_USER_MESSAGE.format(filename="example.png")
    assert "example.png" in msg
    assert "_01 ~ _99" in msg
    assert "기존 결과 파일을 정리" in msg


def test_remove_color_renames_when_target_exists(tmp_path):
    """remove_color 가 출력 충돌 시 _01 자동 부여하고 실제 저장 경로를 반환."""
    src = tmp_path / "in.png"
    _save(_solid((255, 37, 255), (4, 4)), src)
    out = tmp_path / "out.png"
    out.write_bytes(b"")  # 점유

    saved = imageAlpha.remove_color(str(src), str(out), target_color=(255, 37, 255))

    assert saved == tmp_path / "out_01.png"
    assert saved.exists()


def test_process_folder_auto_numbers_collisions(tmp_path):
    """폴더 처리에서 기존 출력 파일과 충돌하면 파일별로 _01 부여 + 콜백에 실제 경로 전달."""
    src_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    src_dir.mkdir()
    out_dir.mkdir()
    _save(_solid((255, 37, 255), (4, 4)), src_dir / "a.png")
    _save(_solid((255, 37, 255), (4, 4)), src_dir / "b.png")
    # a.png 만 미리 점유 → a 만 _01, b 는 원본 이름
    (out_dir / "a.png").write_bytes(b"")

    seen: list[str] = []

    def cb(i, total, in_path, out_path, error):
        assert error is None
        seen.append(Path(out_path).name)

    imageAlpha.process_folder(
        str(src_dir), str(out_dir),
        target_color=(255, 37, 255),
        progress_callback=cb, max_workers=1,
    )

    assert sorted(seen) == ["a_01.png", "b.png"]
    assert (out_dir / "a_01.png").exists()
    assert (out_dir / "b.png").exists()


def test_cli_emits_stderr_and_nonzero_exit_when_slots_exhausted(tmp_path, monkeypatch, capsys):
    """폴더 처리에서 _99 까지 다 차 있으면 stderr 에 안내 + non-zero exit."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "base").mkdir()
    (tmp_path / "alpha").mkdir()
    _save(_solid((255, 37, 255), (4, 4)), tmp_path / "base" / "photo.png")
    # alpha/photo.png 와 _01.._99 모두 점유
    (tmp_path / "alpha" / "photo.png").write_bytes(b"")
    for i in range(1, 100):
        (tmp_path / "alpha" / f"photo_{i:02d}.png").write_bytes(b"")

    monkeypatch.setattr(sys, "argv", ["chromapeel-cli"])
    with pytest.raises(SystemExit) as ei:
        imageAlpha._run_cli()
    assert ei.value.code == 1
    err = capsys.readouterr().err
    assert "photo.png" in err
    assert "photo_99.png" in err
    assert "Traceback" not in err
