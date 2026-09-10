(() => {
  const main = document.querySelector('.automation-main');
  const config = document.createElement('div');
  config.className = 'automation-config';
  config.innerHTML = `<label for="automation-mode">Como entrar na tarefa</label>
    <select id="automation-mode"><option value="auto">Procurar a tarefa e confirmar as dicas</option><option value="ready">Usar as câmeras já abertas</option></select>
    <label for="automation-task">Nome completo da tarefa no Minute</label>
    <input id="automation-task" placeholder="Ex.: Lavar Louça na Pia" maxlength="160">
    <label for="automation-scope">Celulares participantes</label>
    <select id="automation-scope"><option value="all">Todos os cadastrados — rodadas conforme a RAM</option><option value="online">Somente os ligados</option></select>
    <label for="automation-repeat">Repetição</label>
    <select id="automation-repeat"><option value="once">Executar uma rodada</option><option value="repeat">Loop contínuo — repetir até eu parar</option></select>
    <p class="automation-steps">O botão abre o Minute, procura o nome completo e confirma as dicas. Prioriza quem gravou menos nesta tarefa hoje; no empate, quem tem menos tempo acumulado. Pula contas sem saldo diário. Liga os celulares aos poucos, reservando RAM para o Windows. Os que não couberem aguardam; após salvar, a rodada anterior é desligada para liberar memória. Não é necessário abrir todos manualmente.</p><p class="automation-steps">No loop, todos salvam antes da próxima rodada. O mesmo vídeo recomeça do zero na mesma tarefa. Erros ou o limite diário interrompem a repetição.</p>
    <div class="automation-rule"><strong>Encerrar e salvar automaticamente</strong><p>Ao terminar o vídeo instalado ou atingir o limite de 29min59s, o que acontecer primeiro. O tempo de preparação já gravado pelo Minute entra nesse limite.</p></div>
    <p id="automation-video"></p><p class="automation-steps">1. Girar à esquerda → 2. Abrir a tarefa → 3. Vídeo do zero e gravação → 4. Encerrar e salvar</p>`;
  main.prepend(config);
  const ram = document.createElement('div');
  ram.className = 'automation-rule';
  ram.innerHTML = '<strong>Capacidade do PC agora</strong><p id="automation-ram-live" aria-live="polite">Medindo a memória disponível...</p><small>Estimativa atualizada automaticamente. Reserva 2,5 GiB para o Windows e considera 3 GiB por novo celular. Feche programas para liberar RAM; o consumo pode variar.</small>';
  config.prepend(ram);
  const result = document.createElement('article');
  result.className = 'panel automation-results';
  result.innerHTML = '<h2>Andamento por celular</h2><p id="automation-loop-status"></p><p id="automation-queue-status"></p><button class="button button-secondary" id="loop-stop-after" disabled>Parar após salvar esta rodada</button><p id="automation-message">Escolha a tarefa e confira o vídeo antes de iniciar.</p><div id="automation-rows"></div>';
  document.querySelector('#view-automation .automation-layout').after(result);
  const style = document.createElement('style');
  style.textContent = `.automation-config{display:grid;gap:10px;margin-bottom:24px}.automation-config label{font-weight:600;font-size:13px}.automation-config input,.automation-config select{width:100%;padding:12px;border:1px solid var(--border,#334155);border-radius:10px;background:var(--bg,#101827);color:var(--text,#eee)}.automation-rule{padding:14px;background:#112f32;border-radius:12px;margin-top:8px}.automation-rule p,.automation-steps,#automation-video{font-size:13px;line-height:1.6;margin:6px 0}.automation-results{margin-top:20px;padding:22px}.automation-device{padding:15px 0;border-bottom:1px solid var(--border,#334155)}.automation-device header{display:flex;justify-content:space-between;gap:12px}.automation-device small{display:block;margin:8px 0;color:var(--muted,#9ca3af)}.automation-device.error{color:var(--red,#ff7373)}.automation-device .progress{margin-top:10px}.automation-actions button:disabled{opacity:.45;cursor:not-allowed}`;
  document.head.append(style);
  const task = document.getElementById('automation-task');
  task.value = localStorage.getItem('automation-task') || '';
  task.onchange = () => localStorage.setItem('automation-task', task.value.trim());
  const mode = document.getElementById('automation-mode');
  const repeat = document.getElementById('automation-repeat');
  let supportsLoop = false;
  let pending = false, connected = false, latestState = null, notice = '';
  const start = document.getElementById('sync');
  const feedback = document.createElement('p');
  feedback.id = 'automation-start-feedback';
  feedback.setAttribute('role', 'status');
  feedback.setAttribute('aria-live', 'polite');
  document.querySelector('.automation-actions').after(feedback);
  const updateStart = () => {
    start.disabled = pending || !connected || !latestState || latestState.busy || !latestState.automationVersion || !latestState.sharedCameraVersion;
    start.textContent = pending ? 'Enviando início...' : latestState?.busy && latestState.operation === 'sync' ? 'Automação em andamento' : 'Iniciar e salvar em todos';
  };
  feedback.textContent = 'Conectando ao painel...';
  updateStart();
  window.addEventListener('panel-connection', event => {
    connected = event.detail.connected;
    if (!connected) feedback.textContent = event.detail.message;
    updateStart();
  });
  mode.onchange = e => { task.disabled = e.target.value === 'ready'; if (task.disabled) repeat.value = 'once'; };
  repeat.onchange = () => { if (repeat.value === 'repeat') { mode.value = 'auto'; task.disabled = false; } };
  document.getElementById('loop-stop-after').onclick = () => act('loop_stop_after_round');
  start.onclick = async () => {
    if (start.disabled) return;
    const autoNavigate = document.getElementById('automation-mode').value === 'auto';
    if (repeat.value === 'repeat' && !supportsLoop) return feedback.textContent = notice = 'Reinicie o painel para ativar o loop contínuo';
    if (autoNavigate && !task.value.trim()) { task.focus(); return feedback.textContent = notice = 'Informe o nome completo da tarefa no Minute'; }
    notice = '';
    pending = true; updateStart();
    feedback.textContent = 'Enviando comando para iniciar a tarefa...';
    try {
      await call('sync', {autoNavigate, taskName: task.value.trim(), scope: document.getElementById('automation-scope').value, manageRam: autoNavigate && document.getElementById('automation-scope').value === 'all', repeat: repeat.value === 'repeat'});
      feedback.textContent = 'Comando recebido. Preparando os celulares...';
      await refresh();
    } catch (error) {
      feedback.textContent = notice = error.message;
    } finally { pending = false; updateStart(); }
  };
  document.getElementById('cancel').textContent = 'Encerrar agora e salvar';
  const originalRender = render;
  render = state => {
    originalRender(state);
    const capacity = state.capacity;
    document.getElementById('automation-ram-live').textContent = !capacity ? 'Abra o painel atualizado para ver a RAM.' : capacity.error || `RAM livre: ${(capacity.freeBytes/1073741824).toFixed(1)} GiB de ${(capacity.totalBytes/1073741824).toFixed(1)} GiB • Pode iniciar mais ${capacity.additional} celular(es) • Total estimado: ${capacity.estimatedTotal} simultâneos${capacity.lowMemory ? ' • Pouca memória: feche programas antes de iniciar.' : ''}`;
    const active = state.busy && state.operation === 'sync';
    supportsLoop = state.automationVersion >= 4;
    repeat.disabled = active || !supportsLoop;
    mode.disabled = active; task.disabled = active || mode.value === 'ready';
    document.getElementById('automation-scope').disabled = active;
    const phoneLabel = name => (state.phones || []).find(p => p.avd === name)?.name || name;
    document.getElementById('automation-queue-status').textContent = state.queueBatch ? `Rodada ${state.queueBatch} • ${state.queueSaved?.length || 0} salvo(s) • Aguardando: ${(state.queuePending || []).map(phoneLabel).join(', ') || 'ninguém'}${state.queueFreeGiB != null ? ' • RAM livre ao iniciar: ' + state.queueFreeGiB.toFixed(1) + ' GiB' : ''}${state.queueSkipped?.length ? ' • Sem saldo diário: ' + state.queueSkipped.map(phoneLabel).join(', ') : ''}` : '';
    document.getElementById('loop-stop-after').disabled = !active || !(state.loopActive || state.queueActive) || state.loopStopping;
    document.getElementById('automation-loop-status').textContent = !supportsLoop ? 'Reinicie o painel para ativar o loop contínuo.' : state.loopActive ? `Loop: rodada ${state.loopCycle || 1} • ${state.loopCompleted || 0} rodada(s) salva(s)${state.loopStopping ? ' • Parando após esta rodada' : ''}` : state.loopCompleted ? `${state.loopCompleted} rodada(s) salva(s) na última execução.` : '';
    latestState = state; connected = true; updateStart();
    feedback.textContent = pending ? 'Enviando comando para iniciar a tarefa...' : state.busy ? (state.message || 'Operação em andamento. Aguarde.') : notice || (!state.automationVersion || !state.sharedCameraVersion ? 'Reabra o painel atualizado para iniciar.' : state.operation === 'sync' ? state.message : 'Pronto para iniciar. Confira a tarefa e o vídeo.');
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
