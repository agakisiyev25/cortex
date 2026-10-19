/** CorteX viewer overlays: drawer cards, drug banner, and summary modal. */

'use strict';

const _overlayEscape = (value) => String(value ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

const _overlayIcons = {
  x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"><path d="M12 3.5l9.5 16.5h-19z"/><path d="M12 10v4.5M12 17.4v.1" stroke-linecap="round"/></svg>',
  ok: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l3 3 5-6"/></svg>',
};

const _overlayCloseButton = (label) => `<button class="x" type="button" aria-label="${_overlayEscape(label)}">${_overlayIcons.x}</button>`;

const Drawer = (() => {
  let root = null;
  let inner = null;
  let caseData = null;
  let logEntries = [];
  const cards = new Map();
  const eventNames = {
    timeout_complete: 'Time-out complete',
    incision: 'Incision',
    tumor_resected: 'Tumor resected',
    specimen_sent: 'Specimen sent',
    complication: 'Complication',
    milestone: 'Milestone',
    note: 'Note',
  };

  function init(kase) {
    root = document.getElementById('drawer');
    inner = root.querySelector('.drawer-inner');
    caseData = kase;
  }

  function _syncOpen() {
    root.classList.toggle('open', inner.children.length > 0);
  }

  function _card(kind, title, subtitle, bodyHtml) {
    const card = document.createElement('section');
    card.className = 'card';
    card.dataset.kind = kind;
    card.innerHTML = `
      <div class="card-head">
        <div class="card-title">${_overlayEscape(title)}${subtitle ? `<small>${_overlayEscape(subtitle)}</small>` : ''}</div>
        ${_overlayCloseButton(`Close ${title}`)}
      </div>
      ${bodyHtml}`;
    card.querySelector('.x').addEventListener('click', () => remove(kind));

    const existing = cards.get(kind);
    if (existing) existing.replaceWith(card);
    else inner.prepend(card);
    cards.set(kind, card);

    while (inner.children.length > 3) {
      const oldest = inner.lastElementChild;
      cards.delete(oldest.dataset.kind);
      oldest.remove();
    }
    _syncOpen();
  }

  function _isFlagged(note) {
    return /^(low|high|abnormal)\b|required/i.test(String(note || ''));
  }

  function _valueParts(value) {
    const text = String(value || '');
    if (!/^\d/.test(text)) return null;
    const [number, ...unit] = text.split(/\s+/);
    return { number, unit: unit.join(' ') };
  }

  function _readout(field) {
    if (!field) return '';
    const parts = _valueParts(field.value) || { number: field.value, unit: '' };
    const flagged = _isFlagged(field.note);
    return `<div class="readout${flagged ? ' flag' : ''}">
      <label>${_overlayEscape(field.label)}</label>
      <b>${_overlayEscape(parts.number)}</b>
      ${parts.unit ? `<em>${_overlayEscape(parts.unit)}</em>` : ''}
      ${flagged ? `<p>${_overlayEscape(field.note)}</p>` : ''}
    </div>`;
  }

  function showPatient(fields, single = false) {
    const byName = Object.fromEntries((fields || []).map((field) => [field.field, field]));
    if (single) {
      const field = fields?.[0] || {};
      const parts = _valueParts(field.value);
      const value = parts
        ? `<div class="single"><b>${_overlayEscape(parts.number)}</b>${parts.unit ? `<em>${_overlayEscape(parts.unit)}</em>` : ''}</div>`
        : `<div class="single-text">${_overlayEscape(field.value)}</div>`;
      const note = field.note
        ? `<p class="single-note${_isFlagged(field.note) ? ' flag' : ''}">${_overlayEscape(field.note)}</p>`
        : '';
      _card('patient', field.label || 'Patient', '', `${value}${note}`);
      return;
    }

    const age = byName.age || {};
    const weight = byName.weight || {};
    const ageNumber = _valueParts(age.value)?.number || age.value || '';
    const subtitle = `${ageNumber}-year-old ${String(age.note || '').toLowerCase()}, ${weight.value || ''}`;
    const readouts = ['hemoglobin', 'platelets', 'inr', 'creatinine'].map((name) => _readout(byName[name])).join('');
    const secondary = ['bp', 'weight', 'age'].map((name) => _readout(byName[name])).join('');
    const facts = ['diagnosis', 'procedure', 'allergies', 'medications'].map((name) => {
      const field = byName[name];
      if (!field) return '';
      const flagged = _isFlagged(field.note);
      return `<div class="fact${name === 'allergies' ? ' allergy' : ''}">
        <label>${_overlayEscape(field.label)}</label>
        <div>${_overlayEscape(field.value)}</div>
        ${flagged ? `<p class="flag">${_overlayEscape(field.note)}</p>` : ''}
      </div>`;
    }).join('');
    _card('patient', 'Patient', subtitle, `
      <div class="readouts">${readouts}</div>
      <div class="readouts three">${secondary}</div>
      <div class="facts">${facts}</div>`);
  }

  function showVolumes(volumes, sourceNote) {
    const tumorOrder = ['enhancing_tumor', 'non_enhancing_core', 'edema'];
    const presentTumor = tumorOrder.filter((name) => volumes?.[name] !== undefined);
    const total = presentTumor.reduce((sum, name) => sum + Number(volumes[name]), 0);
    const bar = presentTumor.map((name) => `<i style="--c:${_overlayEscape(caseData.colors[name])};flex:${Number(volumes[name])}"></i>`).join('');
    const row = (name, className = '') => `<div class="vrow${className ? ` ${className}` : ''}" style="--c:${_overlayEscape(caseData.colors[name] || 'transparent')}">
      <span>${_overlayEscape(caseData.display_names[name])}</span>
      <b>${Number(volumes[name]).toFixed(1)}<small>cm³</small></b>
    </div>`;
    const tumorRows = presentTumor.map((name) => row(name)).join('');
    const cavity = volumes?.resection_cavity !== undefined ? row('resection_cavity') : '';
    _card('volumes', 'Tumor volumes', '', `
      <div class="vbar">${bar}</div>
      <div class="vrows">
        ${tumorRows}
        <div class="vrow total"><span>Total tumor</span><b>${total.toFixed(1)}<small>cm³</small></b></div>
        ${cavity}
      </div>
      <p class="note">${_overlayEscape(sourceNote)}</p>`);
  }

  function showChecklist(command) {
    const items = (command.checklist || []).map((item) => `<li>${_overlayEscape(item)}</li>`).join('');
    const warning = command.warning
      ? `<div class="callout">${_overlayIcons.warn}<span>${_overlayEscape(command.warning)}</span></div>`
      : '';
    _card('checklist', command.label, 'Surgical phase checklist', `<ul class="checks">${items}</ul>${warning}`);
  }

  function _renderLog() {
    const rows = logEntries.map((entry) => {
      const type = eventNames[entry.type] || String(entry.type || 'Note').replace(/_/g, ' ');
      return `<li class="${entry.type === 'complication' ? 'bad' : ''}">
        <time>${_overlayEscape(String(entry.timestamp || '--:--').slice(0, 5))}</time>
        <div class="ev"><b>${_overlayEscape(type)}</b>${entry.note ? `<span>${_overlayEscape(entry.note)}</span>` : ''}</div>
      </li>`;
    }).join('');
    _card('log', 'Operative log', '', rows
      ? `<ol class="timeline">${rows}</ol>`
      : '<p class="note">No clinical events logged.</p>');
  }

  function showLog(entries) {
    logEntries = [...(entries || [])];
    _renderLog();
  }

  function appendLog(entry) {
    logEntries.push(entry);
    _renderLog();
  }

  function remove(kind) {
    cards.get(kind)?.remove();
    cards.delete(kind);
    _syncOpen();
  }

  function clear() {
    inner.replaceChildren();
    cards.clear();
    _syncOpen();
  }

  return { init, showPatient, showVolumes, showChecklist, showLog, appendLog, remove, clear };
})();

const Banner = (() => {
  let root = null;
  let timer = null;

  function init() {
    root = document.getElementById('banner-slot');
  }

  function show(response) {
    clearTimeout(timer);
    const caution = response.safety_status === 'caution';
    const drugWords = String(response.drug || '').replace(/_/g, ' ');
    const drug = drugWords.charAt(0).toUpperCase() + drugWords.slice(1);
    root.innerHTML = `<div class="banner ${caution ? 'caution' : 'safe'}" role="alert">
      <div class="banner-head">${caution ? _overlayIcons.warn : _overlayIcons.ok}<b>${_overlayEscape(drug)}</b><span class="badge">${caution ? 'Caution' : 'Safe'}</span></div>
      <p>${_overlayEscape(response.summary || '')}</p>
      <div class="countdown"></div>
    </div>`;
    timer = setTimeout(hide, 15000);
  }

  function hide() {
    clearTimeout(timer);
    root.replaceChildren();
  }

  return { init, show, hide };
})();

const Modal = (() => {
  let root = null;

  function init() {
    root = document.getElementById('modal-slot');
    root.addEventListener('click', (event) => {
      if (event.target.classList.contains('modal-backdrop')) hide();
    });
  }

  function show(title, content, bullets) {
    const checklist = String(title).includes('Checklist');
    const rows = (bullets || []).map((bullet, index) => `<li style="animation-delay:${60 + 40 * index}ms">${_overlayEscape(bullet)}</li>`).join('');
    root.innerHTML = `<div class="modal-backdrop">
      <article class="modal" role="dialog" aria-label="${_overlayEscape(title)}">
        ${_overlayCloseButton('Close summary')}
        <h3>${_overlayEscape(title)}</h3>
        ${content ? `<p class="lead">${_overlayEscape(content)}</p>` : ''}
        <ul class="mlist ${checklist ? 'checked' : 'numbered'}">${rows}</ul>
      </article>
    </div>`;
    root.querySelector('.x').addEventListener('click', hide);
  }

  function hide() {
    root.replaceChildren();
  }

  return { init, show, hide };
})();
