# Example Package A

Example greeting service depending only on `release-lab-core`.

```python
from release_lab_package_a import GreetingService

assert GreetingService().greet("Ada").text == "Hello, Ada!"
```

See the [component documentation](https://dlly11.github.io/release-ci-experiments-20260917/python/packages/package_a/docs/index.html) for examples and API details.
