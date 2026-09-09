(() => {
  const main = document.querySelector('.automation-main');
  const config = document.createElement('div');
  config.className = 'automation-config';
  config.innerHTML = `<label for="automation-mode">Como entrar na tarefa</label>
    <select id="automation-mode"><option value="auto">Procurar a tarefa e confirmar as dicas</option><option value="ready">Usar as câmeras já abertas</option></select>
    <label for="automation-task">Nome completo da tarefa no Minute</label>
    <input id="automation-task" placeholder="Ex.: Lavar Louça na Pia" maxlength="160">
    <label for="automation-scope">Celulares participantes</label>
    <select id="automation-scope"><option value="all">Todos os cadastrados (liga os desligados)</option><option value="online">Somente os ligados</option></select>
    <div class="automation-rule"><strong>Encerrar e salvar automaticamente</strong><p>Ao terminar o vídeo instalado ou atingir o limite de 29min59s, o que acontecer primeiro. O tempo de preparação já gravado pelo Minute entra nesse limite.</p></div>
    <p id="automation-video"></p><p class="automation-steps">1. Girar à esquerda → 2. Abrir a tarefa → 3. Vídeo do zero e gravação → 4. Encerrar e salvar</p>`;
  main.prepend(config);
  const result = document.createElement('article');
  result.className = 'panel automation-results';
  result.innerHTML = '<h2>Andamento por celular</h2><p id="automation-message">Escolha a tarefa e confira o vídeo antes de iniciar.</p><div id="automation-rows"></div>';
  document.querySelector('#view-automation .automation-layout').after(result);
  const style = document.createElement('style');
  style.textContent = `.automation-config{display:grid;gap:10px;margin-bottom:24px}.automation-config label{font-weight:600;font-size:13px}.automation-config input,.automation-config select{width:100%;padding:12px;border:1px solid var(--border,#334155);border-radius:10px;background:var(--bg,#101827);color:var(--text,#eee)}.automation-rule{padding:14px;background:#112f32;border-radius:12px;margin-top:8px}.automation-rule p,.automation-steps,#automation-video{font-size:13px;line-height:1.6;margin:6px 0}.automation-results{margin-top:20px;padding:22px}.automation-device{padding:15px 0;border-bottom:1px solid var(--border,#334155)}.automation-device header{display:flex;justify-content:space-between;gap:12px}.automation-device small{display:block;margin:8px 0;color:var(--muted,#9ca3af)}.automation-device.error{color:var(--red,#ff7373)}.automation-device .progress{margin-top:10px}.automation-actions button:disabled{opacity:.45;cursor:not-allowed}`;
  document.head.append(style);
  const task = document.getElementById('automation-task');
  task.value = localStorage.getItem('automation-task') || '';
  task.onchange = () => localStorage.setItem('automation-task', task.value.trim());
  document.getElementById('automation-mode').onchange = e => { task.disabled = e.target.value === 'ready'; };
  document.getElementById('sync').onclick = () => {
    const autoNavigate = document.getElementById('automation-mode').value === 'auto';
    if (autoNavigate && !task.value.trim()) return toast('Informe o nome completo da tarefa no Minute');
    act('sync', {autoNavigate, taskName: task.value.trim(), scope: document.getElementById('automation-scope').value});
  };
  document.getElementById('cancel').textContent = 'Encerrar agora e salvar';
  const originalRender = render;
  render = state => {
    originalRender(state);
    const active = state.busy && state.operation === 'sync';
    document.getElementById('sync').disabled = state.busy || !state.automationVersion || !state.sharedCameraVersion;
    document.getElementById('cancel').disabled = !active;
    document.querySelector('#view-automation .ready-badge').textContent = active ? 'EM ANDAMENTO' : 'AGUARDANDO INÍCIO';
    document.getElementById('automation-video').textContent = state.allVideoName ? `Vídeo em todos: ${state.allVideoName}` : 'Vídeo diferente ou não confirmado em algum celular. Confira a aba Vídeos.';
    document.getElementById('automation-message').textContent = state.automationVersion ? (state.operation === 'sync' ? state.message : 'Gravações menores que 1 minuto não podem ser salvas pelo Minute.') : 'Reinicie o painel para carregar a nova automação.';
    const rows = Object.entries(state.automation || {});
    document.getElementById('automation-rows').innerHTML = rows.map(([serial, row]) => {
      const phone = (state.phones || []).find(p => p.serial === serial);
      return `<div class="automation-device ${row.error ? 'error' : ''}"><header><strong>${esc(phone?.name || row.name)}</strong><span>${esc(row.stage)}</span></header><small>${esc(row.video || '')} ${row.task ? ' • ' + esc(row.task) : ''}</small><span>${duration(row.elapsed)} / ${duration(row.total)} • ${row.percent || 0}%</span>${row.error ? `<p>${esc(row.error)}</p>` : ''}<div class="progress"><span style="width:${row.percent || 0}%"></span></div></div>`;
    }).join('') || '<p>O resultado de cada celular aparecerá aqui.</p>';
    if (state.operation !== 'sync') {
      document.getElementById('syncbar').style.width = '0%';
      document.getElementById('timer-percent').textContent = '0%';
    }
  };
})();
