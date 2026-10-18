(() => {
  const body = document.body;
  const root = document.documentElement;
  const themeButton = document.getElementById('theme-toggle');
  const csrfToken = body.dataset.csrfToken || '';

  // Give every form control a programmatic label, even in compact table forms.
  const fieldNames = {
    creditos: 'Créditos', id_tg: 'ID de Telegram', username: 'Nombre de usuario',
    rol_tg: 'Rol', plan: 'Plan', estado: 'Estado', antispam: 'Antispam',
    comando: 'Comando', slug: 'Identificador del comando', categoria: 'Categoría',
    categoria_id: 'Categoría', precio: 'Precio', dias: 'Días', vendedor: 'Vendedor',
    key: 'Key', codigo: 'Código', motivo: 'Motivo', respuesta: 'Respuesta',
    mensaje: 'Mensaje', texto: 'Texto', descripcion: 'Descripción', nombre: 'Nombre',
    email: 'Correo electrónico', password: 'Contraseña', password_confirm: 'Repite la contraseña',
    gq: 'Buscar en el panel', q: 'Buscar', uid: 'ID de usuario', limit: 'Límite',
    audit_actor: 'Filtrar por actor', audit_target: 'Filtrar por objetivo',
    backup: 'Archivo de respaldo', file: 'Archivo', section: 'Sección', action: 'Acción'
  };
  let generatedId = 0;
  document.querySelectorAll('input, select, textarea').forEach((control) => {
    const type = (control.getAttribute('type') || '').toLowerCase();
    if (['hidden', 'submit', 'button', 'reset', 'image'].includes(type) || control.labels?.length) return;
    if (control.hasAttribute('aria-label') || control.hasAttribute('aria-labelledby')) return;

    const placeholder = control.getAttribute('placeholder')?.trim();
    const name = control.getAttribute('name') || '';
    const humanized = name.replace(/[_-]+/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase());
    const labelText = placeholder || fieldNames[name] || humanized || 'Campo';
    if (!control.id) control.id = `panel-field-${++generatedId}`;
    const label = document.createElement('label');
    label.className = 'sr-only';
    label.htmlFor = control.id;
    label.textContent = labelText;
    control.before(label);
  });

  document.querySelectorAll('table').forEach((table, index) => {
    const heading = table.closest('.card, .mini-card, .preview-card')?.querySelector('h2, h3, strong');
    if (!table.hasAttribute('aria-label') && !table.hasAttribute('aria-labelledby')) {
      table.setAttribute('aria-label', heading?.textContent.trim() || `Tabla ${index + 1} del panel`);
    }
    table.querySelectorAll('thead th:not([scope])').forEach((cell) => cell.setAttribute('scope', 'col'));
  });

  document.querySelectorAll('form[method="post"], form[method="POST"]').forEach((form) => {
    if (form.querySelector('input[name="csrf_token"]')) return;
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'csrf_token';
    input.value = csrfToken;
    form.appendChild(input);
  });

  const syncThemeButton = () => {
    const isDark = body.classList.contains('dark') || root.classList.contains('dark');
    body.classList.toggle('dark', isDark);
    root.classList.toggle('dark', isDark);
    if (!themeButton) return;
    themeButton.setAttribute('aria-pressed', String(isDark));
    themeButton.textContent = isDark ? '☀️ Tema claro' : '🌙 Tema oscuro';
  };

  try {
    const storedTheme = localStorage.getItem('nexora-panel-theme') || localStorage.getItem('spidersyn-panel-theme');
    if (storedTheme === 'dark') body.classList.add('dark');
  } catch (_) {
    // The panel remains usable when browser storage is disabled.
  }
  syncThemeButton();

  themeButton?.addEventListener('click', () => {
    const useDark = !body.classList.contains('dark');
    body.classList.toggle('dark', useDark);
    root.classList.toggle('dark', useDark);
    syncThemeButton();
    try {
      localStorage.setItem('nexora-panel-theme', body.classList.contains('dark') ? 'dark' : 'light');
    } catch (_) {
      // Theme changes still apply for the current page.
    }
  });
})();
