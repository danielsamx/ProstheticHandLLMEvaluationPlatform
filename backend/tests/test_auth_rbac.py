from app.core.security import (
    ROLE_PERMISSIONS,
    Permission,
    hash_password,
    verify_password,
)
from app.models.enums import UserRole


def test_admin_has_every_permission():
    assert ROLE_PERMISSIONS[UserRole.ADMIN] == frozenset(Permission)


def test_intern_cannot_edit_prompts_or_operate_hardware():
    permissions = ROLE_PERMISSIONS[UserRole.INTERN]
    assert Permission.RUN_EXPERIMENTS in permissions
    assert Permission.LABEL_GESTURES in permissions
    assert Permission.EDIT_PROMPTS not in permissions
    assert Permission.OPERATE_HARDWARE not in permissions


def test_other_is_read_only():
    assert ROLE_PERMISSIONS[UserRole.OTHER] == frozenset({Permission.VIEW_RESULTS})


def test_passwords_longer_than_bcrypt_limit_are_supported():
    password = "contraseña-segura-" * 12
    hashed = hash_password(password)
    assert hashed.startswith("sha256$")
    assert verify_password(password, hashed)


def test_password_content_after_byte_72_is_significant():
    prefix = "x" * 72
    hashed = hash_password(prefix + "A")
    assert verify_password(prefix + "A", hashed)
    assert not verify_password(prefix + "B", hashed)
