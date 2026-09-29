"""Copy the app package and its baked data into worker/src so pywrangler can bundle them.

The Worker bundles only what lives under worker/src. The copies are build output (git-ignored):
edit src/city_walk_planner and seed/, then run this again before `pywrangler dev` / `deploy`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "worker" / "src" / "city_walk_planner"


def main() -> None:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    # The Worker serves only the API; GitHub Pages serves the web front end.
    shutil.copytree(ROOT / "src" / "city_walk_planner", TARGET,
                    ignore=shutil.ignore_patterns("web", "__pycache__", "*.pyc"))
    shutil.copytree(ROOT / "seed", TARGET / "_seed")
    files = sum(1 for path in TARGET.rglob("*") if path.is_file())
    size = sum(path.stat().st_size for path in TARGET.rglob("*") if path.is_file())
    print(f"worker bundle: {files} files, {size / 1_000_000:.1f} MB -> {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
