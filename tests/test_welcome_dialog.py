"""The welcome dialog: the accept sequence, and that dismissal changes nothing."""

import pytest
from pluton.document import DocumentSettings
from pluton.templates import template_for_key
from pluton.ui import preferences
from pluton.ui.welcome_dialog import WelcomeDialog, apply_template
from pluton.units import UnitSystem
from pluton.viewport.environment import PLAIN_WHITE, SKY_AND_GROUND
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)


def test_applying_a_template_sets_both_units_and_environment():
    doc = DocumentSettings()
    apply_template(doc, template_for_key("documentation"), "m")
    assert doc.environment == PLAIN_WHITE
    assert doc.units.metric_unit == "m"


def test_the_unit_override_keeps_the_templates_precision():
    """The two axes have to compose.

    Architectural is mm at precision 0. Choosing metres must change the unit and
    leave the precision alone, because set_metric preserves the fields it does
    not name. A reimplementation that rebuilt Units from scratch would silently
    reset precision to the dataclass default of 3.

    Discriminates: replace the set_metric call in apply_template with
    doc.set_units(Units(system=METRIC, metric_unit=unit)) and this fails.
    """
    doc = DocumentSettings()
    apply_template(doc, template_for_key("architectural"), "m")
    assert doc.units.metric_unit == "m"
    assert doc.units.metric_precision == 0


def test_the_unit_override_keeps_the_templates_denominator():
    doc = DocumentSettings()
    apply_template(doc, template_for_key("woodworking"), "in")
    assert doc.units.system is UnitSystem.IMPERIAL
    assert doc.units.imperial_denominator == 16


def test_applying_a_template_with_its_own_unit_is_a_no_op_on_units():
    doc = DocumentSettings()
    apply_template(doc, template_for_key("architectural"), "mm")
    assert doc.units.metric_unit == "mm"
    assert doc.units.metric_precision == 0


def test_the_dialog_starts_on_the_stored_default_template(app, settings):
    preferences.write_default_template(settings, "studio")
    dialog = WelcomeDialog(settings)
    assert dialog.selected_template.key == "studio"


def test_the_dialog_falls_back_when_the_stored_template_is_unknown(app, settings):
    """Review Focus 3, through the dialog rather than the table."""
    settings.setValue(preferences.DEFAULT_TEMPLATE_PREF_KEY, "no_such_template")
    dialog = WelcomeDialog(settings)
    assert dialog.selected_template.key == "architectural"


def test_the_units_selector_starts_from_the_template(app, settings):
    preferences.write_default_template(settings, "architectural")
    dialog = WelcomeDialog(settings)
    assert dialog.selected_unit == "mm"


def test_ticking_do_not_show_reports_it(app, settings):
    dialog = WelcomeDialog(settings)
    dialog._show_checkbox.setChecked(False)
    assert dialog.show_on_startup is False


def test_the_checkbox_starts_ticked_when_nothing_is_stored(app, settings):
    """Default-true, matching preferences.read_show_welcome's own default."""
    dialog = WelcomeDialog(settings)
    assert dialog.show_on_startup is True


def test_the_checkbox_starts_unticked_when_the_stored_preference_says_so(app, settings):
    """Review finding: the checkbox never read the stored preference, so
    reopening the dialog from Help > Welcome to Pluton after unticking it
    showed ticked regardless, and accepting from there silently reversed the
    user's choice back to True.
    """
    preferences.write_show_welcome(settings, False)
    dialog = WelcomeDialog(settings)
    assert dialog.show_on_startup is False


def test_the_dialog_does_not_write_preferences_on_construction(app, settings):
    """Opening the dialog and closing it must leave the store untouched."""
    WelcomeDialog(settings)
    assert settings.value(preferences.SHOW_WELCOME_KEY) is None


def test_escape_leaves_the_document_alone(app, monkeypatch):
    """Spec: dismissal changes nothing and leaves no half-configured document.

    Review finding: the previous version built a DocumentSettings that was
    never passed to or referenced by the dialog, so dialog.reject() could not
    have affected it under any implementation -- the assertion was
    unconditional. This drives the real path (MainWindow.show_welcome_dialog,
    which execs the real dialog) with exec() patched to report Rejected, and
    compares the live document and settings store against a before snapshot
    rather than against a hardcoded default.
    """
    from pluton.ui.main_window import MainWindow
    from pluton.ui.welcome_dialog import WelcomeDialog as Dialog

    window = MainWindow()
    before_units = window._doc.units
    before_environment = window._doc.environment

    monkeypatch.setattr(Dialog, "exec", lambda self: Dialog.DialogCode.Rejected)
    window.show_welcome_dialog()

    assert window._settings.value(preferences.SHOW_WELCOME_KEY) is None
    assert window._settings.value(preferences.DEFAULT_TEMPLATE_PREF_KEY) is None
    assert window._doc.units == before_units
    assert window._doc.environment == before_environment


