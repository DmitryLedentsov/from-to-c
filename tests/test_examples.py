#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
COMPILER = ROOT / "src" / "ftc.py"

CASES = {
    "counter.ftc": "1\n2\n3\n",
    "point.ftc": "7\n",
}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for source_name, expected in CASES.items():
            source = ROOT / "examples" / source_name
            generated = tmp / source.with_suffix(".c").name
            binary = tmp / source.stem

            subprocess.run([sys.executable, str(COMPILER), str(source), "-o", str(generated)], check=True)
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(generated), "-o", str(binary)],
                check=True,
            )
            actual = subprocess.check_output([str(binary)], text=True)
            if actual != expected:
                raise AssertionError(f"{source_name}: expected {expected!r}, got {actual!r}")
            print(f"ok: {source_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
