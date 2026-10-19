from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]

def test_successful_tools_have_render_commands(cortex_case: SimpleNamespace) -> None:
    tools = cortex_case.tools
    results = [
        tools.display_patient_data("hemoglobin"),
        tools.display_all_patient_data(),
        tools.hide_patient_data(),
        tools.navigate_scan("up"),
        tools.jump_to_landmark("tumor"),
        tools.hide_scan(),
        tools.rotate_model("y", 0),
        tools.toggle_structure("edema", True),
        tools.reset_3d_view(),
        tools.hide_3d(),
        tools.get_tumor_measurements(),
        tools.get_surgical_phase("positioning"),
        tools.hide_surgical_checklist(),
        tools.check_drug_safety("propofol"),
        tools.log_event("note", "test event"),
        tools.show_event_log(),
        tools.hide_event_log(),
        tools.show_agent_summary("Test", "", []),
        tools.hide_all_overlays(),
        tools.show_only_ar(),
    ]
    for result in results:
        if result.get("status") != "error":
            assert "render_command" in result


def test_scan_navigation_clamps(cortex_case: SimpleNamespace) -> None:
    tools = cortex_case.tools
    assert tools.navigate_scan("up", 1000)["slice"] == cortex_case.case["slices"]["count"]
    assert tools.navigate_scan("down", 1000)["slice"] == 1


def test_scan_landmarks(cortex_case: SimpleNamespace) -> None:
    tools = cortex_case.tools
    result = tools.jump_to_landmark("tumor")
    assert result["slice"] == cortex_case.case["landmarks"]["tumor"]
    assert tools.jump_to_landmark("carina")["status"] == "error"


def test_drug_safety(cortex_case: SimpleNamespace) -> None:
    tools = cortex_case.tools
    cefazolin = tools.check_drug_safety("cefazolin")
    assert cefazolin["safety_status"] == "caution"
    assert "vancomycin" in cefazolin["summary"].lower()
    assert tools.check_drug_safety("propofol")["safety_status"] == "safe"


def test_tumor_measurements(cortex_case: SimpleNamespace) -> None:
    result = cortex_case.tools.get_tumor_measurements()
    assert result["volumes_cm3"] == cortex_case.case["volumes_cm3"]
    assert result["render_command"]["value"] == (
        "Enhancing tumor 8.4 cm³ · Necrotic core 3.1 cm³ · "
        "Edema 45.7 cm³ · Resection cavity 1.0 cm³"
    )
    assert result["render_command"]["note"] == "CorteX segmentation · T1c"


def test_event_log(cortex_case: SimpleNamespace) -> None:
    tools = cortex_case.tools
    tools.log_event("incision")
    entries = tools.show_event_log()["render_command"]["entries"]
    assert any(entry["type"] == "incision" for entry in entries)


def test_ai_interaction_is_not_added_to_event_log(cortex_case: SimpleNamespace) -> None:
    tools = cortex_case.tools
    tools.log_ai_interaction("a", "b")
    entries = tools.show_event_log()["render_command"]["entries"]
    assert not any(entry["type"] == "ai_interaction" for entry in entries)


def test_structure_grounding(cortex_case: SimpleNamespace) -> None:
    callback = cortex_case.agent._grounding_before_tool
    tool = SimpleNamespace(name="toggle_structure")
    assert callback(tool, {"structure": "lung_left"}, None)["status"] == "error"
    assert callback(tool, {"structure": "edema"}, None) is None


def test_root_agent(cortex_case: SimpleNamespace) -> None:
    root_agent = cortex_case.package.root_agent
    assert root_agent.name == "CORTEX"
    assert [tool.__name__ for tool in root_agent.tools] == [
        "display_patient_data",
        "display_all_patient_data",
        "hide_patient_data",
        "navigate_scan",
        "jump_to_landmark",
        "hide_scan",
        "rotate_model",
        "toggle_structure",
        "reset_3d_view",
        "hide_3d",
        "get_tumor_measurements",
        "get_surgical_phase",
        "hide_surgical_checklist",
        "check_drug_safety",
        "log_event",
        "show_event_log",
        "hide_event_log",
        "show_agent_summary",
        "hide_all_overlays",
        "show_only_ar",
    ]


def test_dev_tool_route_is_environment_gated(
    cortex_case: SimpleNamespace,
    monkeypatch,
) -> None:
    monkeypatch.chdir(ROOT / "app")

    monkeypatch.delenv("CORTEX_DEV", raising=False)
    sys.modules.pop("main", None)
    production_main = importlib.import_module("main")
    production_paths = {route.path for route in production_main.app.routes}
    assert "/dev/tool/{name}" not in production_paths

    monkeypatch.setenv("CORTEX_DEV", "1")
    sys.modules.pop("main", None)
    development_main = importlib.import_module("main")
    development_paths = {route.path for route in development_main.app.routes}
    assert "/dev/tool/{name}" in development_paths

    client = TestClient(development_main.app)
    response = client.post(
        "/dev/tool/display_patient_data",
        json={"field": "hemoglobin"},
    )
    assert response.status_code == 200
    assert response.json()["response"]["field"] == "hemoglobin"
    assert client.post("/dev/tool/not_a_tool", json={}).status_code == 404

    sys.modules.pop("main", None)
