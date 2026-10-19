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
  let resizeObserver;

  function init(config) {
    canvas = document.getElementById(config.canvasId);
    context = canvas.getContext('2d');
    body = document.getElementById('mri-panel');
    viewers = document.getElementById('viewers');
    slicesBase = config.slicesBase;
    totalSlices = config.totalSlices;
    filenamePad = config.pad;
    landmarks = config.landmarks;
    currentSlice = config.startSlice;

    const modalityNames = {
      T1c: 'T1 with contrast',
      T1: 'T1',
      T2: 'T2',
      FLAIR: 'FLAIR',
    };
    document.getElementById('mri-modality').textContent = modalityNames[config.modality] || config.modality;
    _buildLegend(config.structures, config.displayNames, config.colors);
    body.addEventListener('wheel', _onWheel, { passive: false });
    window.addEventListener('resize', _resizeAndDraw);
    resizeObserver = new ResizeObserver(_resizeAndDraw);
    resizeObserver.observe(body);
    jumpToLandmark('tumor');
  }

  function _buildLegend(structures, displayNames, colors) {
    const legend = document.getElementById('mri-legend');
    legend.replaceChildren();
    structures.filter((name) => name !== 'brain').forEach((name) => {
      const item = document.createElement('span');
      item.style.setProperty('--c', colors[name]);
      item.textContent = displayNames[name];
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
    context.fillStyle = '#000';
    context.fillRect(0, 0, width, height);
    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = 'high';
    if (currentImage) {
      const left = 16;
      const top = 48;
      const availableWidth = Math.max(1, width - left - 24);
      const availableHeight = Math.max(1, height - top - 40);
      const scale = Math.min(
        availableWidth / currentImage.naturalWidth,
        availableHeight / currentImage.naturalHeight,
      );
      const drawWidth = currentImage.naturalWidth * scale;
      const drawHeight = currentImage.naturalHeight * scale;
      context.drawImage(
        currentImage,
        left + (availableWidth - drawWidth) / 2,
        top + (availableHeight - drawHeight) / 2,
        drawWidth,
        drawHeight,
      );
    }
    _updateTrack();
  }

  function _updateMeta() {
    document.getElementById('mri-slice-meta').innerHTML = `${currentSlice} <small>/ ${totalSlices}</small>`;
    const landmark = document.getElementById('mri-landmark');
    if (currentLandmark) {
      const words = currentLandmark.replace(/_/g, ' ');
      landmark.textContent = words.charAt(0).toUpperCase() + words.slice(1);
      landmark.hidden = false;
    } else {
      landmark.hidden = true;
      landmark.textContent = '';
    }
    _updateTrack();
  }

  function _updateTrack() {
    const marker = document.getElementById('slice-marker');
    if (!marker) return;
    const fraction = totalSlices > 1 ? (currentSlice - 1) / (totalSlices - 1) : 0;
    marker.style.top = `${fraction * 100}%`;
  }

  return { init, navigate, jumpToLandmark, hide };
})();
