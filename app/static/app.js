(() => {
  const menu = document.querySelector('[data-menu-toggle]');
  const sidebar = document.getElementById('sidebar');
  if (menu && sidebar) menu.addEventListener('click', () => sidebar.classList.toggle('open'));

  document.querySelectorAll('[data-dismiss]').forEach((button) => {
    button.addEventListener('click', () => button.closest('.flash')?.remove());
  });

  document.querySelectorAll('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!window.confirm(form.dataset.confirm || 'Are you sure?')) event.preventDefault();
    });
  });

  const fileInput = document.getElementById('import-file');
  const selected = document.querySelector('[data-file-name]');
  if (fileInput && selected) {
    fileInput.addEventListener('change', () => {
      selected.textContent = fileInput.files?.[0]?.name || 'কোনো ফাইল নির্বাচন করা হয়নি';
    });
  }

  const editor = document.getElementById('text');
  const counter = document.querySelector('[data-char-count]');
  if (editor && counter) {
    const update = () => { counter.textContent = `${editor.value.length.toLocaleString()} characters`; };
    editor.addEventListener('input', update);
    update();
  }
})();
