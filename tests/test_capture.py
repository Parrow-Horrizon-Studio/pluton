from pluton.model.tag import TagLibrary
from pluton.viewport.camera import Camera
from pluton.viewport.render_style import FaceStyle, RenderStyle
from pluton.views.capture import apply_tags_and_style, apply_view, capture_view


def _tags():
    lib = TagLibrary()
    lib.add("Walls")   # id 1
    lib.add("Roof")    # id 2
    return lib


def test_capture_snapshots_camera_tags_and_style():
    cam = Camera()
    cam.position[:] = (5.0, 6.0, 7.0)
    tags = _tags()
    tags.set_visible(2, False)   # hide Roof
    style = RenderStyle(face_style=FaceStyle.WIREFRAME, xray=True)

    v = capture_view(0, "Test", cam, tags, style)

    assert v.id == 0 and v.name == "Test"
    assert v.camera.position == (5.0, 6.0, 7.0)
    assert v.face_style == "WIREFRAME"
    assert v.xray is True
    # Untagged (id 0) is excluded; Walls visible, Roof hidden.
    assert v.tag_visibility == {1: True, 2: False}


def test_apply_view_restores_all_three():
    tags = _tags()
    style = RenderStyle()
    v = capture_view(0, "V", _capture_source_camera(), _hidden_roof_tags(),
                     RenderStyle(face_style=FaceStyle.MONOCHROME, xray=True))
    cam = Camera()
    apply_view(v, cam, tags, style)
    assert tuple(float(x) for x in cam.position) == (9.0, 0.0, 0.0)
    assert tags.is_visible(2) is False
    assert style.face_style is FaceStyle.MONOCHROME
    assert style.xray is True


def test_apply_tolerates_unknown_tag_id():
    tags = TagLibrary()          # only Untagged exists
    style = RenderStyle()
    cam = Camera()
    v = capture_view(0, "V", cam, tags, style)
    # Inject a stale id that no longer exists in this library:
    from pluton.views.saved_view import SavedView
    stale = SavedView(v.id, v.name, v.camera, {999: False}, v.face_style,
                      v.xray)
    apply_view(stale, cam, tags, style)   # must not raise
    assert tags.is_visible(999) is True   # unknown id → treated visible (no-op)


def _capture_source_camera():
    cam = Camera()
    cam.position[:] = (9.0, 0.0, 0.0)
    return cam


def _hidden_roof_tags():
    lib = _tags()
    lib.set_visible(2, False)
    return lib
