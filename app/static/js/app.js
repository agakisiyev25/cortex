/** CorteX WebSocket, audio, tool routing, and console interaction. */

import { startAudioPlayerWorklet } from './audio-player.js';
import { startAudioRecorderWorklet, stopMicrophone } from './audio-recorder.js';

const CONFIG = Object.assign({ caseUrl: '/static/case/case.json' }, window.ORION_CONFIG || {});
const isDemo = new URLSearchParams(window.location.search).get('demo') === '1';

const voiceTrace = document.getElementById('voice-trace');
const voiceStateMain = document.getElementById('vs-main');
const voiceStateSub = document.getElementById('vs-sub');
const liveStatus = document.getElementById('live-status');
const liveStatusText = document.getElementById('live-status-text');
const sessionTimer = document.getElementById('session-timer');
const disconnectButton = document.getElementById('disconnect-button');
const voiceModePtt = document.getElementById('voice-mode-ptt');
const voiceModeHandsFree = document.getElementById('voice-mode-handsfree');
const transcriptLog = document.getElementById('transcript-log');
const actionsFeed = document.getElementById('actions-feed');
const typedCommand = document.getElementById('typed-command');
const typedInput = document.getElementById('typed-input');

let caseData = null;
let patientData = null;
let audioPlayerNode = null;
let audioRecorderCtx = null;
let micStream = null;
let audioSuppressed = false;
let _lastSuppressTime = 0;
let ws = null;
let _autoReconnect = false;
let currentOrionEntry = null;
let currentSurgeonEntry = null;
let handsFree = false;
let talking = false;
let voiceState = 'offline';
let thinkingTimer = null;
let speakingTimer = null;
let timerInterval = null;
let sessionStarted = 0;
let spaceHeld = false;
const transcriptTimers = new WeakMap();

const _dispatchedTools = new Map();
const TOOL_DEDUP_MS = 4000;
const pendingActions = new Map();

const pageReady = initialisePage();

async function initialisePage() {
  const response = await fetch('/api/case');
  if (!response.ok) throw new Error(`Case API failed: ${response.status}`);
  const payload = await response.json();
  caseData = payload.case;
  patientData = payload.patient;

  document.getElementById('case-id').textContent = caseData.case_id;
  document.getElementById('case-procedure').textContent = patientData.procedure.value;
  const allergies = patientData.allergies.value.replace(/\s*\([^)]*\)/g, '');
  document.getElementById('allergy-chip').textContent = `Allergies: ${allergies}`;

  Drawer.init(caseData);
  Banner.init();
  Modal.init();
  CTViewer.init({
    canvasId: 'ct-canvas',
    slicesBase: caseData.slices.base_url,
    totalSlices: caseData.slices.count,
    pad: caseData.slices.pad,
    landmarks: caseData.landmarks,
    startSlice: caseData.landmarks.tumor,
    modality: caseData.modality,
    structures: caseData.structures,
    displayNames: caseData.display_names,
    colors: caseData.colors,
  });
  Anatomy3D.init({
    canvasId: 'ar-canvas',
    modelUrl: caseData.model_url,
    defaultView: caseData.default_view,
    structures: caseData.structures,
    displayNames: caseData.display_names,
    colors: caseData.colors,
  });

  if (isDemo) {
    setStatus('demo');
    installDemoApi();
  } else {
    setStatus('offline');
  }
}

async function connect() {
  if (isDemo) return;
  await pageReady;
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;

  const timestamp = Date.now();
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  setStatus('connecting');
  ws = new WebSocket(`${protocol}://${window.location.host}/ws/surgeon_${timestamp}/session_${timestamp}`);
  ws.binaryType = 'arraybuffer';

  ws.onopen = async () => {
    setStatus('active');
    _startSessionTimer();
    try {
      [audioPlayerNode] = await startAudioPlayerWorklet();
      [, audioRecorderCtx, micStream] = await startAudioRecorderWorklet(audioRecorderHandler);
    } catch (error) {
      console.error('Audio init failed:', error);
      disconnect();
    }
  };

  ws.onmessage = (event) => {
    if (typeof event.data === 'string') handleServerEvent(event.data);
  };

  ws.onclose = () => {
    talking = false;
    _dispatchedTools.clear();
    pendingActions.forEach((items) => items.forEach((item) => clearTimeout(item.timer)));
    pendingActions.clear();
    currentOrionEntry = null;
    currentSurgeonEntry = null;
    if (micStream) { stopMicrophone(micStream); micStream = null; }
    if (audioRecorderCtx) {
      try { audioRecorderCtx.close(); } catch (_) {}
      audioRecorderCtx = null;
    }
    if (audioPlayerNode) {
      try {
        audioPlayerNode.port.postMessage({ command: 'endOfAudio' });
        audioPlayerNode.disconnect();
        audioPlayerNode.context.close();
      } catch (_) {}
      audioPlayerNode = null;
    }
    _stopSessionTimer();
    setStatus('offline');
    if (_autoReconnect) {
      _autoReconnect = false;
      setTimeout(connect, 1500);
    }
  };

  ws.onerror = () => console.error('CorteX WebSocket error');
}

