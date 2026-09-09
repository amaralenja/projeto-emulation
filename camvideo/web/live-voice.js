(() => {
  const panel = document.createElement('article');
  panel.className = 'panel';
  panel.style.marginBottom = '20px';
  panel.innerHTML = `<div class="panel-heading"><div><span class="eyebrow">APRESENTAÇÃO DO PRODUTO</span><h2>Falas contínuas com IA</h2></div><span id="live-key-state" class="tiktok-status">Verificando chave</span></div>
    <p class="tiktok-note">A OpenAI escreve os roteiros com os dados abaixo. O OmniVoice gera a voz no PC. Cada fala tem aproximadamente um minuto; duas ficam prontas antes da reprodução começar.</p>
    <details class="voice-help"><summary>Configurar chave da OpenAI</summary><form id="live-key-form" class="tiktok-form"><label for="live-key">Chave da API</label><input id="live-key" type="password" autocomplete="off" spellcheck="false" maxlength="512" placeholder="Cole sua chave"><button class="button button-secondary">Salvar chave protegida</button><p class="tiktok-note">Armazenada com proteção do Windows. Os roteiros consomem créditos da sua API; o áudio é local.</p></form></details>
    <form id="live-product-form" class="tiktok-form" style="margin-top:16px"><label for="live-name">Nome do produto</label><input id="live-name" maxlength="120" required placeholder="Nome exato do produto">
    <label for="live-features">Características e informações confirmadas</label><textarea id="live-features" rows="5" maxlength="3000" required placeholder="Materiais, medidas, funções, modo de uso e outras informações verdadeiras"></textarea>
    <label for="live-offer">Oferta e condições (opcional)</label><textarea id="live-offer" rows="2" maxlength="600" placeholder="Preço, desconto e condições, se existirem"></textarea>
    <div class="tiktok-actions"><button class="button button-secondary">Salvar produto</button><button type="button" id="live-prepare" class="button button-secondary">Gerar amostra de 1 minuto</button></div></form>
    <div class="tiktok-form" style="margin-top:16px"><label for="live-quality">Qualidade da geração</label><select id="live-quality"><option value="32">Original — 32 etapas</option><option value="16">Rápida — 16 etapas</option></select>
    <label for="live-minutes">Duração da sessão</label><select id="live-minutes"><option value="15">15 minutos</option><option value="30">30 minutos</option><option value="60" selected>1 hora</option><option value="120">2 horas</option><option value="0">Até eu parar</option></select>
    <p class="tiktok-note">A sessão usa a saída e o volume escolhidos em “Para onde a voz vai?”. Iniciar autoriza novas chamadas à sua API até o fim da sessão. Confira os dados e ouça a amostra antes.</p>
    <div class="tiktok-actions"><button id="live-start" class="button button-primary">Iniciar falas contínuas</button><button id="live-stop" class="button cancel-button" disabled>Parar sessão</button><button id="live-unload" class="button button-secondary">Liberar memória da voz</button></div>
    <p id="live-status" class="tiktok-note" role="status"></p><p id="live-counts" class="tiktok-note"></p>
    <details class="voice-help"><summary>Último roteiro gerado</summary><p id="live-script" style="white-space:pre-wrap"></p></details></div>`;
  $('view-tiktok').querySelector('.voice-studio').prepend(panel);
  let loaded = false;
  const product = () => ({name:$('live-name').value.trim(), features:$('live-features').value.trim(), offer:$('live-offer').value.trim()});
  async function act(action, data={}) {
    const response = await fetch('/api/voice/action', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action,...data})});
    const result = await response.json();
    if (!response.ok) throw Error(result.error || 'Não foi possível concluir.');
    return result;
  }
  async function run(action, data={}) {
    try { await act(action,data); } catch(error) { toast(error.message); $('live-status').textContent=error.message; }
  }
  $('live-key-form').onsubmit = async e => {
    e.preventDefault();
    const key=$('live-key').value; $('live-key').value='';
    try { await act('save_openai_key',{key}); toast('Chave salva com proteção do Windows'); }
    catch(error) { toast(error.message); }
  };
  $('live-product-form').onsubmit = async e => { e.preventDefault(); try { await act('save_product',{product:product()}); toast('Produto salvo'); } catch(error) { toast(error.message); } };
  function start(action) {
    if (!$('live-product-form').reportValidity()) return;
    run(action,{product:product(), output:$('voice-output').value, volume:Number($('voice-volume').value)/100,
                minutes:Number($('live-minutes').value), steps:Number($('live-quality').value)});
  }
  $('live-start').onclick=()=>start('live_start'); $('live-prepare').onclick=()=>start('live_prepare');
  $('live-stop').onclick=()=>run('live_stop'); $('live-unload').onclick=()=>run('unload');
  window.addEventListener('voice-state', e => {
    const value=e.detail.live;
    if (!value) { $('live-status').textContent='Abra o painel atualizado para usar as falas contínuas.'; return; }
    if (!loaded) { loaded=true; $('live-name').value=value.product.name; $('live-features').value=value.product.features; $('live-offer').value=value.product.offer; }
    $('live-key-state').textContent=value.apiKeyConfigured ? 'Chave configurada' : 'Configure sua chave';
    $('live-start').disabled=$('live-prepare').disabled=value.active || !value.apiKeyConfigured;
    $('live-stop').disabled=!value.active;
    $('live-unload').disabled=value.active || e.detail.generation.busy || e.detail.playback.busy;
    $('live-status').textContent=value.message;
    $('live-status').classList.toggle('voice-error',!!value.error);
    $('live-counts').textContent=`${value.generated} falas geradas · ${value.queued} na fila · ${value.played} reproduzidas · ${value.requests} chamadas OpenAI · ${value.tokens} tokens`;
    $('live-script').textContent=value.script || 'Nenhum roteiro ainda.';
  });

  const uploads=document.createElement('article'); uploads.className='panel'; uploads.style.marginBottom='20px';
  uploads.innerHTML=`<div class="panel-heading"><div><span class="eyebrow">VÍDEOS DA LIVE</span><h2>Adicionar demonstrações do produto</h2></div></div><p class="tiktok-note">Envie seus vídeos para a biblioteca e selecione um no rascunho. O envio não altera a câmera nem inicia uma transmissão. Use demonstrações e ângulos diferentes; edições não garantem que o TikTok considere o conteúdo original.</p><div class="tiktok-actions"><label class="button button-secondary" for="live-video-upload">Enviar vídeos</label><input type="file" id="live-video-upload" accept="video/*" multiple hidden><button class="button button-secondary" id="live-upload-cancel" disabled>Cancelar envio</button></div><progress id="live-upload-progress" max="100" value="0" style="width:100%;margin-top:14px"></progress><p class="tiktok-note" id="live-upload-status" role="status">Nenhum envio em andamento.</p>`;
  $('view-tiktok').querySelector('#tiktok-draft').closest('article').before(uploads);
  let xhr=null, cancelled=false;
  $('live-upload-cancel').onclick=()=>{cancelled=true; xhr?.abort();};
  $('live-video-upload').onchange=async e=>{
    const files=Array.from(e.target.files); cancelled=false;
    $('live-upload-cancel').disabled=false; e.target.disabled=true;
    try {
      for(const file of files) {
        if(cancelled) break;
        const name=await new Promise((resolve,reject)=>{
          xhr=new XMLHttpRequest(); xhr.open('POST','/api/upload'); xhr.setRequestHeader('X-Filename',encodeURIComponent(file.name));
          xhr.upload.onprogress=event=>{if(event.lengthComputable) $('live-upload-progress').value=event.loaded/event.total*100;};
          xhr.onload=()=>{try {const value=JSON.parse(xhr.responseText); if(xhr.status!==200) throw Error(value.error || 'Falha no envio'); resolve(value.name);}catch(error){reject(error);}};
          xhr.onerror=()=>reject(Error('Erro de conexão durante o envio.')); xhr.onabort=()=>reject(Error('Envio cancelado.'));
          $('live-upload-status').textContent=`Enviando ${file.name}...`; xhr.send(file);
        });
        await refresh(); $('tiktok-video').value=name; $('tiktok-video').dispatchEvent(new Event('change'));
        $('live-upload-status').textContent=`${name} adicionado à biblioteca.`;
      }
    }catch(error){$('live-upload-status').textContent=error.message;}
    finally{xhr=null; e.target.value=''; e.target.disabled=false; $('live-upload-cancel').disabled=true;}
  };
})();
