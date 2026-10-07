/* UI guard only: this does not replace server-side transaction idempotency. */
(() => {
  const dirtyForms = new Set();
  const pendingForms = new Set();
  const notice = document.getElementById('panel-save-status');
  const announce = (text) => { if (notice) notice.textContent = text; };
  const forms = [...document.querySelectorAll('form')].filter(
    form => form.method.toLowerCase() === 'post');

  forms.forEach(form => {
    form.addEventListener('input', () => {
      dirtyForms.add(form);
      announce('Cambios sin enviar. La actualización automática está pausada.');
    });
    form.addEventListener('change', () => dirtyForms.add(form));
    form.addEventListener('submit', event => {
      if (event.defaultPrevented) return;
      if (pendingForms.has(form)) {
        event.preventDefault();
        return;
      }
      const confirmation = event.submitter?.dataset.confirm || form.dataset.confirm;
      if (confirmation && !window.confirm(confirmation)) {
        event.preventDefault();
        return;
      }
      pendingForms.add(form);
      dirtyForms.delete(form);
      form.setAttribute('aria-busy', 'true');
      // Do not disable the submitter: its name/value selects the server action.
      form.querySelectorAll('button[type="submit"], button:not([type]), input[type="submit"]')
        .forEach(button => button.setAttribute('aria-disabled', 'true'));
      announce('Enviando… No repitas la acción mientras se confirma el resultado.');
    });
  });

  window.addEventListener('beforeunload', event => {
    if (dirtyForms.size && !pendingForms.size) {
      event.preventDefault();
      event.returnValue = '';
    }
  });
  window.addEventListener('pageshow', () => {
    pendingForms.clear();
    forms.forEach(form => {
      form.removeAttribute('aria-busy');
      form.querySelectorAll('[aria-disabled="true"]')
        .forEach(button => button.removeAttribute('aria-disabled'));
    });
    announce('Comprueba el resultado antes de repetir una operación.');
  });

  if (document.body.dataset.section === 'solicitudes') {
    window.setInterval(() => {
      const editing = document.activeElement?.matches('input, textarea, select, [contenteditable="true"]');
      if (dirtyForms.size || pendingForms.size || editing || document.hidden) return;
      window.location.reload();
    }, 15000);
  }
})();
