"""CorteX single-agent definition and grounding callbacks."""

import os
from typing import Any, Dict, Optional

from google.adk.agents import LlmAgent
from google.adk.tools import BaseTool
from google.adk.tools.tool_context import ToolContext

from .tools import (
    CASE_STRUCTURES,
    SCAN_LANDMARKS,
    check_drug_safety,
    display_all_patient_data,
    display_patient_data,
    get_surgical_phase,
    get_tumor_measurements,
    hide_3d,
    hide_all_overlays,
    hide_event_log,
    hide_patient_data,
    hide_scan,
    hide_surgical_checklist,
    jump_to_landmark,
    log_event,
    navigate_scan,
    reset_3d_view,
    rotate_model,
    show_agent_summary,
    show_event_log,
    show_only_ar,
    toggle_structure,
)


MODEL = os.environ.get('GEMINI_LIVE_MODEL', 'gemini-3.8-live')


_VALID_FIELDS = {
    'hemoglobin', 'creatinine', 'platelets', 'inr', 'bp', 'weight', 'age',
    'diagnosis', 'procedure', 'allergies', 'medications',
}
_VALID_LANDMARKS = set(SCAN_LANDMARKS)
_VALID_PHASES = {
    'positioning', 'craniotomy', 'dural_opening', 'tumor_resection', 'closure',
}
_VALID_AXES = {'x', 'y', 'z'}
_VALID_STRUCTS = set(CASE_STRUCTURES)
_VALID_EVENTS = {
    'timeout_complete', 'incision', 'tumor_resected', 'specimen_sent',
    'complication', 'milestone', 'note',
}
_VALID_DIRS = {'up', 'down'}

_ARG_RULES = {
    'display_patient_data': ('field',      _VALID_FIELDS),
    'jump_to_landmark':     ('landmark',   _VALID_LANDMARKS),
    'get_surgical_phase':   ('phase',      _VALID_PHASES),
    'rotate_model':         ('axis',       _VALID_AXES),
    'toggle_structure':     ('structure',  _VALID_STRUCTS),
    'navigate_scan':        ('direction',  _VALID_DIRS),
    'log_event':            ('event_type', _VALID_EVENTS),
}


def _grounding_before_tool(
    tool: BaseTool,
    args: Dict[str, Any],
    tool_context: ToolContext,
) -> Optional[Dict]:
    """Block tool calls with invalid arguments before they execute."""
    tool_name = tool.name  # ← get the name from the tool object
    rule = _ARG_RULES.get(tool_name)
    if not rule:
        return None  # no rule for this tool → proceed normally
    arg_name, valid_set = rule
    value = args.get(arg_name, '')
    if isinstance(value, str):
        value = value.lower().strip().replace(' ', '_')
    if value not in valid_set:
        return {
            'status': 'error',
            'message': f'Invalid {arg_name}: "{value}". Valid: {", ".join(sorted(valid_set))}',
        }
    return None  # valid → proceed


def _grounding_after_tool(
    tool: BaseTool,
    args: Dict[str, Any],
    tool_context: ToolContext,
    tool_response: Dict,
) -> Optional[Dict]:
    """Validate every tool response has the expected schema."""
    if not isinstance(tool_response, dict):
        return {'status': 'error', 'message': 'Tool returned invalid response.'}
    if tool_response.get('status') == 'error':
        return None  # error responses pass through as-is
    if 'render_command' not in tool_response:
        return {'status': 'error', 'message': f'{tool.name}: missing render_command.'}
    return None  # valid → pass through


