(() => {
  const online=document.createElement('article');online.className='panel';online.style.cssText='padding:24px;margin-bottom:24px';
  online.innerHTML=`<h2>Baixar vídeo pela internet</h2><p>Cole o código online do vídeo. Este computador baixa o original e os quadros preparados, sem precisar acessar o PC que publicou.</p><label for="asset-online-code">Código online</label><input id="asset-online-code" style="width:100%" placeholder="VC2.…"><button class="button button-secondary" id="asset-online-import">Baixar e preparar</button><p id="asset-online-status" role="status" aria-live="polite"></p><progress id="asset-online-progress" max="100" value="0" style="width:100%"></progress><small>O pacote precisa estar publicado na internet. Um código VC1 de pasta compartilhada não é um código online. Se a transferência falhar, tente novamente: as partes completas serão reutilizadas.</small>`;
  document.querySelector('.video-layout').before(online);
  const publish=document.createElement('article');publish.className='panel';publish.style.cssText='padding:24px;margin-bottom:24px';
  publish.innerHTML=`<h2>Publicar no GitHub para outros PCs</h2><p id="asset-public-selection"></p><label for="asset-repository">Repositório público</label><input id="asset-repository" style="width:100%" value="amaralenja/projeto-emulation"><p><label><input type="checkbox" id="asset-confirm-public"> Publicar o vídeo selecionado e seus quadros para qualquer pessoa baixar.</label></p><button class="button button-secondary" id="asset-github-publish">Publicar vídeo selecionado no GitHub</button><p id="asset-public-status" role="status"></p><label for="asset-online-share-code">Código online para copiar no outro PC</label><input id="asset-online-share-code" readonly style="width:100%" placeholder="Disponível depois de concluir a publicação"><small>A publicação envia arquivos grandes e exige uma conta GitHub com acesso de escrita conectada ao Git neste PC. O outro PC só precisa do código e de internet.</small>`;
  document.querySelector('.video-layout').before(publish);
  let publicSelection='';
  const card=document.createElement('article');card.className='panel';card.style.cssText='padding:24px;margin-bottom:24px';
  card.innerHTML=`<h2>Vídeos por código</h2><p>Publique uma vez o original e os quadros preparados em uma pasta compartilhada. Em outro PC, use essa pasta e o código para importar sem converter novamente.</p><label for="asset-folder">Pasta compartilhada</label><input id="asset-folder" style="width:100%" placeholder="Caminho completo da pasta compartilhada"><p id="asset-selected"></p><label for="asset-current-code">Código do vídeo selecionado</label><input id="asset-current-code" readonly style="width:100%"><button class="button button-secondary" id="asset-export">Publicar vídeo preparado</button><label for="asset-code">Código para importar</label><input id="asset-code" style="width:100%" placeholder="VC1-..."><button class="button button-secondary" id="asset-import">Importar pelo código</button><p id="asset-status" role="status"></p><small>O código identifica os arquivos, não contém o vídeo. A primeira transferência ocupa rede e disco; depois o cache local é reutilizado. Nenhuma câmera é trocada automaticamente.</small>`;
  document.querySelector('.video-layout').before(card);
  const folder=$('asset-folder');folder.value=localStorage.getItem('video-code-folder')||'';
  folder.onchange=()=>localStorage.setItem('video-code-folder',folder.value.trim());
  const before=render;
  render=state=>{
    before(state);
    $('asset-online-import').disabled=!state.videoCodesOnlineVersion||state.busy||state.backgroundVideo?.busy;
    const active=state.operation==='video_code_online_import';
    $('asset-online-status').textContent=!state.videoCodesOnlineVersion?'Reabra o servidor atualizado para habilitar o download online.':active?state.message:'Aguardando um código de pacote publicado online.';
    $('asset-online-progress').value=active?state.progress||0:0;
    const item=(state.videos||[]).find(v=>v.name===app.video);
    const code=$('fill').checked?item?.croppedVideoCode:item?.videoCode;
    const selection=app.video+':'+$('fill').checked;
    if(selection!==publicSelection){$('asset-confirm-public').checked=false;publicSelection=selection;}
    $('asset-public-selection').textContent=app.video?'Será publicado: '+app.video:'Selecione o vídeo que deseja publicar.';
    $('asset-online-share-code').value=($('fill').checked?item?.croppedOnlineVideoCode:item?.onlineVideoCode)||'';
    $('asset-github-publish').disabled=!state.videoCodesOnlineVersion||state.busy||state.backgroundVideo?.busy||!code||!$('asset-confirm-public').checked;
    $('asset-public-status').textContent=state.operation==='video_code_github_publish'?`${Math.floor(state.progress||0)}% — ${state.message}`:'Publicação em partes de até 1 GiB. O código só fica disponível após concluir.';
    $('asset-selected').textContent=app.video?'Selecionado: '+app.video:'Selecione um vídeo da biblioteca.';
    $('asset-current-code').value=code||'Prepare o vídeo para gerar seu código';
    const blocked=!state.videoCodesVersion||state.busy||state.backgroundVideo?.busy;
    $('asset-export').disabled=!!blocked||!code;
    $('asset-import').disabled=!!blocked;
    $('asset-status').textContent=!state.videoCodesVersion?'Reabra o servidor atualizado para usar os códigos.':['video_code_export','video_code_import'].includes(state.operation)?state.message:'Informe a mesma pasta compartilhada nos dois PCs.';
  };
  $('fill').addEventListener('change',()=>render(app.state));
  $('asset-confirm-public').onchange=()=>render(app.state);
  $('asset-github-publish').onclick=async()=>{
    if(!$('asset-confirm-public').checked)return;
    if(publicSelection!==app.video+':'+$('fill').checked){render(app.state);return toast('O vídeo selecionado mudou. Confirme a publicação desse vídeo.');}
    $('asset-github-publish').disabled=true;
    try{await call('video_code_github_publish',{video:app.video,fill:$('fill').checked,repository:$('asset-repository').value.trim(),confirmPublic:true});await refresh();}
    catch(error){toast(error.message);render(app.state);}
  };
  $('asset-online-import').onclick=async()=>{
    const code=$('asset-online-code').value.trim();
    if(!code.startsWith('VC2.'))return toast('Cole um código online VC2. O código VC1 exige uma pasta compartilhada.');
    $('asset-online-import').disabled=true;
    try{await call('video_code_online_import',{code});await refresh();}
    catch(error){toast(error.message);render(app.state);}
  };
  for(const [id,action] of [['asset-export','video_code_export'],['asset-import','video_code_import']]){
    $(id).onclick=async()=>{
      if(!folder.value.trim()){folder.focus();return toast('Informe a pasta compartilhada');}
      $(id).disabled=true;
      try{await call(action,{folder:folder.value.trim(),video:app.video,fill:$('fill').checked,code:$('asset-code').value.trim()});await refresh();}
      catch(error){toast(error.message);render(app.state);}
    };
  }
})();
