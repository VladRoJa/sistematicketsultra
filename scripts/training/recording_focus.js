/* Inyección exclusivamente para grabaciones Playwright CAP-V1; nunca en Angular. */
(() => {
  if (window.__capV1FocusRecorder) return;
  const interactions = [];
  let previewCounter = 0;
  const previewMoments = [];
  const W = window;
  let spotlight, targetBox, pointer, pulse, cue, dismissTimer, watchTimer, selectedElement;
  const now = () => Math.round(performance.now());
  const point = (element, x, y) => {
    element.style.left = Math.round(x) + 'px';
    element.style.top = Math.round(y) + 'px';
  };
  const dismiss = () => {
    spotlight?.classList.remove('cap-v1-visible');
    targetBox?.classList.remove('cap-v1-visible');
    cue?.classList.remove('cap-v1-visible');
    clearInterval(watchTimer);
    selectedElement = null;
  };
  const watchSelection = () => {
    if (!selectedElement || !selectedElement.isConnected) {
      targetBox?.classList.remove('cap-v1-visible');
      return;
    }
    const rect = selectedElement.getBoundingClientRect();
    if (!rect.width || !rect.height) {
      // El botón puede desaparecer al abrir/cerrar un diálogo: no dibujar un
      // contorno fantasma en la posición anterior.
      targetBox?.classList.remove('cap-v1-visible');
    }
  };
  const init = () => {
    if (document.getElementById('cap-v1-recording-overlay')) return;
    const root = document.createElement('div');
    root.id = 'cap-v1-recording-overlay';
    root.setAttribute('aria-hidden', 'true');
    root.innerHTML = [
      '<div class="cap-v1-spotlight"></div>',
      '<div class="cap-v1-target"></div>',
      '<div class="cap-v1-pulse"></div>',
      '<div class="cap-v1-cursor"></div>',
      '<div class="cap-v1-cue">HAZ CLIC AQUÍ</div>',
    ].join('');
    document.body.appendChild(root);
    spotlight = root.querySelector('.cap-v1-spotlight');
    targetBox = root.querySelector('.cap-v1-target');
    pulse = root.querySelector('.cap-v1-pulse');
    pointer = root.querySelector('.cap-v1-cursor');
    cue = root.querySelector('.cap-v1-cue');

    document.addEventListener('pointermove', (event) => {
      if (event.isTrusted && pointer) {
        point(pointer, event.clientX, event.clientY);
      }
    }, true);

    document.addEventListener('pointerdown', (event) => {
      if (!event.isTrusted || event.button !== 0) return;
      cue.classList.remove('cap-v1-visible');
      const x = event.clientX;
      const y = event.clientY;
      const clickable = event.target instanceof Element
        ? event.target.closest(
          'button, a, input, select, textarea, [role="button"], [role="checkbox"], ' +
          '[role="option"], [role="tab"], mat-option, mat-checkbox, .mat-mdc-row'
        ) || event.target
        : null;
      // No registrar etiquetas, texto, IDs de usuario ni datos de formulario.
      interactions.push({x: Math.round(x), y: Math.round(y), ms: now()});
      if (interactions.length > 500) interactions.shift();
      point(pointer, x, y);
      point(pulse, x, y);
      pulse.classList.remove('cap-v1-animate');
      void pulse.offsetWidth;
      pulse.classList.add('cap-v1-animate');
      spotlight.style.setProperty('--focus-x', Math.round(x) + 'px');
      spotlight.style.setProperty('--focus-y', Math.round(y) + 'px');
      spotlight.classList.add('cap-v1-visible');
      selectedElement = clickable;
      clearInterval(watchTimer);
      watchTimer = setInterval(watchSelection, 80);
      const rect = clickable?.getBoundingClientRect();
      if (rect && rect.width > 0 && rect.height > 0 &&
          rect.width < innerWidth * .8 && rect.height < innerHeight * .8) {
        const pad = 5;
        targetBox.style.left = Math.max(0, rect.left - pad) + 'px';
        targetBox.style.top = Math.max(0, rect.top - pad) + 'px';
        targetBox.style.width = Math.min(innerWidth - rect.left + pad, rect.width + pad * 2) + 'px';
        targetBox.style.height = Math.min(innerHeight - rect.top + pad, rect.height + pad * 2) + 'px';
        targetBox.classList.add('cap-v1-visible');
      } else {
        targetBox.classList.remove('cap-v1-visible');
      }
      clearTimeout(dismissTimer);
      dismissTimer = setTimeout(dismiss, 1450);
    }, true);
  };
  // Se llama desde la capa Playwright *antes* del clic. Nunca hace clic,
  // dispara eventos de negocio ni extrae texto/datos del objetivo.
  const preview = (rect) => {
    if (!spotlight || !targetBox || !cue ||
        !rect || ![rect.x, rect.y, rect.width, rect.height].every(Number.isFinite) ||
        rect.width <= 0 || rect.height <= 0) return false;
    clearTimeout(dismissTimer);
    clearInterval(watchTimer);
    selectedElement = null;
    const x = Math.round(rect.x + rect.width / 2);
    const y = Math.round(rect.y + rect.height / 2);
    spotlight.style.setProperty('--focus-x', x + 'px');
    spotlight.style.setProperty('--focus-y', y + 'px');
    spotlight.classList.add('cap-v1-visible');
    const pad = 6;
    targetBox.style.left = Math.max(0, rect.x - pad) + 'px';
    targetBox.style.top = Math.max(0, rect.y - pad) + 'px';
    targetBox.style.width = Math.min(innerWidth - Math.max(0, rect.x - pad),
      rect.width + 2 * pad) + 'px';
    targetBox.style.height = Math.min(innerHeight - Math.max(0, rect.y - pad),
      rect.height + 2 * pad) + 'px';
    targetBox.classList.add('cap-v1-visible');
    // Situar la flecha arriba, o abajo si el control está cerca del borde.
    const below = rect.y < 90;
    const cueWidth = 154;
    const cueX = Math.min(innerWidth - cueWidth - 8,
      Math.max(8, x - cueWidth / 2));
    cue.style.left = cueX + 'px';
    cue.style.top = Math.round(below ?
      Math.min(innerHeight - 56, rect.y + rect.height + 20) :
      Math.max(8, rect.y - 66)) + 'px';
    cue.classList.toggle('cap-v1-cue-below', below);
    cue.classList.add('cap-v1-visible');
    previewCounter += 1;
    previewMoments.push(now());
    if (previewMoments.length > 500) previewMoments.shift();
    return true;
  };
  window.__capV1FocusRecorder = {
    events: () => interactions.map(e => ({...e})),
    ready: () => !!document.getElementById('cap-v1-recording-overlay'),
    preview,
    cueVisible: () => !!cue?.classList.contains('cap-v1-visible'),
    previewCount: () => previewCounter,
    previewMoments: () => previewMoments.slice(),
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, {once: true});
  } else {
    init();
  }
})();
