"""GUI dialog modal package.

기존에는 ``chromapeel_gui/dialogs.py`` 단일 파일에 GridSplitDialog (425 LOC) +
ManualCropDialog (454 LOC) 가 모여 있어 review / 변경 부담이 컸다. 패키지로
분리하면서 두 다이얼로그가 공유하는 클립보드 paste 흐름은 ``_clipboard.py`` 의
``ClipboardPasteMixin`` 으로 추출했다.

외부 import 경로는 그대로 유지된다 — 즉 ``from chromapeel_gui.dialogs import
GridSplitDialog, ManualCropDialog`` 가 분리 전후 모두 동작한다.
"""
from ._clipboard import _cleanup_clip_tempdir
from .grid_split import GridSplitDialog
from .manual_crop import ManualCropDialog

__all__ = ["GridSplitDialog", "ManualCropDialog", "_cleanup_clip_tempdir"]
