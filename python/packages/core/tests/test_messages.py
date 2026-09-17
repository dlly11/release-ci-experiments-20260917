"""Tests for the shared Python core package."""

import pytest

from release_lab_core import Message, MessageKind, create_message, normalize_name


def test_normalize_name_collapses_whitespace() -> None:
    assert normalize_name("  Ada   Lovelace  ") == "Ada Lovelace"


def test_normalize_name_rejects_blank_input() -> None:
    with pytest.raises(ValueError, match="name must contain"):
        normalize_name("   ")


def test_create_message_returns_domain_value() -> None:
    assert create_message(
        kind=MessageKind.GREETING,
        source="test",
        prefix="Hello",
        name="Grace",
    ) == Message(kind=MessageKind.GREETING, source="test", text="Hello, Grace!")
