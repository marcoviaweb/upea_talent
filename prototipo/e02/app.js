(() => {
  const roleSelect = document.querySelector('#role-select');
  const main = document.querySelector('#main-content');
  const toast = document.querySelector('#toast-region');
  const roleStatus = document.querySelector('#role-preview-status');
  const roleViews = {
    estudiante: { title: 'Inicio', id: 'inicio' },
    docente: { title: 'Inicio docente', id: 'docente' },
    coordinacion: { title: 'Panel de carrera', id: 'coordinacion' },
    administracion: { title: 'Configuración académica', id: 'administracion' }
  };
  let toastTimer;

  function announce(message) {
    toast.textContent = message;
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => { toast.textContent = ''; }, 4200);
  }

  function applyRole() {
    const role = roleSelect.value;
    document.querySelectorAll('[data-nav-for]').forEach((item) => {
      item.hidden = item.dataset.navFor !== role;
    });
    document.querySelectorAll('.nav-item:not([data-nav-for])').forEach((item) => {
      item.hidden = role !== 'estudiante';
    });
    roleStatus.textContent = `Vista de navegación de ${roleSelect.selectedOptions[0].text.toLowerCase()}; la cuenta y los datos son ficticios.`;
    showView(roleViews[role].id, false);
  }

  function showView(id, updateHistory = true) {
    const role = roleSelect.value;
    const permittedView = role === 'estudiante'
      ? ['inicio', 'trayectoria', 'evidencias', 'oportunidades', 'evaluaciones', 'apoyo', 'movimientos'].includes(id)
      : id === role;
    if (!permittedView) {
      announce('Esta pantalla no corresponde a la vista de demostración seleccionada.');
      return;
    }
    const view = document.querySelector(`#view-${id}`);
    if (!view) return;
    document.querySelectorAll('.page-view').forEach((section) => { section.hidden = section !== view; });
    document.querySelectorAll('.nav-item').forEach((link) => {
      const active = link.getAttribute('href') === `#${id}`;
      link.classList.toggle('is-active', active);
      if (active) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
    if (updateHistory) history.pushState({ id }, '', `#${id}`);
    view.querySelector('h1')?.setAttribute('tabindex', '-1');
    view.querySelector('h1')?.focus({ preventScroll: true });
    main.scrollIntoView({ block: 'start' });
  }

  roleSelect.addEventListener('change', applyRole);
  document.addEventListener('click', (event) => {
    const link = event.target.closest('a[href^="#"]');
    if (link && link.closest('.app-shell')) {
      const id = link.getAttribute('href').slice(1);
      if (document.querySelector(`#view-${id}`)) {
        event.preventDefault();
        showView(id);
      }
    }
    if (event.target.closest('.demo-action, .notice-button, .user-menu')) {
      announce('Prototipo: esta acción no está conectada; no se guardó ningún cambio.');
    }
  });
  window.addEventListener('popstate', () => showView(location.hash.slice(1) || roleViews[roleSelect.value].id, false));
  window.addEventListener('hashchange', () => showView(location.hash.slice(1) || roleViews[roleSelect.value].id, false));

  const filter = document.querySelector('#evidence-filter');
  filter?.addEventListener('change', () => {
    document.querySelectorAll('#evidence-rows tr').forEach((row) => {
      row.hidden = filter.value !== 'todas' && row.dataset.status !== filter.value;
    });
  });

  const eligibilityToggle = document.querySelector('#eligibility-toggle');
  eligibilityToggle?.addEventListener('click', () => {
    const panel = document.querySelector('#eligibility-details');
    const expanded = eligibilityToggle.getAttribute('aria-expanded') === 'true';
    eligibilityToggle.setAttribute('aria-expanded', String(!expanded));
    eligibilityToggle.textContent = expanded ? 'Ver evaluación de requisitos' : 'Ocultar evaluación de requisitos';
    panel.hidden = expanded;
  });

  document.querySelector('#evaluation-form')?.addEventListener('submit', (event) => {
    event.preventDefault();
    if (!event.currentTarget.reportValidity()) return;
    document.querySelector('#evaluation-status').textContent = 'Respuesta simulada; no se envió ni almacenó información.';
    event.currentTarget.reset();
  });

  applyRole();
  const initial = location.hash.slice(1);
  if (roleSelect.value === 'estudiante' && initial && document.querySelector(`#view-${initial}`)) showView(initial, false);
})();
