"""Sphinx configuration for the repository-wide documentation site."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

project = "Release CI Experiments"
author = "Release CI Experiment"
copyright = "2026, Release CI Experiment"
release = (ROOT / "version.txt").read_text(encoding="utf-8").strip()
version = release

extensions = [
    "breathe",
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinxcontrib.mermaid",
]

root_doc = "docs/index"
source_suffix = {".md": "markdown"}
exclude_patterns = [
    ".git/**",
    ".github/**",
    ".venv/**",
    ".pytest_cache/**",
    ".ruff_cache/**",
    "build/**",
    "dist/**",
    "stage/**",
    "**/__pycache__/**",
    "**/*.egg-info/**",
    "README.md",
    "CHANGELOG.md",
    "tools/README.md",
    "python/**/README.md",
]

myst_heading_anchors = 3

myst_enable_extensions = ["colon_fence"]
myst_fence_as_directive = ["mermaid"]

breathe_projects = {"native": str(ROOT / "build/docs/doxygen/xml")}
breathe_default_project = "native"
breathe_domain_by_extension = {"h": "c"}

autodoc_member_order = "bysource"
autodoc_typehints = "description"
nitpicky = True
nitpick_ignore_regex = [
    ("py:class", r"argparse\..*"),
    ("py:class", r"collections\.abc\..*"),
    ("c:identifier", r"size_t"),
    ("cpp:identifier", r"size_t"),
]

templates_path = [str(ROOT / "tools/sphinx/templates")]
redirects = {
    "index": ("docs/index", ""),
    "python/apps/package_a_cli/docs/examples": (
        "python/apps/package_a_cli/docs/index",
        "python-release-lab-package-a-cli-examples",
    ),
    "python/apps/package_a_cli/docs/api": (
        "python/apps/package_a_cli/docs/index",
        "python-release-lab-package-a-cli-api",
    ),
    "python/packages/core/docs/examples": (
        "python/packages/core/docs/index",
        "python-core-examples",
    ),
    "python/packages/core/docs/api": ("python/packages/core/docs/index", "python-core-api"),
    "python/packages/package_a/docs/examples": (
        "python/packages/package_a/docs/index",
        "python-package-a-examples",
    ),
    "python/packages/package_a/docs/api": (
        "python/packages/package_a/docs/index",
        "python-package-a-api",
    ),
    "python/packages/package_b/docs/examples": (
        "python/packages/package_b/docs/index",
        "python-package-b-examples",
    ),
    "python/packages/package_b/docs/api": (
        "python/packages/package_b/docs/index",
        "python-package-b-api",
    ),
    "native/apps/package_a_cli/docs/examples": (
        "native/apps/package_a_cli/docs/index",
        "native-release-lab-package-a-cli-examples",
    ),
    "native/apps/package_a_cli/docs/api": (
        "native/apps/package_a_cli/docs/index",
        "native-release-lab-package-a-cli-version-api",
    ),
    "native/packages/core/docs/examples": (
        "native/packages/core/docs/index",
        "native-core-examples",
    ),
    "native/packages/core/docs/api": ("native/packages/core/docs/index", "native-core-api"),
    "native/packages/package_a/docs/examples": (
        "native/packages/package_a/docs/index",
        "native-package-a-examples",
    ),
    "native/packages/package_a/docs/api": (
        "native/packages/package_a/docs/index",
        "native-package-a-api",
    ),
    "native/packages/package_b/docs/examples": (
        "native/packages/package_b/docs/index",
        "native-package-b-examples",
    ),
    "native/packages/package_b/docs/api": (
        "native/packages/package_b/docs/index",
        "native-package-b-api",
    ),
}
html_context = {"redirects": redirects}
html_additional_pages = dict.fromkeys(redirects, "redirect.html")
html_theme = "furo"
html_title = f"{project} {release}"
html_baseurl = "https://dlly11.github.io/release-ci-experiments-20260917/"
html_theme_options = {
    "source_repository": "https://github.com/dlly11/release-ci-experiments-20260917/",
    "source_branch": "main",
    "source_directory": "",
}
