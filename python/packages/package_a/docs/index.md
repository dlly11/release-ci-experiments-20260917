# Python package A

`release-lab-package-a` provides `GreetingService`. It depends on `release-lab-core` and does not depend
on package B or either application.

```python
from release_lab_package_a import GreetingService
```

## Python package A examples

### Default greeting

```python
from release_lab_package_a import GreetingService

message = GreetingService().greet("Ada")
assert message.text == "Hello, Ada!"
assert message.source == "package_a"
```

### Custom prefix

```python
from release_lab_package_a import GreetingService

message = GreetingService(prefix="Welcome").greet("Grace Hopper")
assert message.text == "Welcome, Grace Hopper!"
```

## Python package A API

```{automodule} release_lab_package_a.service
:members:
:show-inheritance:
```
