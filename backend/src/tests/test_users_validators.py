"""Tests for users/validators.py."""
import pytest

from users.exceptions import ValidationFailedError
from users.validators import (
    validate_api_key_name,
    validate_email_format,
    validate_not_blank,
    validate_organization_name,
    validate_password_strength,
    validate_team_name,
)


def test_validate_email_format_accepts_valid_email():
    validate_email_format("user@example.com")  # must not raise


@pytest.mark.parametrize("email", ["", "not-an-email", "missing-domain@", "@missing-local.com", "no-at-sign.com"])
def test_validate_email_format_rejects_invalid(email):
    with pytest.raises(ValidationFailedError):
        validate_email_format(email)


def test_validate_password_strength_accepts_strong_password():
    validate_password_strength("StrongPass123")  # must not raise


def test_validate_password_strength_rejects_too_short():
    with pytest.raises(ValidationFailedError):
        validate_password_strength("Sh0rt")


def test_validate_password_strength_rejects_missing_uppercase():
    with pytest.raises(ValidationFailedError):
        validate_password_strength("lowercase123")


def test_validate_password_strength_rejects_missing_lowercase():
    with pytest.raises(ValidationFailedError):
        validate_password_strength("UPPERCASE123")


def test_validate_password_strength_rejects_missing_digit():
    with pytest.raises(ValidationFailedError):
        validate_password_strength("NoDigitsHere")


def test_validate_not_blank_rejects_blank():
    with pytest.raises(ValidationFailedError):
        validate_not_blank("   ", "field")


def test_validate_not_blank_accepts_non_blank():
    validate_not_blank("value", "field")  # must not raise


def test_validate_organization_name_rejects_too_long():
    with pytest.raises(ValidationFailedError):
        validate_organization_name("x" * 256)


def test_validate_team_name_rejects_too_long():
    with pytest.raises(ValidationFailedError):
        validate_team_name("x" * 256)


def test_validate_api_key_name_rejects_too_long():
    with pytest.raises(ValidationFailedError):
        validate_api_key_name("x" * 256)
