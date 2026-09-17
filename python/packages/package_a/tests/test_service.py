"""Tests for Python Package A."""

from release_lab_core import MessageKind
from release_lab_package_a import GreetingService


def test_greeting_service_uses_core_message() -> None:
    result = GreetingService().greet("Ada")

    assert result.kind is MessageKind.GREETING
    assert result.source == "package_a"
    assert result.text == "Hello, Ada!"


def test_greeting_service_supports_custom_prefix() -> None:
    assert GreetingService(prefix="Welcome").greet("Lin").text == "Welcome, Lin!"