function disconnect() {
  if (ws) {
    ws.close();
    ws = null;
  }
}

function _bargeIn() {
  if (audioSuppressed) return;
  audioSuppressed = true;
  _lastSuppressTime = Date.now();
  if (audioPlayerNode) audioPlayerNode.port.postMessage({ command: 'endOfAudio' });
  _finishTranscript(currentOrionEntry);
  currentOrionEntry = null;
}

function audioRecorderHandler(pcmData) {
  if (talking) {
    const samples = new Int16Array(pcmData);
    let energy = 0;
    for (let index = 0; index < samples.length; index += 1) {
      const sample = samples[index] / 32768;
      energy += sample * sample;
    }
    const rms = Math.sqrt(energy / Math.max(1, samples.length));
    VoiceTrace.setLevel(Math.min(1, rms * 6));
  }
  if (ws?.readyState === WebSocket.OPEN && (handsFree || talking)) {
    ws.send(pcmData);
  }
}

function startTalking() {
  if (handsFree || talking || ws?.readyState !== WebSocket.OPEN) return;
  _bargeIn();
  talking = true;
  clearTimeout(thinkingTimer);
  setStatus('talking');
}

function stopTalking() {
  if (!talking) return;
  talking = false;
  VoiceTrace.setLevel(0);
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'audio_stream_end' }));
  }
  setStatus('thinking');
  clearTimeout(thinkingTimer);
  thinkingTimer = setTimeout(() => {
    if (voiceState === 'thinking') setStatus('active');
  }, 8000);
}

function _markSpeaking() {
  clearTimeout(thinkingTimer);
  setStatus('speaking');
  clearTimeout(speakingTimer);
  speakingTimer = setTimeout(() => {
    if (ws?.readyState === WebSocket.OPEN && voiceState === 'speaking') setStatus('active');
  }, 600);
}

function base64ToArray(base64) {
  const standard = base64.replace(/-/g, '+').replace(/_/g, '/');
  const binary = atob(standard);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes.buffer;
}

function handleServerEvent(jsonString) {
  let event;
  try { event = JSON.parse(jsonString); } catch (_) { return; }

  if (event.type === 'error') {
    console.error(event.message || 'Unknown live-session error');
    _autoReconnect = true;
    return;
  }

  const inputText = event.inputTranscription?.text ?? event.input_transcription?.text;
  if (inputText) {
    _bargeIn();
    _upsertTranscript('surgeon', inputText);
  }

  const outputText = event.outputTranscription?.text ?? event.output_transcription?.text;
  if (outputText) {
    if (Date.now() - _lastSuppressTime > 300) audioSuppressed = false;
    _markSpeaking();
    _upsertTranscript('orion', outputText);
  }

  const parts = event.content?.parts ?? [];
  for (const part of parts) {
    const inlineData = part.inlineData ?? part.inline_data;
    const mimeType = inlineData?.mimeType ?? inlineData?.mime_type ?? '';
    if (inlineData && mimeType.startsWith('audio/pcm') && audioPlayerNode && !audioSuppressed) {
      _markSpeaking();
      audioPlayerNode.port.postMessage(base64ToArray(inlineData.data));
    }

    if (part.text && event.content?.role === 'model' && !outputText) {
      _markSpeaking();
      _upsertTranscript('orion', part.text);
    }

    const functionCall = part.functionCall ?? part.function_call;
    if (functionCall) {
      const args = functionCall.args ?? functionCall.arguments ?? {};
      const key = `${functionCall.name}:${JSON.stringify(args)}`;
      const now = Date.now();
      if (now - (_dispatchedTools.get(key) ?? 0) > TOOL_DEDUP_MS) {
        _dispatchedTools.set(key, now);
        queueAction(functionCall.name, args);
        dispatchRenderCommand(functionCall.name, args);
      }
    }

    const functionResponse = part.functionResponse ?? part.function_response;
    if (functionResponse) {
      handleFunctionResponse(functionResponse);
      resolveAction(functionResponse);
    }
  }

  if (event.interrupted) _bargeIn();
  if (event.turnComplete ?? event.turn_complete) {
    _finishTranscript(currentSurgeonEntry);
    _finishTranscript(currentOrionEntry);
    currentSurgeonEntry = null;
    currentOrionEntry = null;
  }
}

