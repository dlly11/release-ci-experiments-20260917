"""Exercise the native CLI helper's bounded child processes."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[3] / "cmake/CheckCommandOutput.cmake"


@pytest.mark.parametrize("with_argument", [False, True])
def test_hanging_command_is_terminated(tmp_path: Path, with_argument: bool) -> None:
    cmake = shutil.which("cmake")
    if cmake is None:
        pytest.skip("CMake is needed to exercise the native command helper")
    source = 'import time\nprint("started", flush=True)\ntime.sleep(60)\n'
    command = [
        cmake,
        f"-DCOMMAND_PATH={sys.executable}",
        "-DEXPECTED_EXIT_CODE=0",
        "-DEXPECTED_STDOUT=",
        "-DEXPECTED_STDERR=",
    ]
    if with_argument:
        script = tmp_path / "sleep.py"
        script.write_text(source, encoding="utf-8")
        command.append(f"-DCOMMAND_ARGUMENT={script}")
    command.extend(["-P", str(HELPER)])
    result = subprocess.run(
        command,
        # Without an argument, Python reads the sleeping program from inherited stdin.
        input=None if with_argument else source,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode != 0
    assert "10-second timeout" in result.stderr
    # CMake wraps diagnostic lines at spaces in long checkout paths.
    assert " ".join(sys.executable.split()) in " ".join(result.stderr.split())
