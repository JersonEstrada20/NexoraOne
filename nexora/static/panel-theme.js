try {
  const theme = localStorage.getItem('nexora-panel-theme') || localStorage.getItem('spidersyn-panel-theme');
  if (theme === 'dark') document.documentElement.classList.add('dark');
} catch (_) {
  // Keep the default theme when browser storage is unavailable.
}
