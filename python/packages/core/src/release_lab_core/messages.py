"""Domain message types shared by independently deliverable packages."""

from dataclasses import dataclass
from enum import StrEnum


class MessageKind(StrEnum):
    """Supported categories for the example domain."""

    GREETING = "greeting"
    FAREWELL = "farewell"


@dataclass(frozen=True, slots=True)
class Message:
    """A small immutable value returned across package boundaries."""

    kind: MessageKind
    source: str
    text: str


def normalize_name(name: str) -> str:
    """Normalize user input and reject blank names."""
    normalized = " ".join(name.split())
    if not normalized:
        message = "name must contain at least one non-whitespace character"
        raise ValueError(message)
    return normalized


def create_message(*, kind: MessageKind, source: str, prefix: str, name: str) -> Message:
    """Create a consistently formatted message for downstream packages."""
    normalized_name = normalize_name(name)
    return Message(kind=kind, source=source, text=f"{prefix}, {normalized_name}!")