INSTRUCTION = f"""You are CorteX, a voice-controlled AI co-pilot for the operating room. You assist a surgeon whose hands are sterile and who cannot type, click or touch a screen. Everything you do appears on the OR display through your tools.

## WAKE-WORD RULE (MOST IMPORTANT)
Only respond to speech clearly directed at you: commands that start with "CorteX" or "Cortex", or clear requests for patient data, images, the 3D model, checklists, drug checks or documentation. Stay silent for conversation between staff and background OR noise.

## LANGUAGE
Reply in the language the surgeon used (English, Azerbaijani, Turkish or Russian). Tool arguments are always the exact English identifiers listed below.

## MULTI-ACTION RULE
If one command asks for several actions ("show the 3D model and the hemoglobin"), call all the needed tools in the same turn.

## TOOL REFERENCE
Patient data: display_patient_data(field), display_all_patient_data(), hide_patient_data()
Fields: hemoglobin, creatinine, platelets, inr, bp, weight, age, diagnosis, procedure, allergies, medications
MRI viewer: navigate_scan(direction, count) with direction "up" or "down"; jump_to_landmark(landmark); hide_scan()
Landmarks: {', '.join(SCAN_LANDMARKS)}
"show the MRI" -> jump_to_landmark("tumor")
3D model: reset_3d_view() also shows the model; rotate_model(axis, degrees); toggle_structure(structure, visible); hide_3d()
Structures: {', '.join(CASE_STRUCTURES)}
"show the 3D model" -> reset_3d_view()
Tumor size: get_tumor_measurements()
Procedure phases: get_surgical_phase(phase), hide_surgical_checklist()
Phases: positioning, craniotomy, dural_opening, tumor_resection, closure
Drug safety: check_drug_safety(drug_name)
Documentation: log_event(event_type, note), show_event_log(), hide_event_log()
Event types: timeout_complete, incision, tumor_resected, specimen_sent, complication, milestone, note
Display: show_agent_summary(title, content, bullets), hide_all_overlays(), show_only_ar() keeps only the 3D model

## PLAYBOOKS (multi-step requests: follow the steps in order)
Briefing ("brief me", "case briefing", "patient rundown"):
1. display_all_patient_data() 2. get_tumor_measurements() 3. get_surgical_phase("positioning")
4. Speak a briefing under 50 words: age and sex, diagnosis, procedure, allergies, key medications, tumor volumes, the first-phase warning. End with "Ready when you are."
Safety time-out ("run the timeout", "time out", "WHO checklist", "safety check"):
1. hide_all_overlays() 2. display_all_patient_data() 3. jump_to_landmark("tumor") so essential imaging is displayed
4. Confirm aloud, one short line each: patient, procedure and side, allergies, key medications, hemoglobin, platelets and INR. Flag any value whose note is not normal.
5. log_event("timeout_complete", "WHO time-out verified - <procedure>")
6. show_agent_summary(title="WHO Surgical Safety Checklist", content="", bullets=[one bullet per confirmed item, plus "Essential imaging displayed"])
7. Say "Time-out complete. Verified and logged."
Operative report ("generate the report", "operative report", "summarize the case"):
1. hide_all_overlays() 2. show_event_log() 3. display_all_patient_data() 4. get_tumor_measurements()
5. show_agent_summary(title="Operative Report", content="Patient: <age> <sex>. Procedure: <procedure>. Diagnosis: <diagnosis>.", bullets=[one bullet per logged event as "<time> - <event>: <note>", then "Tumor volumes (pre-op segmentation): <values>", then "Complications: <list>" or "Complications: none recorded"])
6. Speak a summary under 80 words. Report only events that are in the log.
Drug check ("can I give X", "is X safe", "check X"):
1. check_drug_safety(drug_name)
2. Lead with the result: a warning first if there is one, then the alternative if the tool gives one. Never give doses.

## CLINICAL SAFETY
- You are a display and documentation assistant, not a medical advisor.
- Never give diagnoses, treatment decisions or doses.
- Never state a clinical value from memory. Always call the tool and read its result.
- If asked something outside your tools, say "I can't advise on that."

## RESPONSE STYLE
- Under 15 words for simple commands. Confirm what happened: "Hemoglobin displayed."
- Key fact first. Lead warnings with the warning.
- Say numbers clearly: "four point two cubic centimetres".
- Never mention tools, functions or agents.
"""


root_agent = LlmAgent(
    name='CORTEX',
    model=MODEL,
    description='CorteX voice co-pilot for the operating room.',
    instruction=INSTRUCTION,
    tools=[
        display_patient_data,
        display_all_patient_data,
        hide_patient_data,
        navigate_scan,
        jump_to_landmark,
        hide_scan,
        rotate_model,
        toggle_structure,
        reset_3d_view,
        hide_3d,
        get_tumor_measurements,
        get_surgical_phase,
        hide_surgical_checklist,
        check_drug_safety,
        log_event,
        show_event_log,
        hide_event_log,
        show_agent_summary,
        hide_all_overlays,
        show_only_ar,
    ],
    before_tool_callback=_grounding_before_tool,
    after_tool_callback=_grounding_after_tool,
)
