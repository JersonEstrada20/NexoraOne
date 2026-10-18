(() => {
  const body = document.body;
  const root = document.documentElement;
  const themeButton = document.getElementById('theme-toggle');
  const csrfToken = body.dataset.csrfToken || '';

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