function dispatchRenderCommand(toolName, args = {}) {
  switch (toolName) {
    case 'hide_patient_data': Drawer.remove('patient'); break;
    case 'navigate_scan': CTViewer.navigate(args.direction, args.count || 1); break;
    case 'jump_to_landmark': CTViewer.jumpToLandmark(args.landmark); break;
    case 'hide_scan': CTViewer.hide(); break;
    case 'rotate_model': Anatomy3D.rotate(args.axis, args.degrees); break;
    case 'toggle_structure': Anatomy3D.toggleStructure(args.structure, args.visible); break;
    case 'reset_3d_view': Anatomy3D.reset(); break;
    case 'hide_3d': Anatomy3D.hide(); break;
    case 'hide_surgical_checklist': Drawer.remove('checklist'); break;
    case 'hide_event_log': Drawer.remove('log'); break;
    case 'hide_all_overlays':
      Drawer.clear(); Banner.hide(); Modal.hide();
      break;
    case 'show_only_ar':
      Drawer.clear(); Banner.hide(); Modal.hide(); CTViewer.hide();
      document.getElementById('viewers').classList.remove('ar-hidden');
      window.dispatchEvent(new Event('resize'));
      break;
    default:
      break;
  }
}

function handleFunctionResponse(functionResponse) {
  const response = functionResponse.response || {};
  const command = response.render_command;
  if (!command) return;

  if (command.layer === 'clinical' && command.action === 'show') {
    if (command.field === 'drug_check') {
      Banner.show(response);
    } else if (command.field === 'tumor_volumes') {
      Drawer.showVolumes(response.volumes_cm3, command.note);
    } else {
      Drawer.showPatient([{
        field: command.field,
        label: command.label,
        value: command.value,
        note: command.note,
      }], true);
    }
  } else if (command.layer === 'clinical' && command.action === 'show_all') {
    Drawer.showPatient(command.fields, false);
  } else if (command.layer === 'clinical' && command.action === 'hide') {
    Drawer.remove('patient');
  } else if (command.layer === 'checklist' && command.action === 'show') {
    Drawer.showChecklist(command);
  } else if (command.layer === 'checklist' && command.action === 'hide') {
    Drawer.remove('checklist');
  } else if (command.layer === 'log' && command.action === 'append') {
    Drawer.appendLog(command.entry);
  } else if (command.layer === 'log' && command.action === 'show_all') {
    Drawer.showLog(command.entries);
  } else if (command.layer === 'log' && command.action === 'hide') {
    Drawer.remove('log');
  } else if (command.layer === 'summary' && command.action === 'show') {
    Modal.show(command.title, command.content, command.bullets);
  } else if (command.layer === 'summary' && command.action === 'hide') {
    Modal.hide();
  } else if (command.layer === 'all' && command.action === 'hide') {
    Drawer.clear(); Banner.hide(); Modal.hide();
  }
}

function queueAction(name, args) {
  const item = { args, done: false, timer: null };
  item.timer = setTimeout(() => {
    if (!item.done) {
      item.done = true;
      addAction(name, args, null);
    }
  }, 1000);
  const queue = pendingActions.get(name) || [];
  queue.push(item);
  pendingActions.set(name, queue);
}

function resolveAction(functionResponse) {
  const name = functionResponse.name;
  const queue = pendingActions.get(name) || [];
  const item = queue.find((candidate) => !candidate.done);
  if (!item) return;
  item.done = true;
  clearTimeout(item.timer);
  addAction(name, item.args, functionResponse.response || null);
  pendingActions.set(name, queue.filter((candidate) => candidate !== item));
}

