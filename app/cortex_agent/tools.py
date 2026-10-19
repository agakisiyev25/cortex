"""
CorteX Tool Functions
======================
Tools used by the CorteX voice-controlled operating-room co-pilot.

IMPORTANT: Docstrings in this file are instructions to Gemini, not
documentation for humans. They tell the LLM when and how to call each tool.
Write them as explicit natural-language-to-parameter mappings.

Return convention: every tool returns:
  {
    'status': 'success' | 'error',
    'render_command': {
        'layer': 'ct' | 'clinical' | 'ar' | 'all',
        'action': 'show' | 'hide' | 'navigate' | 'rotate' | 'toggle' | 'reset',
        ...additional params
    }
  }
"""

import json
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

CASE_DIR = Path(os.environ.get(
    'CASE_DIR', Path(__file__).resolve().parent.parent / 'static' / 'case'
))
with (CASE_DIR / 'case.json').open(encoding='utf-8') as case_file:
    CASE = json.load(case_file)

SCAN_TOTAL_SLICES: int = CASE['slices']['count']
SCAN_LANDMARKS: dict[str, int] = CASE['landmarks']
CASE_STRUCTURES: list[str] = CASE['structures']
CASE_VOLUMES: dict[str, float] = CASE['volumes_cm3']

# Scan navigation state persists across multiple navigate_scan calls.
_scan_state: dict = {'current_slice': SCAN_LANDMARKS['tumor']}

# Synthetic demo data, not a real patient.
_PATIENT_DATA: dict[str, dict] = {
    'hemoglobin':  {'value': '13.4 g/dL', 'label': 'Hemoglobin', 'note': 'Normal'},
    'creatinine':  {'value': '0.8 mg/dL', 'label': 'Creatinine', 'note': 'Normal renal function'},
    'platelets':   {'value': '245 K/μL', 'label': 'Platelets', 'note': 'Adequate for surgery'},
    'inr':         {'value': '1.0', 'label': 'INR', 'note': 'Normal coagulation'},
    'bp':          {'value': '124/78 mmHg', 'label': 'Blood Pressure', 'note': 'Last recorded 07:10'},
    'weight':      {'value': '78 kg', 'label': 'Weight', 'note': ''},
    'age':         {'value': '46 years', 'label': 'Age', 'note': 'Male'},
    'diagnosis':   {'value': 'Recurrent glioblastoma — right frontal', 'label': 'Diagnosis', 'note': 'Recurrence on follow-up MRI'},
    'procedure':   {'value': 'Right frontal craniotomy for tumor resection', 'label': 'Procedure', 'note': 'Neuronavigation-guided'},
    'allergies':   {'value': 'Cefazolin (hives), Latex', 'label': 'Allergies', 'note': 'Latex-free room required'},
    'medications': {'value': 'Dexamethasone 4 mg BID, Levetiracetam 500 mg BID',
                    'label': 'Medications', 'note': 'Steroid and seizure prophylaxis continued'},
}


# ---------------------------------------------------------------------------
# IR Agent Tools — Information Retrieval (clinical data)
# ---------------------------------------------------------------------------

def display_patient_data(field: str) -> dict:
    """
    Use this tool when the surgeon asks to see, show, or display any clinical
    patient data. Valid field names are:

      hemoglobin  — blood hemoglobin level in g/dL
      creatinine  — serum creatinine in mg/dL
      platelets   — platelet count in K/μL
      inr         — international normalized ratio (coagulation)
      bp          — blood pressure in mmHg
      weight      — patient weight in kg
      age         — patient age in years
      diagnosis   — primary diagnosis and staging
      procedure   — name of the current surgical procedure
      allergies   — known drug allergies and reactions
      medications — current medication list

    Examples:
      "show me the hemoglobin" → field='hemoglobin'
      "what is the creatinine" → field='creatinine'
      "what medications is he on" → field='medications'
      "any allergies" → field='allergies'
      "what's the diagnosis" → field='diagnosis'

    For broad requests ("show all labs", "all patient data"), use
    display_all_patient_data() instead — do NOT call this tool in a loop.
    """
    field = field.lower().strip()
    if field not in _PATIENT_DATA:
        return {
            'status': 'error',
            'message': f"Unknown field '{field}'. Valid fields: {', '.join(_PATIENT_DATA.keys())}",
            'render_command': {'layer': 'clinical', 'action': 'error'},
        }
    record = _PATIENT_DATA[field]
    return {
        'status': 'success',
        'field': field,
        'label': record['label'],
        'value': record['value'],
        'note': record['note'],
        'render_command': {
            'layer': 'clinical',
            'action': 'show',
            'field': field,
            'label': record['label'],
            'value': record['value'],
            'note': record['note'],
        },
    }


