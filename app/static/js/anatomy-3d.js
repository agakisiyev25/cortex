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
    renderer.outputEncoding = THREE.sRGBEncoding;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;

    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
    camera.position.set(0, 0, 3);

    controls = new THREE.OrbitControls(camera, canvas);
    controls.enableDamping = true;
    controls.enablePan = false;
    controls.addEventListener('start', () => _setViewName('Custom'));

    const hemisphere = new THREE.HemisphereLight(0xE8F4F2, 0x0A1413, 0.75);
    const key = new THREE.DirectionalLight(0xffffff, 1.1);
    key.position.set(3, 5, 4);
    const rim = new THREE.DirectionalLight(0x7FE9DA, 0.6);
    rim.position.set(-4, 2, -5);
    scene.add(hemisphere, key, rim);

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
        const centre = rawBox.getCenter(new THREE.Vector3());
        content.position.sub(centre);

        model = new THREE.Group();
        model.add(content);
        scene.add(model);

        content.traverse((child) => {
          if (!child.isMesh) return;
          const name = child.name.toLowerCase();
          if (!child.geometry.attributes.normal) child.geometry.computeVertexNormals();
          if (name === 'brain') {
            child.material = new THREE.ShaderMaterial({
              uniforms: { uColor: { value: new THREE.Color('#C9D2DA') }, uBase: { value: 0.04 }, uRim: { value: 0.6 }, uPower: { value: 2.2 } },
              vertexShader: 'varying vec3 vN; varying vec3 vV; void main() { vec4 mv = modelViewMatrix * vec4(position, 1.0); vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }',
              fragmentShader: 'uniform vec3 uColor; uniform float uBase; uniform float uRim; uniform float uPower; varying vec3 vN; varying vec3 vV; void main() { float f = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), uPower); gl_FragColor = vec4(uColor, uBase + uRim * f); }',
              transparent: true,
              depthWrite: false,
            });
            child.renderOrder = 2;
          } else {
            const color = new THREE.Color(colors[name] || '#C9D2DA').convertSRGBToLinear();
            child.material = new THREE.MeshStandardMaterial({
              color,
              roughness: 0.42,
              metalness: 0,
              emissive: color,
              emissiveIntensity: name === 'enhancing_tumor' ? 0.15 : 0.08,
            });
            child.renderOrder = 0;
          }
          if (name === 'edema') {
            child.material.transparent = true;
            child.material.opacity = 0.35;
            child.material.depthWrite = false;
            child.renderOrder = 1;
          }
          child.material.needsUpdate = true;
          console.log(child.name, Boolean(child.geometry.attributes.normal), child.material.type);
          structures[name] = child;
        });

        _applyDefaultRotation();
        controls.target.set(0, 0, 0);
        _fitCamera();
        controls.saveState();
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
    if (model) _fitCamera();
  }

  function _fitCamera() {
    if (!model || !camera || !controls) return;
    const box = new THREE.Box3().setFromObject(model);
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    const direction = camera.position.clone().sub(controls.target);
    if (!direction.lengthSq()) direction.set(0, 0, 1);
    direction.normalize();
    const vf = THREE.MathUtils.degToRad(camera.fov / 2);
    const hf = Math.atan(Math.tan(vf) * camera.aspect);
    const distance = sphere.radius * 0.75 / Math.sin(Math.min(vf, hf));
    controls.target.copy(sphere.center);
    camera.position.copy(sphere.center).addScaledVector(direction, distance);
    camera.near = distance / 100;
    camera.far = distance * 10;
    camera.updateProjectionMatrix();
    controls.update();
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
    _fitCamera();
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
    _fitCamera();
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
      item.className = structures[name]?.visible === false ? 'off' : '';
      item.style.setProperty('--c', colors[name]);
      item.textContent = displayNames[name] || name.replace(/_/g, ' ');
      legend.appendChild(item);
    });
  }

  function _setViewName(name) {
    document.getElementById('ar-view-name').textContent = name === 'Default' ? 'Default view' : name;
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
