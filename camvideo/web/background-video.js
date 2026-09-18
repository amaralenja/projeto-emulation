const backgroundCard = document.createElement('article');
backgroundCard.className = 'panel';
backgroundCard.style.cssText = 'padding:24px;margin-bottom:24px';
backgroundCard.innerHTML = `<div class="panel-heading"><div><span class="eyebrow">SEGUNDO PLANO</span><h2>Deixar o próximo vídeo pronto</h2></div></div>
<p>Importe e prepare no PC enquanto os celulares continuam com o vídeo atual. Depois, use “Usar no selecionado” ou “Usar em todos” para trocar a fonte.</p>
<div class="install-actions"><label class="button button-secondary">Importar e preparar<input id="background-upload" type="file" accept="video/*" hidden></label>
<button class="button button-secondary" id="background-prepare">Preparar vídeo selecionado</button></div>
<p id="background-selection"></p><p id="background-status" role="status" aria-live="polite">Aguardando</p>
<strong id="background-percent" style="display:block;font-size:24px;margin:8px 0">0%</strong><progress id="background-progress" max="100" value="0" style="width:100%"></progress>
<div id="background-queue"></div><small>A preparação usa prioridade reduzida. A velocidade depende dos recursos livres do PC.</small>`;
document.querySelector('.video-layout').before(backgroundCard);
let backgroundUpload = null;
const renderBeforeBackground = render;
render = function(state) {
  renderBeforeBackground(state);
  const job = state.backgroundVideo || {};
  const unavailable = !state.backgroundVideoVersion;
  $('background-prepare').disabled = unavailable || !!job.busy || !!backgroundUpload || !app.video;
  $('background-upload').disabled = unavailable || !!job.busy || !!backgroundUpload;
  $('background-selection').textContent = app.video ? `Selecionado: ${app.video}` : 'Selecione um vídeo da biblioteca.';
  $('background-status').textContent = unavailable ? 'Atualização do servidor pendente; as gravações atuais continuam.' : backgroundUpload ? `Importando ${backgroundUpload.name}: ${backgroundUpload.percent}%` : `${job.name ? job.name + ' — ' : ''}${job.stage || 'Aguardando'}${job.error ? ': ' + job.error : ''}`;
  $('background-queue').innerHTML = [...(job.queued || []).map((name,index) => `<p>${index+1}º na fila: ${esc(name)} — aguardando preparação</p>`), ...(job.results || []).slice(-10).map(item => `<p>${esc(item.name)} — ${item.error ? esc(item.error) : '100% • Pronto para todos os celulares'}</p>`)].join('');
  const percent = Math.max(0, Math.min(100, Number(backgroundUpload ? backgroundUpload.percent : job.progress) || 0));
  $('background-progress').value = percent;
  $('background-percent').textContent = `${Math.floor(percent)}%${backgroundUpload ? ' importado' : job.busy ? ' • ' + (job.stage || 'Preparando') : ''}`;
  $('background-progress').setAttribute('aria-label', 'Progresso da preparação');
};
$('background-prepare').onclick = async () => {
  try {
    await call('prepare_background', {video: app.video, fill: $('fill').checked});
    await refresh();
  } catch (error) { toast(error.message); }
};
$('background-upload').onchange = async event => {
  const file = event.target.files[0];
  if (!file) return;
  const fill = $('fill').checked;
  backgroundUpload = {name: file.name, percent: 0};
  render(app.state);
  try {
    const result = await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/upload');
      xhr.setRequestHeader('X-Filename', encodeURIComponent(file.name));
      xhr.setRequestHeader('X-Background', '1');
      xhr.setRequestHeader('X-Fill', fill ? '1' : '0');
      xhr.upload.onprogress = e => {
        backgroundUpload.percent = e.lengthComputable ? Math.min(99, Math.floor(e.loaded * 100 / e.total)) : 0;
        render(app.state);
      };
      xhr.onload = () => {
        try {
          const body = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300) resolve(body);
          else reject(Error(body.error || 'Falha ao importar'));
        } catch (error) { reject(error); }
      };
      xhr.onerror = () => reject(Error('Importação interrompida'));
      xhr.onabort = () => reject(Error('Importação cancelada'));
      xhr.send(file);
    });
    // Preserve the selected preview as well as the running camera source.
    if (!result.preparationQueued) await call('prepare_background', {video: result.name, fill});
    toast('Vídeo importado; preparação em segundo plano iniciada');
  } catch (error) { toast(error.message); }
  finally { backgroundUpload = null; event.target.value = ''; await refresh(); }
};
