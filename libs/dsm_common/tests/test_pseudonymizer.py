import pytest

from dsm_common.privacy import pseudonymize_user_id


def test_pseudonymize_is_deterministic() -> None:
    first = pseudonymize_user_id("12345", salt="secret-salt")
    second = pseudonymize_user_id(" 12345 ", salt="secret-salt")
    assert first == second
    assert first.startswith("usr_")
    assert len(first) == len("usr_") + 16
    assert first != "12345"


def test_pseudonymize_depends_on_salt() -> None:
    a = pseudonymize_user_id("12345", salt="salt-a")
    b = pseudonymize_user_id("12345", salt="salt-b")
    assert a != b


def test_pseudonymize_rejects_empty_inputs() -> None:
    with pytest.raises(ValueError):
        pseudonymize_user_id("   ", salt="secret")
    with pytest.raises(ValueError):
        pseudonymize_user_id("12345", salt="")
    with pytest.raises(ValueError):
        pseudonymize_user_id("12345", salt="secret", length=0)