function addAction(name, args, response) {
  const command = response?.render_command;
  const eventWords = {
    timeout_complete: 'Time-out complete', incision: 'Incision', tumor_resected: 'Tumor resected',
    specimen_sent: 'Specimen sent', complication: 'Complication', milestone: 'Milestone', note: 'Note',
  };
  const landmarkWords = String(args.landmark || '').replace(/_/g, ' ');
  const structureName = caseData.display_names[args.structure] || String(args.structure || '').replace(/_/g, ' ');
  const texts = {
    display_patient_data: `Patient: ${patientData[args.field]?.label || args.field}`,
    display_all_patient_data: 'Patient record opened',
    hide_patient_data: 'Patient card closed',
    navigate_scan: `MRI ${args.direction} ${args.count || 1} → slice ${response?.slice ?? command?.slice ?? '—'}`,
    jump_to_landmark: `MRI → ${landmarkWords} (slice ${response?.slice ?? command?.slice ?? '—'})`,
    hide_scan: 'MRI hidden',
    rotate_model: `3D → ${Anatomy3D.viewNameFor(args.axis, args.degrees)}`,
    toggle_structure: `3D: ${structureName} ${args.visible ? 'shown' : 'hidden'}`,
    reset_3d_view: '3D reset',
    hide_3d: '3D hidden',
    get_tumor_measurements: 'Tumor volumes measured',
    get_surgical_phase: `Checklist: ${command?.label || String(args.phase || '').replace(/_/g, ' ')}`,
    hide_surgical_checklist: 'Checklist closed',
    check_drug_safety: `Drug check: ${response?.drug || args.drug_name}`,
    log_event: `Logged: ${eventWords[response?.render_command?.entry?.type || args.event_type] || args.event_type}`,
    show_event_log: 'Operative log opened',
    hide_event_log: 'Operative log closed',
    show_agent_summary: response?.render_command?.title || args.title,
    hide_all_overlays: 'Display cleared',
    show_only_ar: '3D only',
  };
  actionsFeed.querySelector('.empty-row')?.remove();
  actionsFeed.querySelectorAll('.fresh').forEach((item) => item.classList.remove('fresh'));
  const row = document.createElement('li');
  row.className = `fresh${name === 'check_drug_safety' && response?.safety_status === 'caution' ? ' alarm' : ''}`;
  row.innerHTML = `<time>${new Date().toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit' })}</time><span>${escapeHtml(texts[name] || name)}</span>`;
  actionsFeed.prepend(row);
  while (actionsFeed.children.length > 50) actionsFeed.lastElementChild.remove();
}

function setStatus(state) {
  voiceState = state;
  const traceState = state === 'active' || state === 'demo' ? 'idle' : state;
  voiceTrace.dataset.state = traceState;
  VoiceTrace.setState(traceState);
  const connected = ['active', 'talking', 'thinking', 'speaking', 'demo'].includes(state);
  disconnectButton.hidden = !connected;
  const labels = {
    offline: ['Tap to connect', 'CorteX is offline'],
    connecting: ['Connecting', ''],
    active: handsFree ? ['Listening hands-free', ''] : ['Hold Space to talk', 'or hold the trace'],
    talking: ['Listening', 'Release to send'],
    thinking: ['Thinking', ''],
    speaking: ['Speaking', 'Hold Space to interrupt'],
    demo: ['Hold Space to talk', 'or hold the trace'],
  };
  [voiceStateMain.textContent, voiceStateSub.textContent] = labels[state] || labels.offline;

  liveStatus.dataset.state = 'offline';
  if (state === 'demo') {
    liveStatus.dataset.state = 'demo'; liveStatusText.textContent = 'Demo';
  } else if (state === 'connecting') {
    liveStatus.dataset.state = 'connecting'; liveStatusText.textContent = 'Connecting';
  } else if (connected) {
    liveStatus.dataset.state = 'live'; liveStatusText.textContent = 'Live';
  } else {
    liveStatusText.textContent = 'Offline';
  }
}

function _startSessionTimer() {
  sessionStarted = Date.now();
  clearInterval(timerInterval);
  const update = () => {
    const seconds = Math.floor((Date.now() - sessionStarted) / 1000);
    sessionTimer.textContent = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  };
  update();
  timerInterval = setInterval(update, 1000);
}

function _stopSessionTimer() {
  clearInterval(timerInterval);
  timerInterval = null;
  sessionTimer.textContent = '00:00';
}

