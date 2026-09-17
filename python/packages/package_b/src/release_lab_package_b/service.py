"""Package B business logic."""

from dataclasses import dataclass

from release_lab_core import Message, MessageKind, create_message


@dataclass(frozen=True, slots=True)
class FarewellService:
    """Create farewells using shared core domain primitives."""

    prefix: str = "Goodbye"

    def farewell(self, name: str) -> Message:
        """Return a farewell for ``name``."""
        return create_message(
            kind=MessageKind.FAREWELL,
            source="package_b",
            prefix=self.prefix,
            name=name,
        )
