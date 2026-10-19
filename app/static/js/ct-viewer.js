/** MRI axial slice viewer for the CorteX console. */

'use strict';

const CTViewer = (() => {
  let canvas;
  let context;
  let body;
  let viewers;
  let slicesBase = '';
  let totalSlices = 0;
  let filenamePad = 3;
  let landmarks = {};
  let currentSlice = 1;
  let currentImage = null;
  let currentLandmark = '';

  function init(config) {
    canvas = document.getElementById(config.canvasId);
    context = canvas.getContext('2d');
    body = document.getElementById('mri-body');
    viewers = document.getElementById('viewers');
    slicesBase = config.slicesBase;
    totalSlices = config.totalSlices;
    filenamePad = config.pad;
    landmarks = config.landmarks;
    currentSlice = config.startSlice;

    document.getElementById('mri-title').textContent = `MRI · ${config.modality} · Axial`;
    _buildLegend(config.structures, config.displayNames, config.colors);
    body.addEventListener('wheel', _onWheel, { passive: false });
    window.addEventListener('resize', _resizeAndDraw);
    jumpToLandmark('tumor');
  }

  function _buildLegend(structures, displayNames, colors) {
    const legend = document.getElementById('mri-legend');
    legend.replaceChildren();
    structures.filter((name) => name !== 'brain').forEach((name) => {
      const item = document.createElement('span');
      item.className = 'legend-item';
      const swatch = document.createElement('span');
      swatch.className = 'legend-swatch';
      swatch.style.background = colors[name];
      const label = document.createElement('span');
      label.textContent = displayNames[name];
      item.append(swatch, label);
      legend.appendChild(item);
    });
  }

  function _onWheel(event) {
    event.preventDefault();
    navigate(event.deltaY < 0 ? 'up' : 'down', 1);
  }

  function navigate(direction, count = 1) {
    const amount = parseInt(count, 10) || 1;
    currentSlice = direction === 'up'
      ? Math.min(totalSlices, currentSlice + amount)
      : Math.max(1, currentSlice - amount);
    currentLandmark = '';
    _show();
    _load(currentSlice);
  }

  function jumpToLandmark(landmark) {
    const key = String(landmark).toLowerCase().replace(/ /g, '_');
    if (!landmarks[key]) {
      console.warn('CTViewer: unknown landmark', landmark);
      return;
    }
    currentSlice = landmarks[key];
    currentLandmark = key;
    _show();
    _load(currentSlice);
  }

  function hide() {
    viewers.classList.add('mri-hidden');
    window.dispatchEvent(new Event('resize'));
  }

  function _show() {
    viewers.classList.remove('mri-hidden');
    requestAnimationFrame(_resizeAndDraw);
  }

  function _load(sliceNumber) {
    const image = new Image();
    const filename = String(sliceNumber).padStart(filenamePad, '0');
    image.onload = () => {
      currentImage = image;
      requestAnimationFrame(_resizeAndDraw);
    };
    image.onerror = () => console.error('CTViewer: failed to load slice', image.src);
    image.src = `${slicesBase}/${filename}.png`;
    _updateMeta();
  }

  function _resizeAndDraw() {
    if (!canvas || !body) return;
    const width = Math.max(1, body.clientWidth);
    const height = Math.max(1, body.clientHeight);
    const dpr = window.devicePixelRatio || 1;
    const pixelWidth = Math.round(width * dpr);
    const pixelHeight = Math.round(height * dpr);
    if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
      canvas.width = pixelWidth;
      canvas.height = pixelHeight;
    }
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    context.clearRect(0, 0, width, height);
    if (currentImage) {
      const scale = Math.min(width / currentImage.naturalWidth, height / currentImage.naturalHeight);
      const drawWidth = currentImage.naturalWidth * scale;
      const drawHeight = currentImage.naturalHeight * scale;
      context.drawImage(
        currentImage,
        (width - drawWidth) / 2,
        (height - drawHeight) / 2,
        drawWidth,
        drawHeight,
      );
    }
    _updateTrack();
  }

  function _updateMeta() {
    document.getElementById('mri-slice-meta').textContent = `Slice ${currentSlice} / ${totalSlices}`;
    const landmark = document.getElementById('mri-landmark');
    if (currentLandmark) {
      landmark.textContent = currentLandmark.replace(/_/g, ' ');
      landmark.hidden = false;
    } else {
      landmark.hidden = true;
      landmark.textContent = '';
    }
    _updateTrack();
  }

  function _updateTrack() {
    const track = document.querySelector('.slice-track');
    const marker = document.getElementById('slice-marker');
    if (!track || !marker) return;
    const usable = Math.max(0, track.clientHeight - marker.offsetHeight);
    const fraction = totalSlices > 1 ? (currentSlice - 1) / (totalSlices - 1) : 0;
    marker.style.top = `${usable * fraction}px`;
  }

  return { init, navigate, jumpToLandmark, hide };
})();