def display_all_patient_data() -> dict:
    """
    Use this tool when the surgeon asks to see ALL patient data, all labs,
    all vitals, all patient information, or any broad request for the full
    patient record. This shows every field in one single call — do NOT loop
    through display_patient_data repeatedly.

    Use this for:
      "show all patient data"        → display_all_patient_data()
      "show me everything"           → display_all_patient_data()
      "show all the labs"            → display_all_patient_data()
      "what are all the vitals"      → display_all_patient_data()
      "show the full patient record" → display_all_patient_data()
      "display all data"             → display_all_patient_data()

    For a SINGLE specific field, use display_patient_data(field) instead.
    NEVER call display_patient_data in a loop — use this tool instead.
    """
    fields = [
        {'field': k, 'label': v['label'], 'value': v['value'], 'note': v['note']}
        for k, v in _PATIENT_DATA.items()
    ]
    return {
        'status': 'success',
        'render_command': {
            'layer': 'clinical',
            'action': 'show_all',
            'fields': fields,
        },
    }


def hide_patient_data() -> dict:
    """
    Use this tool when the surgeon asks to hide, clear, or remove the clinical
    data display. Examples:
      "hide the labs"
      "clear the clinical data"
      "remove the patient info"
    """
    return {
        'status': 'success',
        'render_command': {
            'layer': 'clinical',
            'action': 'hide',
        },
    }


# ---------------------------------------------------------------------------
# Image Viewer Tools — MRI navigation
# ---------------------------------------------------------------------------

def navigate_scan(direction: str, count: int = 1) -> dict:
    """
    Use this tool when the surgeon asks to move through MRI scan slices.

    Direction mapping:
      'up'   — use when the surgeon says: up, superior, higher, cranial
      'down' — use when the surgeon says: down, inferior, lower, caudal

    Count mapping:
      1 (default) — a single move, "next slice", "one slice"
      3 — "a bit", "a few", "slightly"
      5 — "several", "quite a few", "a bunch"
      10 — "many", "a lot", "further"
      Surgeon can also say an explicit number: "go down 7 slices" → count=7

    Examples:
      "go up two slices" → direction='up', count=2
      "move down one slice" → direction='down', count=1
      "go superior a bit" → direction='up', count=3
      "go inferior several" → direction='down', count=5
      "scroll down 10 slices" → direction='down', count=10
    """
    direction = direction.lower().strip()
    if direction not in ('up', 'down'):
        return {
            'status': 'error',
            'message': "direction must be 'up' or 'down'",
            'render_command': {'layer': 'ct', 'action': 'error'},
        }

    current = _scan_state['current_slice']
    if direction == 'up':
        new_slice = min(SCAN_TOTAL_SLICES, current + count)
    else:
        new_slice = max(1, current - count)

    _scan_state['current_slice'] = new_slice

    return {
        'status': 'success',
        'slice': new_slice,
        'total': SCAN_TOTAL_SLICES,
        'render_command': {
            'layer': 'ct',
            'action': 'navigate',
            'slice': new_slice,
            'total': SCAN_TOTAL_SLICES,
        },
    }


