"""Tests for Python Package B."""

from release_lab_core import MessageKind
from release_lab_package_b import FarewellService


def test_farewell_service_uses_core_message() -> None:
    result = FarewellService().farewell("Ada")

    assert result.kind is MessageKind.FAREWELL
    assert result.source == "package_b"
    assert result.text == "Goodbye, Ada!"
