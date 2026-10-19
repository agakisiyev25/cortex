from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def cortex_case(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    base = tmp_path_factory.mktemp("cortex_case")
    source = base / "synthetic"
    case_dir = base / "case"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "make_synthetic_case.py"),
            "--out",
            str(source),
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_case.py"),
            "--image",
            str(source / "image.nii.gz"),
            "--mask",
            str(source / "mask.nii.gz"),
            "--out",
            str(case_dir),
        ],
        check=True,
    )

    os.environ["CASE_DIR"] = str(case_dir)
    app_dir = str(ROOT / "app")
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    package = importlib.import_module("cortex_agent")
    agent = importlib.import_module("cortex_agent.agent")
    tools = importlib.import_module("cortex_agent.tools")
    case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    return SimpleNamespace(package=package, agent=agent, tools=tools, case=case)
