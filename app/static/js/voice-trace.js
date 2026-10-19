/** Monitor-style voice trace for the CorteX rail. */

'use strict';

const VoiceTrace = (() => {
  const VOICE = {
    offline: { color: '#788C89', alpha: 1 },
    connecting: { color: '#FFB648', alpha: 1 },
    idle: { color: '#3FD8C2', alpha: 0.55 },
    talking: { color: '#3FD8C2', alpha: 1 },
    thinking: { color: '#3FD8C2', alpha: 0.8 },
    speaking: { color: '#3FD8C2', alpha: 1 },
  };
  let state = 'offline';
  let targetLevel = 0;
  let level = 0;

  function pulse(t, period, width) {
    const phase = (t % period) / period;
    return Math.exp(-((phase - 0.5) ** 2) / (2 * width * width));
  }

  function signal(t, voiceState, micLevel) {
    const noise = Math.sin(t * 71) * 0.5 + Math.sin(t * 113) * 0.5;
    switch (voiceState) {
      case 'offline': return 0;
      case 'connecting': return 0.28 * pulse(t, 1, 0.03);
      case 'idle': {
        const phase = (t % 2.4) / 2.4;
        return phase > 0.46 && phase < 0.54
          ? 0.42 * Math.sin((phase - 0.46) / 0.08 * Math.PI * 2)
          : 0.015 * noise;
      }
      case 'talking': return micLevel * Math.sin(t * 2 * Math.PI * 11 + 2 * noise) * (0.55 + 0.45 * Math.sin(t * 2 * Math.PI * 1.3));
      case 'thinking': return 0.14 * Math.sin(t * 2 * Math.PI * 0.9);
      case 'speaking': {
        const envelope = Math.pow(Math.max(0, Math.sin(t * 2 * Math.PI * 2.6)), 0.6)
          * (0.7 + 0.3 * Math.sin(t * 2 * Math.PI * 0.7));
        return 0.62 * envelope * Math.sin(t * 2 * Math.PI * 9 + 3 * Math.sin(t * 2 * Math.PI * 2));
      }
      default: return 0;
    }
  }

  const canvas = document.getElementById('trace');
  const context = canvas.getContext('2d');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let x = 0;
  let previousY = null;
  let last = performance.now();
  let width = 0;
  let height = 0;

  function fit() {
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    width = rect.width;
    height = rect.height;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    x = 0;
    previousY = null;
  }

  function frame(now) {
    const delta = Math.min(0.05, (now - last) / 1000);
    last = now;
    level += (targetLevel - level) * 0.3;
    const config = VOICE[state];
    context.lineWidth = 2;
    context.lineCap = 'round';
    context.lineJoin = 'round';
    context.strokeStyle = config.color;
    context.globalAlpha = config.alpha;
    context.shadowColor = config.color;
    context.shadowBlur = state === 'talking' || state === 'speaking' ? 8 : 0;

    if (reduce) {
      context.clearRect(0, 0, width, height);
      context.beginPath();
      for (let index = 0; index <= width; index += 2) {
        const y = height / 2 - signal(index / 140, state, level) * height * 0.38;
        if (index) context.lineTo(index, y);
        else context.moveTo(index, y);
      }
      context.stroke();
      return;
    }

    const steps = Math.max(1, Math.round(140 * delta));
    for (let index = 0; index < steps; index += 1) {
      x += 1;
      if (x > width) {
        x = 0;
        previousY = null;
      }
      context.clearRect(x, 0, 22, height);
      const time = now / 1000 - (steps - index) / 140;
      const y = height / 2 - signal(time, state, level) * height * 0.38;
      if (previousY !== null) {
        context.beginPath();
        context.moveTo(x - 1, previousY);
        context.lineTo(x, y);
        context.stroke();
      }
      previousY = y;
    }
    requestAnimationFrame(frame);
  }

  new ResizeObserver(fit).observe(canvas);
  fit();
  requestAnimationFrame(frame);

  function setState(nextState) {
    if (VOICE[nextState]) state = nextState;
    if (state !== 'talking') targetLevel = 0;
  }

  function setLevel(nextLevel) {
    targetLevel = Math.max(0, Math.min(1, Number(nextLevel) || 0));
  }

  return { setState, setLevel };
})();

window.VoiceTrace = VoiceTrace;
