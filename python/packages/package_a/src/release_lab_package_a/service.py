"""Package A business logic."""

from dataclasses import dataclass

from release_lab_core import Message, MessageKind, create_message


@dataclass(frozen=True, slots=True)
class GreetingService:
    """Create greetings using shared core domain primitives."""

    prefix: str = "Hello"

    def greet(self, name: str) -> Message:
        """Return a greeting for ``name``."""
        return create_message(
            kind=MessageKind.GREETING,
            source="package_a",
            prefix=self.prefix,
            name=name,
        )
