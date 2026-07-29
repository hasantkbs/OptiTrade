"""OptiTrade User & Organization Platform — input validation."""
from __future__ import annotations

import re

from users.exceptions import ValidationFailedError

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MIN_PASSWORD_LENGTH = 10


def validate_email_format(email: str) -> None:
    if not email or not _EMAIL_RE.match(email.strip()):
        raise ValidationFailedError(f"{email!r} is not a valid email address")


def validate_password_strength(password: str) -> None:
    if len(password) < _MIN_PASSWORD_LENGTH:
        raise ValidationFailedError(f"password must be at least {_MIN_PASSWORD_LENGTH} characters long")
    if not any(character.isupper() for character in password):
        raise ValidationFailedError("password must contain at least one uppercase letter")
    if not any(character.islower() for character in password):
        raise ValidationFailedError("password must contain at least one lowercase letter")
    if not any(character.isdigit() for character in password):
        raise ValidationFailedError("password must contain at least one digit")


def validate_not_blank(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValidationFailedError(f"{field_name} must not be blank")


def validate_organization_name(name: str) -> None:
    validate_not_blank(name, "organization name")
    if len(name) > 255:
        raise ValidationFailedError("organization name must be at most 255 characters")


def validate_team_name(name: str) -> None:
    validate_not_blank(name, "team name")
    if len(name) > 255:
        raise ValidationFailedError("team name must be at most 255 characters")


def validate_api_key_name(name: str) -> None:
    validate_not_blank(name, "API key name")
    if len(name) > 255:
        raise ValidationFailedError("API key name must be at most 255 characters")
