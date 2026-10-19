/**
 * ct-viewer.js — MRI scan slice overlay renderer
 * ================================================
 * Renders MRI PNG slices onto a canvas element. Maintains current
 * slice state internally.
 *
 * Public API (called by app.js dispatchRenderCommand):
 *   CTViewer.init(config)
 *   CTViewer.navigate(direction, count)
 *   CTViewer.jumpToLandmark(landmark)
 *   CTViewer.hide()
 */

'use strict';

const CTViewer = (() => {

  // ── State ────────────────────────────────────────────────────────────────
  let canvas      = null;
  let ctx         = null;
  let modal       = null;   // parent .overlay-modal wrapper
  let slicesBase  = '';
  let totalSlices = 0;
  let pad         = 3;
  let landmarks   = {};
  let currentSlice = 1;


  // ── Initialisation ───────────────────────────────────────────────────────

  /**
   * @param {Object} config
   * @param {string} config.canvasId       - DOM id of the MRI canvas element
   * @param {string} config.slicesBase     - URL containing numbered PNG slices
   * @param {number} config.totalSlices    - total number of PNG slices
   * @param {number} config.pad            - slice filename zero-padding
   * @param {Object} config.landmarks      - landmark to slice mapping
   * @param {number} config.startSlice     - initial slice number
   */
  function init(config) {
    canvas      = document.getElementById(config.canvasId);
    ctx         = canvas.getContext('2d');
    modal       = canvas.closest('.tile-panel');
    slicesBase  = config.slicesBase;
    totalSlices = config.totalSlices;
    pad         = config.pad;
    landmarks   = config.landmarks;
    currentSlice = config.startSlice;

    // Size canvas to match its modal body (modal is in layout even when opacity:0)
    _resizeCanvas();
    window.addEventListener('resize', _resizeCanvas);
  }

  function _resizeCanvas() {
    if (!canvas) return;
    canvas.width  = canvas.offsetWidth  || canvas.parentElement.offsetWidth;
    canvas.height = canvas.offsetHeight || canvas.parentElement.offsetHeight;
  }


  // ── Public API ────────────────────────────────────────────────────────────

  /**
   * Moves the current slice by `count` steps in `direction`.
   * @param {'up'|'down'} direction
   * @param {number} count
   */
  function navigate(direction, count) {
    count = parseInt(count, 10) || 1;
    if (direction === 'up') {
      currentSlice = Math.min(totalSlices, currentSlice + count);
    } else {
      currentSlice = Math.max(1, currentSlice - count);
    }
    _loadAndDraw(currentSlice);
  }

  /**
   * Jumps to the slice number corresponding to a named landmark.
   * @param {string} landmark - must match a configured landmark key
   */
  function jumpToLandmark(landmark) {
    const key = landmark.toLowerCase().replace(/ /g, '_');
    const slice = landmarks[key];
    if (!slice) {
      console.warn('CTViewer: unknown landmark', landmark);
      return;
    }
    currentSlice = slice;
    _loadAndDraw(currentSlice, landmark);
  }

  /**
   * Hides the MRI modal.
   */
  function hide() {
    if (modal) { modal.classList.remove('visible'); window.ORION_relayoutModals?.(); }
  }


  // ── Rendering ─────────────────────────────────────────────────────────────

  /**
   * Constructs the URL for a slice, loads it as an Image,
   * and draws it onto the canvas with semi-transparency.
   */
  function _loadAndDraw(sliceNum, landmarkLabel) {
    if (!canvas || !ctx) return;

    const url = `${slicesBase}/${String(sliceNum).padStart(pad, '0')}.png`;

    const img = new Image();

    img.onload = () => {
      // Show tile FIRST — tiles-column expands instantly (no CSS transition),
      // so canvas gets real dimensions after the browser's next layout pass.
      if (modal) { modal.classList.add('visible'); window.ORION_relayoutModals?.(); }

      // Defer resize+draw to the next animation frame so the browser has
      // recalculated layout and canvas.offsetWidth/Height are non-zero.
      requestAnimationFrame(() => {
        _resizeCanvas();
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.globalAlpha = 0.9;
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        ctx.globalAlpha = 1.0;
        _drawLabel(sliceNum, landmarkLabel);
      });
    };

    img.onerror = () => {
      console.error('CTViewer: failed to load slice', url);
      // Draw error state on canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = 'rgba(0,0,0,0.7)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#ef9a9a';
      ctx.font = '14px monospace';
      ctx.fillText(`MRI slice ${sliceNum} not found`, 20, 40);
    };

    img.src = url;
  }

  /**
   * Draws slice number and optional landmark label onto the canvas.
   */
  function _drawLabel(sliceNum, landmarkLabel) {
    const pad = 14;

    ctx.font = "600 11px 'Poppins', sans-serif";
    ctx.textBaseline = 'top';

    // Slice counter — top-right
    const sliceText = `MRI ${sliceNum} / ${totalSlices}`;
    const sliceW = ctx.measureText(sliceText).width;
    ctx.fillStyle = 'rgba(255,255,255,0.55)';
    ctx.fillRect(canvas.width - sliceW - pad * 2 - 4, pad - 4, sliceW + 8, 20);
    ctx.fillStyle = '#1a4e80';
    ctx.fillText(sliceText, canvas.width - sliceW - pad - 4, pad);

    // Landmark label — below slice counter
    if (landmarkLabel) {
      const label = landmarkLabel.toUpperCase().replace(/_/g, ' ');
      const labelW = ctx.measureText(label).width;
      ctx.fillStyle = 'rgba(255,255,255,0.55)';
      ctx.fillRect(canvas.width - labelW - pad * 2 - 4, pad + 24, labelW + 8, 20);
      ctx.fillStyle = '#2a6090';
      ctx.fillText(label, canvas.width - labelW - pad - 4, pad + 24);
    }
  }


  // ── Public interface ──────────────────────────────────────────────────────
  return { init, navigate, jumpToLandmark, hide };

})();
