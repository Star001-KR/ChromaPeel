"""chromapeel_gui.settings_store 회귀 테스트.

GUI 종료 시 마지막 알고리즘 파라미터를 ~/.chromapeel/settings.json 에 저장하고
다음 실행에 복원하는 동작을 보장한다. 손상된 파일 / 누락된 키 / 형식 오류에서
조용히 default 로 fallback 하는 것이 핵심 안전 속성.
"""
from __future__ import annotations

import json

from chromapeel_gui.settings_store import (
    default_settings,
    load_settings,
    normalize,
    save_settings,
)


def test_load_missing_file_returns_default(tmp_path):
    path = tmp_path / "settings.json"
    assert not path.exists()
    assert load_settings(path) == default_settings()


def test_load_corrupt_json_returns_default(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("not json", encoding="utf-8")
    assert load_settings(path) == default_settings()


def test_load_non_dict_top_level_returns_default(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert load_settings(path) == default_settings()


def test_save_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "deep" / "settings.json"
    save_settings(default_settings(), path)
    assert path.exists()


def test_round_trip_all_fields(tmp_path):
    path = tmp_path / "settings.json"
    data = {
        "target_colors": [(123, 45, 67)],
        "tolerance": 80,
        "feather": 12,
        "decontaminate": False,
        "edge_erosion": 3,
        "auto_detect_bg": True,
        "auto_trim": False,
        "trim_padding": 50,
    }
    save_settings(data, path)
    loaded = load_settings(path)
    assert loaded["target_colors"] == [(123, 45, 67)]
    assert loaded["tolerance"] == 80
    assert loaded["feather"] == 12
    assert loaded["decontaminate"] is False
    assert loaded["edge_erosion"] == 3
    assert loaded["auto_detect_bg"] is True
    assert loaded["auto_trim"] is False
    assert loaded["trim_padding"] == 50


def test_round_trip_multi_color(tmp_path):
    """다색 chroma key 사용자 — target_colors 가 여러 개 보존돼야 함."""
    path = tmp_path / "settings.json"
    data = default_settings()
    data["target_colors"] = [(255, 255, 255), (0, 0, 0), (128, 64, 32)]
    save_settings(data, path)
    loaded = load_settings(path)
    assert loaded["target_colors"] == [(255, 255, 255), (0, 0, 0), (128, 64, 32)]


def test_empty_target_colors_falls_back_to_default(tmp_path):
    """빈 색 리스트는 default 한 개로 복원돼야 — 앱이 빈 색 상태로 시작 못 함."""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"target_colors": []}), encoding="utf-8")
    loaded = load_settings(path)
    assert len(loaded["target_colors"]) >= 1


def test_invalid_color_entries_dropped(tmp_path):
    """일부 색만 valid 한 경우 valid 한 것만 남기고, 모두 invalid 면 default."""
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({
            "target_colors": [
                [255, 0, 0],
                "garbage",
                [256, 0, 0],
                [10, 20, 30],
                [1, 2],
            ]
        }),
        encoding="utf-8",
    )
    loaded = load_settings(path)
    assert loaded["target_colors"] == [(255, 0, 0), (10, 20, 30)]


def test_int_out_of_range_clamped(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({
            "tolerance": 9999,
            "feather": -50,
            "edge_erosion": 100,
            "trim_padding": 500,
        }),
        encoding="utf-8",
    )
    loaded = load_settings(path)
    assert loaded["tolerance"] == 255
    assert loaded["feather"] == 0
    assert loaded["edge_erosion"] == 10
    assert loaded["trim_padding"] == 200


def test_non_int_value_falls_back(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"tolerance": "abc", "feather": None}),
        encoding="utf-8",
    )
    loaded = load_settings(path)
    defaults = default_settings()
    assert loaded["tolerance"] == defaults["tolerance"]
    assert loaded["feather"] == defaults["feather"]


def test_non_bool_value_falls_back(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({
            "decontaminate": "yes",
            "auto_detect_bg": 1,
            "auto_trim": "true",
        }),
        encoding="utf-8",
    )
    loaded = load_settings(path)
    defaults = default_settings()
    assert loaded["decontaminate"] is defaults["decontaminate"]
    assert loaded["auto_detect_bg"] is defaults["auto_detect_bg"]
    assert loaded["auto_trim"] is defaults["auto_trim"]


def test_missing_keys_use_defaults(tmp_path):
    """일부 키만 있는 부분 dict — 나머지는 default 로 채움."""
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"tolerance": 42}),
        encoding="utf-8",
    )
    loaded = load_settings(path)
    defaults = default_settings()
    assert loaded["tolerance"] == 42
    assert loaded["feather"] == defaults["feather"]
    assert loaded["decontaminate"] == defaults["decontaminate"]


def test_save_silently_ignores_oserror(tmp_path, monkeypatch):
    """디렉토리 생성 실패 / write 실패는 사용자에게 노출되지 않아야 함."""
    path = tmp_path / "sub" / "settings.json"

    from chromapeel_gui import settings_store

    def boom(self, *args, **kwargs):
        raise PermissionError("no write")

    monkeypatch.setattr(
        settings_store.Path, "write_text", boom, raising=True
    )
    # raise 없이 통과해야 한다
    save_settings(default_settings(), path)


def test_normalize_idempotent():
    """normalize(normalize(x)) == normalize(x) — 저장/로드 round-trip 안전."""
    sample = {
        "target_colors": [[1, 2, 3]],
        "tolerance": 100,
        "feather": 5,
        "decontaminate": True,
        "edge_erosion": 2,
        "auto_detect_bg": False,
        "auto_trim": True,
        "trim_padding": 20,
    }
    once = normalize(sample)
    twice = normalize(once)
    assert once == twice


def test_save_writes_target_colors_as_lists(tmp_path):
    """JSON 파일 안에서 target_colors 는 list-of-lists 로 직렬화돼야 한다."""
    path = tmp_path / "settings.json"
    data = default_settings()
    data["target_colors"] = [(10, 20, 30), (40, 50, 60)]
    save_settings(data, path)
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["target_colors"] == [[10, 20, 30], [40, 50, 60]]