def jump_to_landmark(landmark: str) -> dict:
    """
    Use this tool when the surgeon asks to go to a specific landmark in the
    MRI scan. Available landmarks:

      tumor             — "jump to the tumor", "show the tumor on the MRI"
      tumor_top         — highest slice containing the tumor or edema
      tumor_bottom      — lowest slice containing the tumor or edema
      resection_cavity  — "show the cavity" (available only when present)
      mid_brain         — "middle of the brain"

    Examples:
      "jump to the tumor" → landmark='tumor'
      "show the cavity" → landmark='resection_cavity'
      "middle of the brain" → landmark='mid_brain'
    """
    landmark = landmark.lower().strip().replace(' ', '_')
    if landmark not in SCAN_LANDMARKS:
        return {
            'status': 'error',
            'message': f"Unknown landmark '{landmark}'. Available: {', '.join(SCAN_LANDMARKS.keys())}",
            'render_command': {'layer': 'ct', 'action': 'error'},
        }

    slice_num = SCAN_LANDMARKS[landmark]
    _scan_state['current_slice'] = slice_num

    return {
        'status': 'success',
        'landmark': landmark,
        'slice': slice_num,
        'total': SCAN_TOTAL_SLICES,
        'render_command': {
            'layer': 'ct',
            'action': 'navigate',
            'slice': slice_num,
            'total': SCAN_TOTAL_SLICES,
            'landmark': landmark,
        },
    }


def hide_scan() -> dict:
    """
    Use this tool when the surgeon asks to hide, clear, or dismiss the MRI scan
    overlay. Examples:
      "hide the MRI"
      "clear the scan"
      "remove the MRI overlay"
      "close the scan"
    """
    return {
        'status': 'success',
        'render_command': {
            'layer': 'ct',
            'action': 'hide',
        },
    }


# ---------------------------------------------------------------------------
# AR Agent Tools — Anatomy Renderer (3D model)
# ---------------------------------------------------------------------------

def rotate_model(axis: str, degrees: float) -> dict:
    """
    Use this tool when the surgeon asks to rotate the 3D anatomy model to see
    it from a different angle.

    Axis and degrees mapping:
      axis='y', degrees=0    — front, anterior, reset rotation
      axis='y', degrees=180  — back, posterior
      axis='y', degrees=90   — patient's right side, right lateral
      axis='y', degrees=-90  — patient's left side, left lateral
      axis='x', degrees=90   — top, superior, from above
      axis='x', degrees=-90  — bottom, inferior, from below

    Examples:
      "rotate the model to show the back" → axis='y', degrees=180
      "show me the posterior surface" → axis='y', degrees=180
      "I want to see it from above" → axis='x', degrees=90
      "show the front again" → axis='y', degrees=0
      "show the patient's left side" → axis='y', degrees=-90
    """
    axis = axis.lower().strip()
    if axis not in ('x', 'y', 'z'):
        return {
            'status': 'error',
            'message': "axis must be 'x', 'y', or 'z'",
            'render_command': {'layer': 'ar', 'action': 'error'},
        }

    return {
        'status': 'success',
        'axis': axis,
        'degrees': degrees,
        'render_command': {
            'layer': 'ar',
            'action': 'rotate',
            'axis': axis,
            'degrees': degrees,
        },
    }


def toggle_structure(structure: str, visible: bool) -> dict:
    """
    Use this tool when the surgeon asks to show or hide a specific anatomical
    structure in the 3D model. The structure names must exactly match the mesh
    names in the loaded GLB file.

    Available structures:
      brain               — the brain
      enhancing_tumor     — the tumor, enhancing part
      non_enhancing_core  — core, necrosis
      edema               — swelling, edema
      resection_cavity    — cavity

    visible=True  — show the structure (surgeon says: show, display, make visible)
    visible=False — hide the structure (surgeon says: hide, remove, turn off)

    Examples:
      "hide the brain"       → structure='brain', visible=False
      "show me the tumor"    → structure='enhancing_tumor', visible=True
      "hide the edema"       → structure='edema', visible=False
      "show the cavity"      → structure='resection_cavity', visible=True
    """
    structure = structure.lower().strip()
    if structure not in CASE_STRUCTURES:
        return {
            'status': 'error',
            'message': f"Unknown structure '{structure}'. Available: {', '.join(CASE_STRUCTURES)}",
            'render_command': {'layer': 'ar', 'action': 'error'},
        }

    return {
        'status': 'success',
        'structure': structure,
        'visible': visible,
        'render_command': {
            'layer': 'ar',
            'action': 'toggle',
            'structure': structure,
            'visible': visible,
        },
    }