function _upsertTranscript(speaker, text) {
  if (!text?.trim()) return;
  const isSurgeon = speaker === 'surgeon';
  const current = isSurgeon ? currentSurgeonEntry : currentOrionEntry;
  transcriptLog.querySelector('.empty')?.remove();
  if (current) {
    current.querySelector('.text').textContent = text;
  } else {
    const entry = document.createElement('div');
    entry.className = `turn ${speaker === 'orion' ? 'cortex' : 'surgeon'}`;
    entry.innerHTML = `<span class="who">${isSurgeon ? 'Surgeon' : 'CorteX'}</span><p class="text">${escapeHtml(text)}</p>`;
    transcriptLog.appendChild(entry);
    while (transcriptLog.children.length > 30) transcriptLog.firstElementChild.remove();
    if (isSurgeon) currentSurgeonEntry = entry;
    else currentOrionEntry = entry;
  }
  const entry = isSurgeon ? currentSurgeonEntry : currentOrionEntry;
  entry.classList.add('streaming');
  clearTimeout(transcriptTimers.get(entry));
  transcriptTimers.set(entry, setTimeout(() => entry.classList.remove('streaming'), 1200));
  transcriptLog.scrollTop = transcriptLog.scrollHeight;
}

function _finishTranscript(entry) {
  if (!entry) return;
  clearTimeout(transcriptTimers.get(entry));
  transcriptTimers.delete(entry);
  entry.classList.remove('streaming');
}

function escapeHtml(value) {
  return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function installDemoApi() {
  window.cortexDemo = {
    async call(name, args = {}) {
      await pageReady;
      queueAction(name, args);
      dispatchRenderCommand(name, args);
      const response = await fetch(`/dev/tool/${encodeURIComponent(name)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(args),
      });
      if (!response.ok) throw new Error(`Demo tool ${name} failed: ${response.status}`);
      const result = await response.json();
      handleFunctionResponse(result);
      resolveAction(result);
      return result.response;
    },
    say(role, text) {
      const speaker = String(role).toLowerCase() === 'surgeon' ? 'surgeon' : 'orion';
      _upsertTranscript(speaker, text);
      if (speaker === 'surgeon') {
        _finishTranscript(currentSurgeonEntry);
        currentSurgeonEntry = null;
      } else {
        _finishTranscript(currentOrionEntry);
        currentOrionEntry = null;
      }
    },
  };
}

voiceTrace.addEventListener('click', () => {
  if (!isDemo && ws?.readyState !== WebSocket.OPEN) connect();
});
voiceTrace.addEventListener('pointerdown', (event) => {
  if (ws?.readyState === WebSocket.OPEN && !handsFree) {
    event.preventDefault();
    voiceTrace.setPointerCapture?.(event.pointerId);
    startTalking();
  }
});
voiceTrace.addEventListener('pointerup', stopTalking);
voiceTrace.addEventListener('pointercancel', stopTalking);

document.addEventListener('keydown', (event) => {
  if (event.code !== 'Space' || event.repeat || handsFree || document.activeElement === typedInput) return;
  if (ws?.readyState !== WebSocket.OPEN) return;
  event.preventDefault();
  spaceHeld = true;
  startTalking();
});
document.addEventListener('keyup', (event) => {
  if (event.code !== 'Space' || !spaceHeld) return;
  event.preventDefault();
  spaceHeld = false;
  stopTalking();
});

function setHandsFree(enabled) {
  handsFree = enabled;
  if (talking) stopTalking();
  voiceModePtt.setAttribute('aria-pressed', String(!handsFree));
  voiceModeHandsFree.setAttribute('aria-pressed', String(handsFree));
  if (ws?.readyState === WebSocket.OPEN) setStatus('active');
}

voiceModePtt.addEventListener('click', () => setHandsFree(false));
voiceModeHandsFree.addEventListener('click', () => setHandsFree(true));
disconnectButton.addEventListener('click', disconnect);

typedCommand.addEventListener('submit', async (event) => {
  event.preventDefault();
  const value = typedInput.value.trim();
  if (!value) return;
  _upsertTranscript('surgeon', value);
  _finishTranscript(currentSurgeonEntry);
  _finishTranscript(currentOrionEntry);
  currentSurgeonEntry = null;
  currentOrionEntry = null;
  typedInput.value = '';
  if (isDemo) return;
  await connect();
  const send = () => ws?.send(JSON.stringify({ type: 'text', content: value }));
  if (ws?.readyState === WebSocket.OPEN) send();
  else ws?.addEventListener('open', send, { once: true });
});

window.ORION_relayoutModals = () => window.dispatchEvent(new Event('resize'));
