(() => {
  const main = document.querySelector('.automation-main');
  const config = document.createElement('div');
  config.className = 'automation-config';
  config.innerHTML = `<label for="automation-plan">Plano de gravação</label>
    <select id="automation-plan"><option value="daily">Plano diário — louça, ervas e jardim</option><option value="interleaved">Plano intercalado — tarefas aleatórias</option><option value="single">Uma tarefa escolhida abaixo</option></select>
    <div class="automation-rule"><strong>Plano diário: até 6h por celular</strong><p>1. Lavar Louça na Pia — 2h — Lavando louça .MOV<br>2. Arrancar ervas daninhas à mão / com garfo de mão — 2h — Arrancando ervas .mov<br>3. Manutenção completa do jardim — 2h — Arrancando ervas .mov</p><p>Completa o saldo de hoje de todos os celulares antes da próxima categoria. Troca a fonte após salvar, mantém dois por rodada e respeita o limite separado por tarefa. À meia-noite o saldo diário reseta. Pode restar menos de 90 segundos para respeitar a duração mínima de gravação do Minute.</p></div>
    <label for="automation-mode">Como entrar na tarefa</label>
    <select id="automation-mode"><option value="auto">Procurar a tarefa e confirmar as dicas</option><option value="ready">Usar as câmeras já abertas</option></select>
    <label for="automation-task">Nome completo da tarefa no Minute</label>
    <input id="automation-task" placeholder="Ex.: Lavar Louça na Pia" maxlength="160">
    <label for="automation-scope">Celulares participantes</label>
    <select id="automation-scope"><option value="all">Todos os cadastrados — rodadas em sequência</option><option value="online">Somente os ligados</option></select>
    <label for="automation-simultaneous">Celulares simultâneos</label>
    <select id="automation-simultaneous"><option value="2">Manter 2 celulares por rodada</option><option value="auto">Automático conforme a RAM</option></select>
    <p class="automation-steps">No modo 2, a gravação só começa quando o par estiver pronto. A RAM livre é informativa: o modo 2 tenta abrir o par mesmo abaixo da estimativa. Quando restar apenas um celular com saldo diário, ele termina sozinho.</p>
    <label for="automation-repeat">Repetição</label>
    <select id="automation-repeat"><option value="once">Executar uma rodada</option><option value="repeat">Loop contínuo — repetir até eu parar</option></select>
    <p class="automation-steps">O botão abre o Minute, procura o nome completo e confirma as dicas. Prioriza os celulares que menos gravaram. No loop com dois simultâneos, completa o par com outro celular que ainda tenha saldo. Pula contas sem saldo diário. No modo automático, ajusta a quantidade pela RAM. No modo 2, prepara o par; após salvar, a rodada anterior é desligada para liberar memória. Não é necessário abrir todos manualmente.</p><p class="automation-steps">No loop, todos salvam antes da próxima rodada. O vídeo vinculado à próxima tarefa recomeça do zero. O supervisor tenta recuperar falhas com intervalos de 30 a 120 segundos. Ao concluir os limites, o plano diário aguarda o próximo dia. Falhas de gravação ou salvamento preservam o vídeo; a fila retoma após a recuperação e a confirmação do salvamento.</p>
    <div class="automation-rule"><strong>Encerrar e salvar automaticamente</strong><p>Ao terminar o vídeo instalado ou atingir o limite de 29min59s, o que acontecer primeiro. O tempo de preparação já gravado pelo Minute entra nesse limite.</p></div>
    <p id="automation-video"></p><p class="automation-steps">1. Girar à esquerda → 2. Abrir a tarefa → 3. Vídeo do zero e gravação → 4. Encerrar e salvar</p>`;
  main.prepend(config);
  const ram = document.createElement('div');
  ram.className = 'automation-rule';
  ram.innerHTML = '<strong>Capacidade do PC agora</strong><p id="automation-ram-live" aria-live="polite">Medindo a memória disponível...</p><small>Estimativa do modo automático. Reserva 2,5 GiB para o Windows e considera 3 GiB por novo celular. Feche programas para liberar RAM; o consumo pode variar.</small>';
  config.prepend(ram);
  const supervisorBox=document.createElement('div');
  supervisorBox.className='automation-rule';
  supervisorBox.innerHTML='<strong>Recuperação automática</strong><p>Ativada ao iniciar. Confere o crescimento do vídeo, tenta salvar capturas pendentes e retoma após falhas. Se o painel fechar ou não responder, um processo local tenta reabri-lo com o plano salvo. Os botões de parar desativam a retomada automática.</p><p id="supervisor-status">Pronto para acompanhar a próxima execução.</p>';
  config.append(supervisorBox);
  const result = document.createElement('article');
  result.className = 'panel automation-results';
  result.innerHTML = '<h2>Andamento por celular</h2><p id="automation-loop-status"></p><p id="automation-queue-status"></p><button class="button button-secondary" id="loop-stop-after" disabled>Parar após salvar esta rodada</button><p id="automation-message">Escolha a tarefa e confira o vídeo antes de iniciar.</p><div id="automation-rows"></div>';
  document.querySelector('#view-automation .automation-layout').after(result);
  const style = document.createElement('style');
  style.textContent = `.automation-config{display:grid;gap:10px;margin-bottom:24px}.automation-config label{font-weight:600;font-size:13px}.automation-config input,.automation-config select{width:100%;padding:12px;border:1px solid var(--border,#334155);border-radius:10px;background:var(--bg,#101827);color:var(--text,#eee)}.automation-rule{padding:14px;background:#112f32;border-radius:12px;margin-top:8px}.automation-rule p,.automation-steps,#automation-video{font-size:13px;line-height:1.6;margin:6px 0}.automation-results{margin-top:20px;padding:22px}.automation-device{padding:15px 0;border-bottom:1px solid var(--border,#334155)}.automation-device header{display:flex;justify-content:space-between;gap:12px}.automation-device small{display:block;margin:8px 0;color:var(--muted,#9ca3af)}.automation-device.error{color:var(--red,#ff7373)}.automation-device .progress{margin-top:10px}.automation-actions button:disabled{opacity:.45;cursor:not-allowed}`;
  document.head.append(style);
  const task = document.getElementById('automation-task');
  const plan = document.getElementById('automation-plan');
  const rememberedPlan=localStorage.getItem('automation-plan');
  if(['daily','single','interleaved'].includes(rememberedPlan))plan.value=rememberedPlan;
  const dailyDescription=[...config.querySelectorAll('.automation-rule')].find(el=>el.textContent.startsWith('Plano diário:'));
  const interleavedBox = document.createElement('div');
  interleavedBox.className='automation-rule'; interleavedBox.hidden=true;
  interleavedBox.innerHTML=`<strong>Plano intercalado</strong><p>Selecione tarefas do Minute e vincule um vídeo a cada uma. A cada rodada de até 29min59s, o par salva e troca de tarefa. A ordem é sorteada, passando por todas as tarefas selecionadas antes de repetir. Limite: 2h por tarefa, por celular, por dia.</p><label for="catalog-phone">Celular para ler o catálogo</label><select id="catalog-phone"></select><button type="button" class="button button-secondary" id="catalog-refresh">Atualizar tarefas do Minute</button><p id="catalog-status"></p><label for="catalog-search">Buscar no catálogo</label><input id="catalog-search" placeholder="Filtrar tarefas"><div id="catalog-choices"></div><p id="catalog-selection-count"></p>`;
  plan.after(interleavedBox);
  let links={};try{links=JSON.parse(localStorage.getItem('interleaved-task-videos')||'{}')}catch{}
  let catalogHash='';
  function drawCatalog(state){
    const catalog=state.minuteCatalog||{tasks:[]};
    const online=state.phones||[], phoneSelect=document.getElementById('catalog-phone');
    const phoneHash=JSON.stringify(online.map(p=>[p.serial,p.name]));
    if(phoneSelect.dataset.hash!==phoneHash){const old=phoneSelect.value;phoneSelect.innerHTML=online.map(p=>`<option value="${esc(p.serial)}">${esc(p.name)}</option>`).join('');if(online.some(p=>p.serial===old))phoneSelect.value=old;phoneSelect.dataset.hash=phoneHash;}
    const hash=JSON.stringify([catalog,state.videos?.map(v=>v.name)]);
    if(hash!==catalogHash){catalogHash=hash;document.getElementById('catalog-choices').innerHTML=(catalog.tasks||[]).map((task,i)=>`<div class="catalog-row" data-task="${esc(task)}"><label><input class="catalog-check" type="checkbox" ${Object.hasOwn(links,task)?'checked':''}>${esc(task)}</label><select aria-label="Vídeo para ${esc(task)}" class="catalog-video"><option value="">Selecione um vídeo</option>${(state.videos||[]).map(v=>`<option value="${esc(v.name)}" ${links[task]===v.name?'selected':''}>${esc(v.name)}</option>`).join('')}</select></div>`).join('');}
    document.getElementById('catalog-status').textContent=catalog.tasks?.length?`${catalog.tasks.length} tarefas • atualizado em ${catalog.updatedAt} • catálogo do celular ${catalog.serial}.`:'Clique em Atualizar tarefas do Minute para carregar a lista. O celular será aberto, sem iniciar gravação.';
    if(state.operation==='minute_catalog')document.getElementById('catalog-status').textContent=panelMessage(state.message);
    interleavedBox.querySelectorAll('button,select,input').forEach(el=>el.disabled=!!state.busy);
    document.getElementById('catalog-selection-count').textContent=`${Object.keys(links).length} tarefa(s) selecionada(s)`;
  }
  interleavedBox.addEventListener('change',event=>{const row=event.target.closest('.catalog-row');if(!row)return;const name=row.dataset.task;if(row.querySelector('.catalog-check').checked)links[name]=row.querySelector('.catalog-video').value;else delete links[name];localStorage.setItem('interleaved-task-videos',JSON.stringify(links));document.getElementById('catalog-selection-count').textContent=`${Object.keys(links).length} tarefa(s) selecionada(s)`;});
  document.getElementById('catalog-search').oninput=event=>{const query=event.target.value.toLocaleLowerCase('pt-BR');interleavedBox.querySelectorAll('.catalog-row').forEach(row=>row.hidden=!row.dataset.task.toLocaleLowerCase('pt-BR').includes(query));};
  document.getElementById('catalog-refresh').onclick=()=>act('minute_catalog',{serial:document.getElementById('catalog-phone').value});
  const catalogStyle=document.createElement('style');catalogStyle.textContent='.automation-rule[hidden],.catalog-row[hidden]{display:none!important}.catalog-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(160px,1fr);gap:12px;padding:12px 0;border-bottom:1px solid #334155}.catalog-row label{display:flex;align-items:center;gap:9px}.automation-config .catalog-check{width:18px;flex-shrink:0}#catalog-choices{max-height:440px;overflow:auto;margin-top:12px}@media(max-width:600px){.catalog-row{grid-template-columns:1fr}}';document.head.append(catalogStyle);
  task.value = localStorage.getItem('automation-task') || '';
  task.onchange = () => localStorage.setItem('automation-task', task.value.trim());
  const mode = document.getElementById('automation-mode');
  const repeat = document.getElementById('automation-repeat');
  const simultaneous = document.getElementById('automation-simultaneous');
  simultaneous.value = localStorage.getItem('automation-simultaneous') || '2';
  simultaneous.onchange = () => { localStorage.setItem('automation-simultaneous', simultaneous.value); updateStart(); };
  let supportsLoop = false;
  let pending = false, connected = false, latestState = null, notice = '';
  const start = document.getElementById('sync');
  const feedback = document.createElement('p');
  feedback.id = 'automation-start-feedback';
  feedback.setAttribute('role', 'status');
  feedback.setAttribute('aria-live', 'polite');
  document.querySelector('.automation-actions').after(feedback);
  const updateStart = () => {
    if(latestState&&!latestState.supervisorVersion){start.disabled=true;start.textContent='Abra a versão atualizada do painel';return;}
    start.disabled = pending || !connected || !latestState || latestState.busy || !latestState.automationVersion || !latestState.sharedCameraVersion || (simultaneous.value === '2' && !(latestState.queueVersion >= 2)) || (plan.value === 'daily' && !latestState.dailyPlanVersion) || (plan.value === 'interleaved' && !latestState.interleavedPlanVersion);
    start.textContent = pending ? 'Enviando início...' : latestState?.busy && latestState.operation === 'sync' ? 'Automação em andamento' : 'Iniciar e salvar em todos';
  };
  feedback.textContent = 'Conectando ao painel...';
  plan.onchange = () => { localStorage.setItem('automation-plan',plan.value); if (latestState) render(latestState); updateStart(); };
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
    if (plan.value === 'single' && autoNavigate && !task.value.trim()) { task.focus(); return feedback.textContent = notice = 'Informe o nome completo da tarefa no Minute'; }
    const interleavedTasks=Object.entries(links).map(([task,video])=>({task,video}));
    if(plan.value==='interleaved'&&(!interleavedTasks.length||interleavedTasks.some(row=>!row.video)))return feedback.textContent=notice='Selecione pelo menos uma tarefa e um vídeo para cada tarefa.';
    notice = '';
    pending = true; updateStart();
    feedback.textContent = 'Enviando comando para iniciar a tarefa...';
    try {
      await call('sync', {interleavedPlan:plan.value==='interleaved',interleavedTasks,dailyPlan: plan.value === 'daily', autoNavigate, taskName: task.value.trim(), scope: document.getElementById('automation-scope').value, manageRam: autoNavigate && document.getElementById('automation-scope').value === 'all', repeat: repeat.value === 'repeat', simultaneous: simultaneous.value === '2' ? 2 : null, randomizePhones: false, usageSince: null});
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
    document.getElementById('supervisor-status').textContent=state.supervisorStage?`${state.supervisorStage}${state.supervisorAttempts?' • '+state.supervisorAttempts+' tentativa(s) de recuperação':''}`:'Ativa ao iniciar • vídeos sem confirmação são preservados, sem descarte automático.';
    const capacity = state.capacity;
    document.getElementById('automation-ram-live').textContent = !capacity ? 'Abra o painel atualizado para ver a RAM.' : capacity.error || `RAM livre: ${(capacity.freeBytes/1073741824).toFixed(1)} GiB de ${(capacity.totalBytes/1073741824).toFixed(1)} GiB • Pode iniciar mais ${capacity.additional} celular(es) • Total estimado: ${capacity.estimatedTotal} simultâneos${capacity.lowMemory ? ' • Pouca memória: o modo 2 continua tentando abrir o par.' : ''}`;
    const active = state.busy && state.operation === 'sync';
    const daily = plan.value !== 'single';
    if(dailyDescription)dailyDescription.hidden=plan.value!=='daily';
    task.hidden=plan.value!=='single';
    document.querySelector('label[for="automation-task"]').hidden=plan.value!=='single';
    interleavedBox.hidden=plan.value!=='interleaved';drawCatalog(state);
    plan.disabled = active;
    if (daily) { mode.value = 'auto'; repeat.value = 'repeat'; simultaneous.value = '2'; document.getElementById('automation-scope').value = 'all'; }
    supportsLoop = state.automationVersion >= 4;
    repeat.disabled = active || daily || !supportsLoop;
    simultaneous.disabled = active || daily || mode.value === 'ready' || document.getElementById('automation-scope').value !== 'all';
    mode.disabled = active || daily; task.disabled = active || daily || mode.value === 'ready';
    document.getElementById('automation-scope').disabled = active || daily;
    const phoneLabel = name => (state.phones || []).find(p => p.avd === name)?.name || name;
    document.getElementById('automation-queue-status').textContent = state.queueBatch ? `Rodada ${state.queueBatch} • ${state.queueSaved?.length || 0} salvo(s) • Aguardando: ${(state.queuePending || []).map(phoneLabel).join(', ') || 'ninguém'}${state.queueFreeGiB != null ? ' • RAM livre ao iniciar: ' + state.queueFreeGiB.toFixed(1) + ' GiB' : ''}${state.queueSkipped?.length ? ' • Sem saldo diário: ' + state.queueSkipped.map(phoneLabel).join(', ') : ''}` : '';
    document.getElementById('loop-stop-after').disabled = !active || !(state.planActive || state.loopActive || state.queueActive) || state.loopStopping;
    document.getElementById('automation-loop-status').textContent = !supportsLoop ? 'Reinicie o painel para ativar o loop contínuo.' : state.loopActive ? `Loop: rodada ${state.loopCycle || 1} • ${state.loopCompleted || 0} rodada(s) salva(s)${state.loopStopping ? ' • Parando após esta rodada' : ''}` : state.loopCompleted ? `${state.loopCompleted} rodada(s) salva(s) na última execução.` : '';
    latestState = state; connected = true; updateStart();
    feedback.textContent = pending ? 'Enviando comando para iniciar a tarefa...' : state.busy ? (panelMessage(state.message) || 'Operação em andamento. Aguarde.') : notice || (!state.automationVersion || !state.sharedCameraVersion ? 'Reabra o painel atualizado para iniciar.' : state.operation === 'sync' ? panelMessage(state.message) : 'Pronto para iniciar. Confira a tarefa e o vídeo.');
    if (!state.busy && simultaneous.value === '2' && !(state.queueVersion >= 2)) feedback.textContent = 'Reabra o painel na versão 2.3.21 para iniciar com dois celulares. Esta execução ainda usa a fila antiga.';
    if (!state.busy && daily && !state.dailyPlanVersion) feedback.textContent = 'Reabra o painel na versão 2.3.22 para usar o plano diário com os vídeos corretos.';
    if (state.planActive) document.getElementById('automation-loop-status').textContent = `${state.planMode==='interleaved'?'Plano intercalado • rodada':'Plano diário • etapa'} ${state.planStep}${state.planMode==='interleaved'?'':'/3'} • ${state.planTask || 'Preparando'} • Vídeo: ${state.planVideo || 'Conferindo fontes'}`;
    document.getElementById('cancel').disabled = !active;
    document.querySelector('#view-automation .ready-badge').textContent = active ? 'EM ANDAMENTO' : 'AGUARDANDO INÍCIO';
    document.getElementById('automation-video').textContent = state.allVideoName ? `Vídeo em todos: ${state.allVideoName}` : 'Vídeo diferente ou não confirmado em algum celular. Confira a aba Vídeos.';
    document.getElementById('automation-message').textContent = state.automationVersion ? (state.operation === 'sync' ? panelMessage(state.message) : 'Gravações menores que 1 minuto não podem ser salvas pelo Minute.') : 'Reinicie o painel para carregar a nova automação.';
    const rows = Object.entries(state.automation || {});
    document.getElementById('automation-rows').innerHTML = rows.map(([serial, row]) => {
      const phone = (state.phones || []).find(p => p.serial === serial);
      return `<div class="automation-device ${row.error ? 'error' : ''}"><header><strong>${esc(phone?.name || row.name)}</strong><span>${esc(row.stage)}</span></header><small>${esc(row.video || '')} ${row.task ? ' • ' + esc(row.task) : ''}</small><span>${duration(row.elapsed)} / ${duration(row.total)} • ${row.percent || 0}%</span>${row.error ? `<p>${esc(panelMessage(row.error))}</p>` : ''}<div class="progress"><span style="width:${row.percent || 0}%"></span></div></div>`;
    }).join('') || '<p>O resultado de cada celular aparecerá aqui.</p>';
    if (state.operation !== 'sync') {
      document.getElementById('syncbar').style.width = '0%';
      document.getElementById('timer-percent').textContent = '0%';
    }
  };
})();