def test_open_is_reported_rather_than_performed(app, settings):
    """The dialog must not reimplement the open-file flow.

    It reports the intent; MainWindow routes it into the existing path. Two open
    paths drift.
    """
    dialog = WelcomeDialog(settings)
    assert dialog.wants_open is False
    dialog._on_open_clicked()
    assert dialog.wants_open is True


def test_every_template_appears_in_the_grid(app, settings):
    from pluton.templates import TEMPLATES

    dialog = WelcomeDialog(settings)
    assert len(dialog._template_buttons) == len(TEMPLATES)


def test_template_descriptions_word_wrap_is_enabled(app, settings):
    """Task 6c Finding 1: a QLabel with no word wrap clips instead of reflowing, and that
    is what made the longer descriptions unreadable.
    """
    dialog = WelcomeDialog(settings)
    assert dialog._description_labels, "no description labels were built"
    for label in dialog._description_labels.values():
        assert label.wordWrap() is True


def test_template_descriptions_report_a_real_wrapped_height(app, settings):
    """Task 6c Finding 1, verified rather than assumed.

    A weak version of this test would only assert setWordWrap(True) was
    called. This instead measures what the label actually reports: its own
    sizeHint is tall enough to hold at least one line, and heightForWidth at
    the dialog's own minimum width is finite and positive -- not 0 (wrapping
    did nothing) and not -1 (the label does not support height-for-width at
    all).
    """
    dialog = WelcomeDialog(settings)
    min_width = dialog.minimumWidth()
    assert min_width > 0

    for key, label in dialog._description_labels.items():
        one_line = label.fontMetrics().height()
        assert label.sizeHint().height() >= one_line, key
        height_for_width = label.heightForWidth(min_width)
        assert height_for_width > 0, f"{key}: heightForWidth({min_width}) = {height_for_width}"


def test_the_description_column_gets_the_layout_stretch(app, settings):
    """Task 6c Finding 1: without this the radio-button column can absorb the slack
    instead, leaving the description column exactly as narrow as before.
    """
    dialog = WelcomeDialog(settings)
    grid = dialog._template_grid
    assert grid.columnStretch(1) > grid.columnStretch(0)


def test_the_default_template_environment_is_the_modelling_one(app, settings):
    """A tester who clicks straight through should land on sky and ground."""
    dialog = WelcomeDialog(settings)
    assert dialog.selected_template.environment == SKY_AND_GROUND


def test_accepting_the_dialog_writes_both_preferences(app, monkeypatch):
    """The dialog reports; MainWindow persists. Nothing else covers the writes.

    Without this, the do-not-show checkbox and the sticky default template could
    both be inert and every other test in this file would still pass, because the
    dialog deliberately does not write to the store itself.

    exec() is patched out rather than called: it would block forever under
    pytest, and the convention this dialog establishes is that application logic
    never execs. MainWindow is the one exception, so the patch goes there.
    """
    from pluton.ui.main_window import MainWindow
    from pluton.ui.welcome_dialog import WelcomeDialog as Dialog

    window = MainWindow()

    def _accept_with_documentation(self):
        self._template_buttons["documentation"].setChecked(True)
        self._show_checkbox.setChecked(False)
        return Dialog.DialogCode.Accepted

    monkeypatch.setattr(Dialog, "exec", _accept_with_documentation)
    window.show_welcome_dialog()

    assert preferences.read_show_welcome(window._settings) is False
    assert preferences.read_default_template(window._settings) == "documentation"
    assert window._doc.environment == PLAIN_WHITE


def test_accepting_the_dialog_applies_the_template_to_the_live_document(app, monkeypatch):
    """The startup path end to end: template units reach DocumentSettings."""
    from pluton.ui.main_window import MainWindow
    from pluton.ui.welcome_dialog import WelcomeDialog as Dialog

    window = MainWindow()

    def _accept_with_architectural(self):
        self._template_buttons["architectural"].setChecked(True)
        return Dialog.DialogCode.Accepted

    monkeypatch.setattr(Dialog, "exec", _accept_with_architectural)
    window.show_welcome_dialog()

    assert window._doc.units.metric_unit == "mm"
    assert window._doc.units.metric_precision == 0
    assert window._doc.environment == SKY_AND_GROUND
