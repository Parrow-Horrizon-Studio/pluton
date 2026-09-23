"""Theme selection, and the icon refresh that #101 reports missing."""

import pytest
from pluton.ui import icons, preferences
from pluton.ui.theme import ThemeChoice, apply_theme, theme_for_name
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)


def test_light_is_the_default_theme(settings):
    """SketchUp is light on every OS regardless of system setting (spec D7)."""
    assert theme_for_name(preferences.read_theme(settings)) is ThemeChoice.LIGHT


def test_theme_for_name_maps_both_values():
    assert theme_for_name("light") is ThemeChoice.LIGHT
    assert theme_for_name("dark") is ThemeChoice.DARK


def test_theme_for_name_falls_back_rather_than_raising():
    """Review Focus 4.

    ThemeChoice("mauve") raises ValueError, and this is read during startup
    before the window exists, so it must not be able to stop the app opening.
    """
    assert theme_for_name("mauve") is ThemeChoice.LIGHT
    assert theme_for_name(None) is ThemeChoice.LIGHT
    assert theme_for_name("") is ThemeChoice.LIGHT


def test_apply_theme_sets_the_qt_colour_scheme(app):
    apply_theme(app, ThemeChoice.DARK)
    assert app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    apply_theme(app, ThemeChoice.LIGHT)
    assert app.styleHints().colorScheme() == Qt.ColorScheme.Light


def test_the_icon_cache_is_keyed_on_colour_so_a_stale_entry_is_reachable(app):
    """The mechanism behind #101, stated as a test so the fix has a target.

    icon() caches on (stem, colour). Rebuilding from a palette Qt has not
    swapped yet re-caches the OLD colour, and because the entry is then present
    the next request returns it too, so the theme switch appears to do nothing
    until restart. That is exactly the symptom #101 reports.
    """
    from PySide6.QtGui import QColor

    icons.clear_icon_cache()
    light = icons.icon("file_new", QColor("#3c3c3c"))
    dark = icons.icon("file_new", QColor("#f0f0f0"))
    assert light is not dark
    assert icons.icon("file_new", QColor("#3c3c3c")) is light


def test_a_palette_change_re_tints_the_properties_tab_strip(app):
    """Review Focus 5, and the half of the fix that gets forgotten.

    The tab strip is built once in PropertiesDock.__init__ and never rebuilt, so
    nothing would re-request its icons and every tab would keep the previous
    theme's ink. That is a partial fix that looks complete from the toolbar.

    Asserted at the CURRENT palette colour rather than merely "is in the cache":
    the cache is keyed on (stem, colour), so a version that warmed the cache at
    the old colour would satisfy a presence check and still show stale icons.

    Discriminates: drop the _properties_dock.refresh_icons call from
    _rebuild_all_icons and this fails.
    """
    from pluton.ui.main_window import MainWindow
    from pluton.ui.panel_icons import TAB_ICONS

    window = MainWindow()
    icons.clear_icon_cache()
    window._rebuild_all_icons()
    color_name = window.palette().windowText().color().name()
    cached_at_current = {stem for stem, color in icons._icon_cache if color == color_name}
    missing = TAB_ICONS - cached_at_current
    assert not missing, f"tab icons not re-tinted at the new colour: {sorted(missing)}"


def test_a_palette_change_rebuilds_the_outliner(app, monkeypatch):
    """The Outliner's other half of the same problem, by a different mechanism.

    It sets each row's icon inside set_rows, reading the palette at that moment,
    so it needs a rebuild rather than a re-tint method. An empty model has no
    rows and therefore caches no row icons, so this pins the rebuild call itself
    instead of asserting over the cache.

    Discriminates: drop the _rebuild_outliner call and this fails.
    """
    from pluton.ui.main_window import MainWindow

    window = MainWindow()
    calls = []
    monkeypatch.setattr(window, "_rebuild_outliner", lambda: calls.append(1))
    window._rebuild_all_icons()
    assert calls == [1]


def test_a_palette_change_re_tints_the_action_icons(app):
    """The registry half, so the tests above cannot pass alone."""
    from pluton.ui import actions
    from pluton.ui.main_window import MainWindow

    window = MainWindow()
    icons.clear_icon_cache()
    window._rebuild_all_icons()
    color_name = window.palette().windowText().color().name()
    cached_at_current = {stem for stem, color in icons._icon_cache if color == color_name}
    expected = {spec.icon for spec in actions.ACTIONS if spec.icon is not None}
    assert expected <= cached_at_current