def hide_3d() -> dict:
    """
    Use this tool when the surgeon asks to hide, close, dismiss, or remove
    the 3D anatomy model overlay entirely. Examples:
      "hide the 3D model"
      "close the 3D view"
      "remove the anatomy model"
      "close the model"
      "dismiss the 3D"
      "hide the anatomy"
    """
    return {
        'status': 'success',
        'render_command': {
            'layer': 'ar',
            'action': 'hide',
        },
    }


def reset_3d_view() -> dict:
    """
    Use this tool when the surgeon asks to reset the 3D model back to the
    default view, restore all hidden structures, or start the model view over.
    Examples:
      "reset the model"
      "show everything again"
      "restore the 3D view"
      "go back to default"
    """
    return {
        'status': 'success',
        'render_command': {
            'layer': 'ar',
            'action': 'reset',
        },
    }


def get_tumor_measurements() -> dict:
    """
    Use this tool when the surgeon asks how big the tumor is, for tumor volume,
    size or measurements, or for the volumes of the tumor regions.
    Examples: "how big is the tumor?", "tumor volume", "what are the measurements?"
    """
    labels = {
        'enhancing_tumor': 'Enhancing',
        'non_enhancing_core': 'Core',
        'edema': 'Edema',
        'resection_cavity': 'Cavity',
    }
    value = ' · '.join(
        f'{labels[name]} {CASE_VOLUMES[name]} cm³'
        for name in labels
        if name in CASE_VOLUMES
    )
    return {
        'status': 'success',
        'volumes_cm3': CASE_VOLUMES,
        'render_command': {
            'layer': 'clinical',
            'action': 'show',
            'field': 'tumor_volumes',
            'label': 'Tumor volumes',
            'value': value,
            'note': 'From CorteX segmentation of ' + CASE['source']['image'],
        },
    }


# ---------------------------------------------------------------------------
# Procedural Context Tool — surgical phase checklist
# ---------------------------------------------------------------------------

# Demo checklist content, not clinical guidance.
SURGICAL_PHASES: dict[str, dict] = {
    'positioning': {
        'label': 'Patient Positioning & Navigation',
        'checklist': [
            'Head fixed in pin holder, pressure points padded',
            'Neuronavigation registered to pre-op MRI',
            'Incision planned over tumor projection',
            'Antibiotic prophylaxis given before incision',
        ],
        'warning': 'Confirm correct side and site before incision',
    },
    'craniotomy': {
        'label': 'Craniotomy',
        'checklist': [
            'Burr holes placed per navigation plan',
            'Dura separated from bone before flap cut',
            'Bone flap stored per protocol',
            'Bone-edge bleeding controlled',
        ],
        'warning': 'Watch for venous sinus near the midline',
    },
    'dural_opening': {
        'label': 'Dural Opening',
        'checklist': [
            'Brain relaxation adequate before opening',
            'Dura opened along planned line',
            'Cortical surface compared with MRI',
            'Navigation accuracy rechecked on cortical landmarks',
        ],
        'warning': None,
    },
    'tumor_resection': {
        'label': 'Tumor Resection',
        'checklist': [
            'Tumor margins confirmed with navigation',
            'Eloquent areas identified before resection',
            'Resection cavity checked against 3D model',
            'Specimens labeled and sent to pathology',
        ],
        'warning': 'Brain shift reduces navigation accuracy as resection progresses',
    },
    'closure': {
        'label': 'Hemostasis & Closure',
        'checklist': [
            'Cavity dry under irrigation',
            'Dura closed watertight',
            'Bone flap replaced and fixed',
            'Instrument and sponge counts correct',
        ],
        'warning': None,
    },
}


