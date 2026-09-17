# Python core

`release-lab-core` owns the shared message value, message categories, name normalization, and message
construction used by the other Python packages. It has no workspace dependencies.

Import its public API from `release_lab_core`:

```python
from release_lab_core import Message, MessageKind, create_message, normalize_name
```

## Python core examples

### Normalize input

```python
from release_lab_core import normalize_name

name = normalize_name("  Ada   Lovelace  ")
assert name == "Ada Lovelace"
```

Blank or whitespace-only names raise `ValueError`.

### Create a message

```python
from release_lab_core import MessageKind, create_message

message = create_message(
    kind=MessageKind.GREETING,
    source="example",
    prefix="Welcome",
    name="Ada Lovelace",
)

assert message.text == "Welcome, Ada Lovelace!"
```

## Python core API

```{automodule} release_lab_core.messages
:members:
:show-inheritance:
```
