/** CorteX viewer overlays: drawer cards, drug banner, and summary modal. */

'use strict';

const _overlayEscape = (value) => String(value ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

const Drawer = (() => {
  let root = null;
  let caseData = null;
  let logEntries = [];
  const cards = new Map();
  const normalNotes = new Set([
    'Normal',
    'Normal renal function',
    'Adequate for surgery',
    'Normal coagulation',
    '',
  ]);
  const eventNames = {
    timeout_complete: 'Time-out complete',
    incision: 'Incision',
    tumor_resected: 'Tumor resected',
    specimen_sent: 'Specimen sent',
    complication: 'Complication',
    milestone: 'Milestone',
    note: 'Note',
  };
  const widePatientFields = new Set([
    'diagnosis',
    'procedure',
    'allergies',
    'medications',
  ]);

  function init(kase) {
    root = document.getElementById('drawer');
    caseData = kase;
  }

  function _card(kind, title, accent, bodyHtml) {
    const card = document.createElement('section');
    card.className = 'drawer-card';
    card.dataset.kind = kind;
    card.style.setProperty('--card-accent', accent);
    card.innerHTML = `
      <header class="drawer-card-header">
        <div class="drawer-card-title">${_overlayEscape(title)}</div>
        <button class="overlay-close" type="button" aria-label="Close ${_overlayEscape(title)}">×</button>
      </header>
      <div class="drawer-card-body">${bodyHtml}</div>`;
    card.querySelector('.overlay-close').addEventListener('click', () => remove(kind));

    const existing = cards.get(kind);
    if (existing) {
      existing.replaceWith(card);
    } else {
      root.prepend(card);
    }
    cards.set(kind, card);

    while (root.children.length > 3) {
      const oldest = root.lastElementChild;
      cards.delete(oldest.dataset.kind);
      oldest.remove();
    }
  }

  function showPatient(fields, single = false) {
    const rows = (fields || []).map((field) => {
      const note = field.note || '';
      const noteClass = normalNotes.has(note) ? '' : ' attention';
      const showNote = note && (single || !normalNotes.has(note));
      return `
        <div class="patient-row ${single ? 'single' : ''} ${field.field === 'allergies' ? 'allergies' : ''} ${widePatientFields.has(field.field) ? 'wide' : ''}">
          <div class="patient-label">${_overlayEscape(field.label)}</div>
          <div class="patient-value">${_overlayEscape(field.value)}</div>
          ${showNote ? `<div class="patient-note${noteClass}">${_overlayEscape(note)}</div>` : ''}
        </div>`;
    }).join('');
    _card(
      'patient',
      'Patient data',
      'var(--accent)',
      single ? rows : `<div class="patient-grid">${rows}</div>`,
    );
  }

  function showVolumes(volumes, sourceNote) {
    const order = ['enhancing_tumor', 'non_enhancing_core', 'edema', 'resection_cavity'];
    const tumorRegions = new Set(['enhancing_tumor', 'non_enhancing_core', 'edema']);
    let total = 0;
    const rows = order.filter((name) => volumes?.[name] !== undefined).map((name) => {
      if (tumorRegions.has(name)) total += Number(volumes[name]);
      const color = caseData.colors[name];
      return `
        <div class="volume-row">
          <span class="legend-swatch" style="background:${_overlayEscape(color)}"></span>
          <span>${_overlayEscape(caseData.display_names[name])}</span>
          <span class="volume-value">${Number(volumes[name]).toFixed(1)} cm³</span>
        </div>`;
    }).join('');
    const body = `${rows}
      <div class="volume-total"><span></span><span>Total tumor regions</span><span class="volume-value">${total.toFixed(1)} cm³</span></div>
      <div class="source-note">${_overlayEscape(sourceNote)}</div>`;
    _card('volumes', 'Tumor volumes', 'var(--accent)', body);
  }

  function showChecklist(command) {
    const items = (command.checklist || []).map((item) => `
      <div class="checklist-item"><span class="empty-checkbox"></span><span>${_overlayEscape(item)}</span></div>`).join('');
    const warning = command.warning
      ? `<div class="warning-callout">${_overlayEscape(command.warning)}</div>`
      : '';
    _card(
      'checklist',
      'Procedure checklist',
      'var(--amber)',
      `<div class="checklist-name">${_overlayEscape(command.label)}</div>${items}${warning}`,
    );
  }

  function _renderLog() {
    const rows = logEntries.map((entry) => {
      const type = eventNames[entry.type] || String(entry.type || 'Note').replace(/_/g, ' ');
      return `
        <div class="log-row ${entry.type === 'complication' ? 'complication' : ''}">
          <time class="log-time">${_overlayEscape(entry.timestamp || '--:--:--')}</time>
          <div><div class="log-type">${_overlayEscape(type)}</div>${entry.note ? `<div class="log-note">${_overlayEscape(entry.note)}</div>` : ''}</div>
        </div>`;
    }).join('') || '<div class="source-note">No clinical events logged.</div>';
    _card('log', 'Operative log', 'var(--ok)', rows);
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
  }

  function clear() {
    root.replaceChildren();
    cards.clear();
  }

  return { init, showPatient, showVolumes, showChecklist, showLog, appendLog, remove, clear };
})();


const Banner = (() => {
  let root = null;
  let timer = null;

  function init() {
    root = document.getElementById('banner');
  }

  function show(response) {
    clearTimeout(timer);
    const caution = response.safety_status === 'caution';
    const drug = String(response.drug || '').replace(/_/g, ' ').toUpperCase();
    root.innerHTML = `
      <div class="drug-banner ${caution ? 'caution' : 'safe'}">
        <div class="drug-banner-title">${caution ? '⚠' : '✓'} ${_overlayEscape(drug)} — ${caution ? 'CAUTION' : 'SAFE'}</div>
        <div class="drug-banner-body">${_overlayEscape(response.summary || '')}</div>
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
    root = document.getElementById('summary-modal');
    root.addEventListener('click', (event) => {
      if (event.target === root) hide();
    });
  }

  function show(title, content, bullets) {
    const checklist = String(title).includes('Checklist');
    const rows = (bullets || []).map((bullet, index) => `
      <div class="summary-bullet">
        <span class="summary-marker">${checklist ? '✓' : index + 1}</span>
        <span>${_overlayEscape(bullet)}</span>
      </div>`).join('');
    root.innerHTML = `
      <article class="summary-card ${checklist ? 'checklist' : ''}">
        <button class="overlay-close" type="button" aria-label="Close summary">×</button>
        <h2 class="summary-title">${_overlayEscape(title)}</h2>
        ${content ? `<p class="summary-content">${_overlayEscape(content)}</p>` : ''}
        <div class="summary-list">${rows}</div>
      </article>`;
    root.querySelector('.overlay-close').addEventListener('click', hide);
    root.classList.add('open');
  }

  function hide() {
    root.classList.remove('open');
    root.replaceChildren();
  }

  return { init, show, hide };
})();