def get_surgical_phase(phase: str) -> dict:
    """
    Use this tool when the surgeon asks about the current surgical phase,
    current checklist, what comes next, or when stating a phase transition.
    Call this tool with the appropriate phase name.

    Available phases (pass exactly as shown):
      positioning       — patient positioning and navigation setup
      craniotomy        — bone flap creation
      dural_opening     — opening the dura and checking navigation
      tumor_resection   — tumor removal
      closure           — hemostasis and closure

    Examples:
      "what phase are we in" → call with the current phase
      "we're starting the craniotomy" → phase='craniotomy'
      "show me the checklist" → call with current phase
      "what's next" → call with the upcoming or next phase
    """
    phase = phase.lower().strip().replace(' ', '_')
    if phase not in SURGICAL_PHASES:
        return {
            'status': 'error',
            'message': (
                f"Unknown phase '{phase}'. "
                f"Valid phases: {', '.join(SURGICAL_PHASES.keys())}"
            ),
            'render_command': {'layer': 'checklist', 'action': 'error'},
        }

    data = SURGICAL_PHASES[phase]
    return {
        'status': 'success',
        'phase': phase,
        'render_command': {
            'layer': 'checklist',
            'action': 'show',
            'phase': phase,
            'label': data['label'],
            'checklist': data['checklist'],
            'warning': data.get('warning'),
        },
    }

# hide surgical checklist
def hide_surgical_checklist() -> dict:
    """
    Use this tool when the surgeon asks to hide, clear, or dismiss the surgical
    checklist overlay. Examples:
      "hide the checklist"
      "clear the surgical checklist"
      "remove the checklist"
      "close the checklist panel"
    """
    return {
        'status': 'success',
        'render_command': {
            'layer': 'checklist',
            'action': 'hide',
        },
    }

# ---------------------------------------------------------------------------
# Session event log — in-memory, lives for the duration of one surgical session.
# Reset each time the FastAPI server restarts (per-session is correct for demo).
# ---------------------------------------------------------------------------
_SESSION_LOG: list[dict] = []


def log_ai_interaction(surgeon_said: str, orion_said: str) -> dict | None:
    """Server-side helper (NOT an agent tool). Called by main.py on turnComplete
    to auto-log every surgeon↔ORION exchange for conversation transparency.
    Returns the entry dict, or None if the turn had no meaningful content."""
    import datetime
    surgeon_said = (surgeon_said or '').strip()
    orion_said = (orion_said or '').strip()
    if not surgeon_said and not orion_said:
        return None
    # Truncate each side to keep log entries concise
    def _trunc(s, maxlen=80):
        return (s[:maxlen] + '…') if len(s) > maxlen else s
    parts = []
    if surgeon_said:
        parts.append(f'Q: {_trunc(surgeon_said)}')
    if orion_said:
        parts.append(f'A: {_trunc(orion_said)}')
    timestamp = datetime.datetime.now().strftime('%H:%M:%S')
    entry = {
        'type': 'ai_interaction',
        'note': ' | '.join(parts),
        'timestamp': timestamp,
    }
    _SESSION_LOG.append(entry)
    return entry


# ---------------------------------------------------------------------------
# DOC Agent Tools — Intraoperative Documentation
# ---------------------------------------------------------------------------

def log_event(event_type: str, note: str = '') -> dict:
    """
    Use this tool when the surgeon voice-logs any intraoperative event.
    Auto-timestamps the event and appends it to the session operative log.

    event_type — pass exactly one of:
      timeout_complete  — WHO surgical safety timeout completed
      incision          — Incision made
      tumor_resected    — Tumor resection completed
      specimen_sent     — Specimen sent to pathology
      complication      — Unexpected intraoperative event (describe in note)
      milestone         — Key procedural step completed (describe in note)
      note              — General surgeon observation (describe in note)

    Examples:
      "log incision"                   → event_type='incision'
      "tumor resected"                 → event_type='tumor_resected'
      "resection complete"             → event_type='tumor_resected'
      "specimen sent to pathology"     → event_type='specimen_sent'
      "log complication — bleeding"    → event_type='complication', note='bleeding'
      "milestone: dura closed"         → event_type='milestone', note='dura closed'
      "note: ..."                      → event_type='note', note='...'
    """
    import datetime
    valid_types = {
        'timeout_complete', 'incision', 'tumor_resected', 'specimen_sent',
        'complication', 'milestone', 'note',
    }
    etype = event_type.lower().strip().replace(' ', '_')
    if etype not in valid_types:
        etype = 'note'
    entry = {
        'type': etype,
        'note': note.strip(),
        'timestamp': datetime.datetime.now().strftime('%H:%M:%S'),
    }
    _SESSION_LOG.append(entry)
    return {
        'status': 'success',
        'render_command': {
            'layer': 'log',
            'action': 'append',
            'entry': entry,
        },
    }


