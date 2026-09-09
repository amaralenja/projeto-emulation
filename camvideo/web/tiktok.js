(() => {
  const key = 'emulation-tiktok-draft';
  let draft = {};
  try { draft = JSON.parse(localStorage.getItem(key) || '{}') || {}; } catch {}
  if (typeof draft !== 'object' || Array.isArray(draft)) draft = {};
  const title = $('tiktok-title'), phone = $('tiktok-phone'), video = $('tiktok-video');
  title.value = typeof draft.title === 'string' ? draft.title : '';
  let choicesHash = '';
  function choices(state) {
    const phones = state.phones || [], videos = state.videos || [];
    const hash = JSON.stringify([phones.map(p => [p.serial, p.name, p.status]), videos.map(v => v.name)]);
    if (hash === choicesHash) return;
    choicesHash = hash;
    phone.innerHTML = '<option value="">Selecione um celular</option>' + phones.map(p => `<option value="${esc(p.serial)}">${esc(p.name)} · ${p.status === 'online' ? 'Online' : p.status === 'booting' ? 'Iniciando' : 'Desligado'}</option>`).join('');
    video.innerHTML = '<option value="">Selecione um vídeo</option>' + videos.map(v => `<option value="${esc(v.name)}">${esc(v.name)}</option>`).join('');
    phone.value = phones.some(p => p.serial === draft.phone) ? draft.phone : '';
    video.value = videos.some(v => v.name === draft.video) ? draft.video : '';
  }
  for (const select of [phone, video]) select.addEventListener('change', () => {
    draft.phone = phone.value;
    draft.video = video.value;
  });
  $('tiktok-draft').addEventListener('submit', event => {
    event.preventDefault();
    draft = {title: title.value.trim(), phone: phone.value, video: video.value};
    try {
      localStorage.setItem(key, JSON.stringify(draft));
      toast('Rascunho da live salvo neste navegador');
    } catch { toast('Não foi possível salvar o rascunho neste navegador'); }
  });
  const previousRender = render;
  render = state => { previousRender(state); choices(state); };
  choices(app.state);
})();
