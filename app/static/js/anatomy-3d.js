/** Three.js patient-specific anatomy renderer for the CorteX console. */

'use strict';

const Anatomy3D = (() => {
  let renderer;
  let scene;
  let camera;
  let controls;
  let model;
  let canvas;
  let container;
  let viewers;
  let resizeObserver;
  let defaultView = { x: 15, y: 35 };
  let animation = null;
  let legendOrder = [];
  let displayNames = {};
  let colors = {};
  const structures = {};

  function init(config) {
    canvas = document.getElementById(config.canvasId);
    container = canvas.parentElement;
    viewers = document.getElementById('viewers');
    defaultView = config.defaultView || defaultView;
    legendOrder = config.structures || [];
    displayNames = config.displayNames || {};
    colors = config.colors || {};

    renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x000000, 0);

    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
    camera.position.set(0, 0, 3);

    controls = new THREE.OrbitControls(camera, canvas);
    controls.enableDamping = true;
    controls.enablePan = false;
    controls.addEventListener('start', () => _setViewName('Custom'));

    scene.add(new THREE.HemisphereLight(0xffffff, 0x223040, 0.9));
    const key = new THREE.DirectionalLight(0xffffff, 0.8);
    key.position.set(3, 5, 4);
    scene.add(key);
    const rim = new THREE.DirectionalLight(0x88ccff, 0.35);
    rim.position.set(-4, 2, -3);
    scene.add(rim);

    _resize();
    window.addEventListener('resize', _resize);
    resizeObserver = new ResizeObserver(_resize);
    resizeObserver.observe(container);
    _loadModel(config.modelUrl);
    _renderLoop();
  }

  function _loadModel(url) {
    new THREE.GLTFLoader().load(
      url,
      (gltf) => {
        const content = gltf.scene;
        const rawBox = new THREE.Box3().setFromObject(content);
        const rawSize = rawBox.getSize(new THREE.Vector3());
        const maxDimension = Math.max(rawSize.x, rawSize.y, rawSize.z);
        content.scale.setScalar(2 / maxDimension);

        const scaledBox = new THREE.Box3().setFromObject(content);
        const centre = scaledBox.getCenter(new THREE.Vector3());
        content.position.sub(centre);

        model = new THREE.Group();
        model.add(content);
        scene.add(model);

        const fittedBox = new THREE.Box3().setFromObject(content);
        const fittedSize = fittedBox.getSize(new THREE.Vector3());
        const fittedMax = Math.max(fittedSize.x, fittedSize.y, fittedSize.z);
        const cameraDistance = fittedMax / (2 * Math.tan(THREE.MathUtils.degToRad(22.5)));
        camera.position.set(0, 0, cameraDistance * 1.35);
        camera.near = cameraDistance * 0.01;
        camera.far = cameraDistance * 10;
        camera.lookAt(0, 0, 0);
        camera.updateProjectionMatrix();
        controls.target.set(0, 0, 0);
        controls.update();
        controls.saveState();

        content.traverse((child) => {
          if (!child.isMesh || !child.material) return;
          child.material.side = THREE.DoubleSide;
          child.material.transparent = false;
          child.material.opacity = 1;
          child.material.depthWrite = true;
          child.renderOrder = 0;
          if (child.name.toLowerCase() === 'edema') {
            child.material.transparent = true;
            child.material.opacity = 0.35;
            child.material.depthWrite = false;
            child.renderOrder = 1;
          }
          if (child.name.toLowerCase() === 'brain') {
            child.material.transparent = true;
            child.material.opacity = 0.14;
            child.material.depthWrite = false;
            child.renderOrder = 2;
          }
          child.material.needsUpdate = true;
          structures[child.name.toLowerCase()] = child;
        });

        _applyDefaultRotation();
        _renderLegend();
        _setViewName('Default');
        canvas.dataset.ready = 'true';
        requestAnimationFrame(_resize);
      },
      undefined,
      (error) => console.error('[Anatomy3D] Failed to load model:', error),
    );
  }

  function _resize() {
    if (!renderer || !container) return;
    const width = Math.max(1, container.clientWidth);
    const height = Math.max(1, container.clientHeight);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }

  function _renderLoop(now) {
    requestAnimationFrame(_renderLoop);
    if (animation && model) {
      const progress = Math.min(1, (now - animation.started) / 400);
      const eased = 1 - Math.pow(1 - progress, 3);
      model.rotation.x = THREE.MathUtils.lerp(animation.from.x, animation.to.x, eased);
      model.rotation.y = THREE.MathUtils.lerp(animation.from.y, animation.to.y, eased);
      model.rotation.z = THREE.MathUtils.lerp(animation.from.z, animation.to.z, eased);
      if (progress === 1) animation = null;
    }
    controls?.update();
    renderer?.render(scene, camera);
  }

  function rotate(axis, degrees) {
    if (!model || !['x', 'y', 'z'].includes(String(axis).toLowerCase())) return;
    _show();
    controls.reset();
    const from = model.rotation.clone();
    model.rotation.set(0, 0, 0);
    model.rotation[String(axis).toLowerCase()] = THREE.MathUtils.degToRad(Number(degrees));
    const to = model.rotation.clone();
    model.rotation.copy(from);
    animation = { from, to, started: performance.now() };
    _setViewName(viewNameFor(axis, Number(degrees)));
  }

  function toggleStructure(structureName, visible) {
    _show();
    const mesh = structures[String(structureName).toLowerCase().trim()];
    if (!mesh) {
      console.warn('[Anatomy3D] Unknown structure:', structureName);
      return;
    }
    mesh.visible = Boolean(visible);
    _renderLegend();
  }

  function reset() {
    if (!model) return;
    _show();
    controls.reset();
    animation = null;
    Object.values(structures).forEach((mesh) => { mesh.visible = true; });
    _applyDefaultRotation();
    _renderLegend();
    _setViewName('Default');
  }

  function hide() {
    viewers.classList.add('ar-hidden');
    window.dispatchEvent(new Event('resize'));
  }

  function _show() {
    viewers.classList.remove('ar-hidden');
    requestAnimationFrame(_resize);
  }

  function _applyDefaultRotation() {
    model.rotation.set(
      THREE.MathUtils.degToRad(defaultView.x || 0),
      THREE.MathUtils.degToRad(defaultView.y || 0),
      0,
    );
  }

  function _renderLegend() {
    const legend = document.getElementById('ar-legend');
    legend.replaceChildren();
    legendOrder.forEach((name) => {
      const item = document.createElement('span');
      item.className = `legend-item${structures[name]?.visible === false ? ' hidden' : ''}`;
      const swatch = document.createElement('span');
      swatch.className = 'legend-swatch';
      swatch.style.background = colors[name];
      const label = document.createElement('span');
      label.textContent = displayNames[name] || name.replace(/_/g, ' ');
      item.append(swatch, label);
      legend.appendChild(item);
    });
  }

  function _setViewName(name) {
    document.getElementById('ar-view-name').textContent = name;
  }

  function viewNameFor(axis, degrees) {
    const key = `${String(axis).toLowerCase()}:${Number(degrees)}`;
    return ({
      'y:0': 'Front',
      'y:180': 'Back',
      'y:90': 'Right side',
      'y:-90': 'Left side',
      'x:90': 'Top',
      'x:-90': 'Bottom',
    })[key] || 'Custom';
  }

  return { init, rotate, toggleStructure, reset, hide, viewNameFor };
})();