def show_event_log() -> dict:
    """
    Use this tool when the surgeon asks to see the operative log or event log.
    Displays the full session event timeline tile on screen.

    Trigger phrases: "show operative log", "show the log", "show event log",
    "what have we logged", "display the timeline"
    """
    return {
        'status': 'success',
        'render_command': {
            'layer': 'log',
            'action': 'show_all',
            'entries': list(_SESSION_LOG),
        },
    }


def hide_event_log() -> dict:
    """
    Use this tool when the surgeon asks to hide or close the operative log panel.

    Trigger phrases: "hide the log", "close the log", "dismiss the log"
    """
    return {
        'status': 'success',
        'render_command': {
            'layer': 'log',
            'action': 'hide',
        },
    }


# ---------------------------------------------------------------------------
# Drug Safety Checker Tools
# ---------------------------------------------------------------------------

# Demo rules only, not a clinical drug database.
_DRUG_DB: dict[str, dict] = {
    'cefazolin': {
        'class': 'Cephalosporin antibiotic',
        'cross_allergies': ['cefazolin', 'cephalosporin'],
        'cross_allergy_note': 'Documented allergy to this drug',
        'interactions': {},
        'alternative': 'vancomycin',
    },
    'vancomycin': {
        'class': 'Glycopeptide antibiotic',
        'cross_allergies': [],
        'cross_allergy_note': '',
        'interactions': {},
        'alternative': None,
    },
    'dexamethasone': {
        'class': 'Corticosteroid',
        'cross_allergies': [],
        'cross_allergy_note': '',
        'interactions': {},
        'alternative': None,
    },
    'mannitol': {
        'class': 'Osmotic diuretic',
        'cross_allergies': [],
        'cross_allergy_note': '',
        'interactions': {},
        'alternative': None,
    },
    'levetiracetam': {
        'class': 'Antiepileptic',
        'cross_allergies': [],
        'cross_allergy_note': '',
        'interactions': {},
        'alternative': None,
    },
    'propofol': {
        'class': 'IV anesthetic',
        'cross_allergies': [],
        'cross_allergy_note': '',
        'interactions': {},
        'alternative': None,
    },
    'fentanyl': {
        'class': 'Opioid analgesic',
        'cross_allergies': [],
        'cross_allergy_note': '',
        'interactions': {},
        'alternative': None,
    },
    'rocuronium': {
        'class': 'Neuromuscular blocker',
        'cross_allergies': [],
        'cross_allergy_note': '',
        'interactions': {},
        'alternative': None,
    },
    'ondansetron': {
        'class': 'Antiemetic',
        'cross_allergies': [],
        'cross_allergy_note': '',
        'interactions': {},
        'alternative': None,
    },
    'tranexamic_acid': {
        'class': 'Antifibrinolytic',
        'cross_allergies': [],
        'cross_allergy_note': '',
        'interactions': {},
        'alternative': None,
    },
    'heparin': {
        'class': 'Anticoagulant',
        'cross_allergies': [],
        'cross_allergy_note': '',
        'interactions': {'low_platelets': 'Bleeding risk with platelets <100K'},
        'alternative': None,
    },
}


