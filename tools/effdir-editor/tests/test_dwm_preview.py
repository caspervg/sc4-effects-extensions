from effdir_editor.ui.dwm_preview import _fit_rect


def test_fit_rect_preserves_widescreen_aspect_ratio() -> None:
    assert _fit_rect(0, 0, 420, 280, 1920, 1080) == (0, 22, 420, 258)
