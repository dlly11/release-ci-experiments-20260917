"""Bootstrap the local tooling package using only Python's standard library."""

import sys
from pathlib import Path

if __name__ == "__main__":
    source = Path(__file__).resolve().parent
    sys.path.insert(0, str(source / "src"))
    from repo_tools.cli import main

    raise SystemExit(main(default_root=source.parent.parent))