def check_drug_safety(drug_name: str) -> dict:
    """
    Use this tool when the surgeon asks whether a medication is safe to give.
    Cross-checks the drug against the patient's allergies, current medications,
    and lab values.

    drug_name — the medication to check (e.g. heparin, cefazolin, ketorolac)

    Examples:
      "can I give heparin?"         → drug_name='heparin'
      "is cefazolin safe?"          → drug_name='cefazolin'
      "check ketorolac"             → drug_name='ketorolac'
      "can we use morphine?"        → drug_name='morphine'
    """
    name = drug_name.lower().strip().replace(' ', '_')
    drug = _DRUG_DB.get(name)
    if not drug:
        known = ', '.join(sorted(_DRUG_DB.keys()))
        return {'status': 'error', 'message': f'Drug "{name}" not in database. Known drugs: {known}'}

    allergies_raw = _PATIENT_DATA.get('allergies', {}).get('value', '').lower()
    meds_raw = _PATIENT_DATA.get('medications', {}).get('value', '').lower()
    platelets_raw = _PATIENT_DATA.get('platelets', {}).get('value', '')

    warnings = []

    # Check cross-allergies
    for allergen in drug['cross_allergies']:
        if allergen in allergies_raw:
            warnings.append(
                f'ALLERGY WARNING: Patient has {allergen} allergy. '
                f'{drug["cross_allergy_note"]}.'
                + (f' Consider {drug["alternative"]} instead.' if drug['alternative'] else '')
            )

    # Check medication interactions
    for trigger, msg in drug['interactions'].items():
        if trigger == 'aspirin' and 'aspirin' in meds_raw:
            warnings.append(f'INTERACTION: {msg}. Note: aspirin may be held — check status.')
        elif trigger == 'low_platelets':
            plat_num = int(''.join(c for c in platelets_raw if c.isdigit()) or '999')
            if plat_num < 100:
                warnings.append(f'LAB WARNING: {msg}. Current platelets: {platelets_raw}.')
        elif trigger == 'anticoagulant' and ('heparin' in meds_raw or 'warfarin' in meds_raw):
            warnings.append(f'INTERACTION: {msg}.')

    status = 'caution' if warnings else 'safe'
    summary = '; '.join(warnings) if warnings else f'{name} — no allergy conflicts or interactions detected. Safe to administer.'

    return {
        'status': 'success',
        'drug': name,
        'drug_class': drug['class'],
        'safety_status': status,
        'summary': summary,
        'warnings': warnings,
        'render_command': {
            'layer': 'clinical',
            'action': 'show',
            'field': 'drug_check',
            'data': {'drug': name, 'status': status, 'summary': summary},
        },
    }


# ---------------------------------------------------------------------------
# Root Agent Tool — crosses all three display domains
# ---------------------------------------------------------------------------

def show_only_ar() -> dict:
    """
    Use this tool when the surgeon asks to keep ONLY the 3D anatomy model
    and close or hide everything else (CT scan, patient data, checklists).
    Examples:
      "only keep the 3D model"
      "keep only the anatomy"
      "close everything except the 3D"
      "hide everything but the model"
      "just show me the 3D"
    Do NOT route this to a sub-agent. Handle it directly at the root level.
    """
    return {
        'status': 'success',
        'render_command': {
            'layer': 'all_except_ar',
            'action': 'hide',
        },
    }


def show_agent_summary(title: str, content: str, bullets: list = None) -> dict:
    """
    Display a formatted text summary tile on the surgical console.
    Call this as the FINAL step after all other display tools to surface
    the agent's key output as a readable tile for the surgeon.

    Args:
        title:   Tile header (e.g. 'WHO Surgical Safety Checklist', 'Handoff — SBAR')
        content: Introductory paragraph or free-form text (can be empty string '')
        bullets: Optional list of numbered/bulleted items (protocol steps, SBAR sections, etc.)
    """
    return {
        'status': 'displayed',
        'render_command': {
            'layer': 'summary',
            'action': 'show',
            'title': title,
            'content': content,
            'bullets': bullets or [],
        },
    }


def hide_all_overlays() -> dict:
    """
    Use this tool when the surgeon asks to clear, hide, close, or dismiss ALL
    active overlays simultaneously — CT scan, clinical data, 3D model, surgical
    checklist, operative log, and any summary or complication panels.
    Trigger on ANY of the following (and natural variations):
      "clear everything"        "hide everything"
      "hide all overlays"       "hide all"
      "clear the screen"        "clear all"
      "remove everything"       "remove all"
      "clean up"                "clean the screen"
      "close everything"        "close all"
      "close all panels"        "close the panels"
      "dismiss everything"      "dismiss all"
      "ORION, clear"            "go back to just the video"
      "get rid of everything"   "take it all away"
    Do NOT route this to a sub-agent. Handle it directly at the root level.
    """
    return {
        'status': 'success',
        'render_command': {
            'layer': 'all',
            'action': 'hide',
        },
    }
