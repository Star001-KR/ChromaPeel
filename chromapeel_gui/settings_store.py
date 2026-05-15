"""사용자 설정 영구 저장 — ~/.chromapeel/settings.json.

GUI 종료 시 마지막으로 사용한 알고리즘 파라미터를 저장하고, 다음 실행 때
복원한다. 비어 있거나 손상된 파일은 조용히 default 로 fallback — 사용자에게
에러를 띄우지 않는다 (1차 범위: 설정 복원은 편의 기능이며 실패해도 앱은 동작해야 함).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from imageAlpha import (
    APP_DEFAULT_AUTO_TRIM,
    APP_DEFAULT_DECONTAMINATE,
    APP_DEFAULT_EDGE_EROSION,
    APP_DEFAULT_FEATHER,
    APP_DEFAULT_TARGET_COLOR,
    APP_DEFAULT_TOLERANCE,
    APP_DEFAULT_TRIM_PADDING,
)

logger = logging.getLogger(__name__)

DEFAULT_AUTO_DETECT_BG = False

SETTINGS_PATH = Path.home() / ".chromapeel" / "settings.json"


def default_settings() -> dict[str, Any]:
    return {
        "target_colors": [list(APP_DEFAULT_TARGET_COLOR)],
        "tolerance": APP_DEFAULT_TOLERANCE,
        "feather": APP_DEFAULT_FEATHER,
        "decontaminate": APP_DEFAULT_DECONTAMINATE,
        "edge_erosion": APP_DEFAULT_EDGE_EROSION,
        "auto_detect_bg": DEFAULT_AUTO_DETECT_BG,
        "auto_trim": APP_DEFAULT_AUTO_TRIM,
        "trim_padding": APP_DEFAULT_TRIM_PADDING,
    }


def _coerce_rgb(item: Any) -> tuple[int, int, int] | None:
    if not isinstance(item, (list, tuple)) or len(item) != 3:
        return None
    try:
        r, g, b = (int(c) for c in item)
    except (TypeError, ValueError):
        return None
    if not all(0 <= c <= 255 for c in (r, g, b)):
        return None
    return (r, g, b)


def _coerce_int(value: Any, lo: int, hi: int, fallback: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return fallback
    if n < lo:
        return lo
    if n > hi:
        return hi
    return n


def _coerce_bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    return fallback


def normalize(raw: Any) -> dict[str, Any]:
    """raw dict (JSON parsed) → 검증된 settings dict. 누락/형식 오류는 default 로.

    target_colors 는 list[tuple[int,int,int]] 로 변환되며, 한 개도 valid 하지 않으면
    default 한 개로 fallback (앱이 빈 색 리스트 상태로 시작되는 걸 막기 위함).
    """
    defaults = default_settings()
    if not isinstance(raw, dict):
        return defaults

    out: dict[str, Any] = {}

    colors_raw = raw.get("target_colors")
    coerced_colors: list[tuple[int, int, int]] = []
    if isinstance(colors_raw, list):
        for item in colors_raw:
            rgb = _coerce_rgb(item)
            if rgb is not None:
                coerced_colors.append(rgb)
    if not coerced_colors:
        coerced_colors = [tuple(APP_DEFAULT_TARGET_COLOR)]
    out["target_colors"] = coerced_colors

    out["tolerance"] = _coerce_int(
        raw.get("tolerance"), 0, 255, defaults["tolerance"]
    )
    out["feather"] = _coerce_int(
        raw.get("feather"), 0, 300, defaults["feather"]
    )
    out["edge_erosion"] = _coerce_int(
        raw.get("edge_erosion"), 0, 10, defaults["edge_erosion"]
    )
    out["trim_padding"] = _coerce_int(
        raw.get("trim_padding"), 0, 200, defaults["trim_padding"]
    )
    out["decontaminate"] = _coerce_bool(
        raw.get("decontaminate"), defaults["decontaminate"]
    )
    out["auto_detect_bg"] = _coerce_bool(
        raw.get("auto_detect_bg"), defaults["auto_detect_bg"]
    )
    out["auto_trim"] = _coerce_bool(
        raw.get("auto_trim"), defaults["auto_trim"]
    )
    return out


def load_settings(path: Path = SETTINGS_PATH) -> dict[str, Any]:
    """settings.json 을 읽어 normalize 한 dict 반환. 실패 시 default."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return default_settings()
    except (OSError, UnicodeDecodeError) as e:
        # UnicodeDecodeError(ValueError 계열)는 except OSError 로 안 잡힌다 — 비UTF-8 로
        # 손상된 파일에서 raise 되면 GUI __init__ 의 load_settings 가 부팅을 막는다.
        logger.warning("설정 파일 읽기 실패: %s — default 사용", e)
        return default_settings()

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("설정 파일 JSON 파싱 실패: %s — default 사용", e)
        return default_settings()

    return normalize(raw)


def save_settings(data: dict[str, Any], path: Path = SETTINGS_PATH) -> None:
    """settings dict 를 JSON 으로 저장. 실패는 로그만 (사용자에게 노출 X).

    임시 파일에 먼저 쓴 뒤 os.replace 로 교체한다 — 쓰기 도중 프로세스가 강제
    종료돼도 기존 settings.json 이 부분 쓰기로 손상되지 않는다 (불완전한 멀티바이트
    시퀀스로 끝나는 비UTF-8 파일이 다음 부팅의 load_settings 를 깨뜨리는 것 방지).

    target_colors 가 tuple 이어도 list 로 직렬화된다 (json.dumps 가 자동).
    """
    serializable = normalize(data)
    serializable["target_colors"] = [list(rgb) for rgb in serializable["target_colors"]]
    payload = json.dumps(serializable, indent=2, ensure_ascii=False)

    tmp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # 임시 파일은 대상과 같은 디렉토리에 — os.replace 가 동일 파일시스템에서만
        # 원자적이기 때문.
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent,
            prefix=".settings-", suffix=".tmp", delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(payload)
        os.replace(tmp_path, path)
    except OSError as e:
        logger.warning("설정 파일 저장 실패: %s — 무시", e)
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
