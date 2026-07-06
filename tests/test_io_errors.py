from pluton.io.errors import PlutonFormatError, PlutonIOError, PlutonVersionError


def test_subclass_hierarchy():
    assert issubclass(PlutonFormatError, PlutonIOError)
    assert issubclass(PlutonVersionError, PlutonIOError)


def test_raisable_with_message():
    for exc in (PlutonIOError, PlutonFormatError, PlutonVersionError):
        try:
            raise exc("boom")
        except PlutonIOError as e:
            assert "boom" in str(e)
