from pluton.io.errors import PlutonFormatError, PlutonIOError, PlutonVersionError


def test_subclass_hierarchy():
    assert issubclass(PlutonFormatError, PlutonIOError)
    assert issubclass(PlutonVersionError, PlutonIOError)


def test_os_error_is_not_a_pluton_io_error():
    """PlutonIOError is a project-specific hierarchy; plain filesystem errors
    (missing file, permission denied) must NOT be silently caught by a
    `except PlutonIOError` handler — callers need OSError to still surface."""
    assert not issubclass(OSError, PlutonIOError)


def test_raisable_with_message():
    for exc in (PlutonIOError, PlutonFormatError, PlutonVersionError):
        try:
            raise exc("boom")
        except PlutonIOError as e:
            assert "boom" in str(e)
