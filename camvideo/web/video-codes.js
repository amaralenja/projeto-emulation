(() => {
  const card=document.createElement('article');card.className='panel';card.style.cssText='padding:24px;margin-bottom:24px';
  card.innerHTML=`<h2>Vídeos por código</h2><p>Publique uma vez o original e os quadros preparados em uma pasta compartilhada. Em outro PC, use essa pasta e o código para importar sem converter novamente.</p><label for="asset-folder">Pasta compartilhada</label><input id="asset-folder" style="width:100%" placeholder="Caminho completo da pasta compartilhada"><p id="asset-selected"></p><label for="asset-current-code">Código do vídeo selecionado</label><input id="asset-current-code" readonly style="width:100%"><button class="button button-secondary" id="asset-export">Publicar vídeo preparado</button><label for="asset-code">Código para importar</label><input id="asset-code" style="width:100%" placeholder="VC1-..."><button class="button button-secondary" id="asset-import">Importar pelo código</button><p id="asset-status" role="status"></p><small>O código identifica os arquivos, não contém o vídeo. A primeira transferência ocupa rede e disco; depois o cache local é reutilizado. Nenhuma câmera é trocada automaticamente.</small>`;
  document.querySelector('.video-layout').before(card);
  const folder=$('asset-folder');folder.value=localStorage.getItem('video-code-folder')||'';
  folder.onchange=()=>localStorage.setItem('video-code-folder',folder.value.trim());
  const before=render;
  render=state=>{
    before(state);
    const item=(state.videos||[]).find(v=>v.name===app.video);
    const code=$('fill').checked?item?.croppedVideoCode:item?.videoCode;
    $('asset-selected').textContent=app.video?'Selecionado: '+app.video:'Selecione um vídeo da biblioteca.';
    $('asset-current-code').value=code||'Prepare o vídeo para gerar seu código';
    const blocked=!state.videoCodesVersion||state.busy||state.backgroundVideo?.busy;
    $('asset-export').disabled=!!blocked||!code;
    $('asset-import').disabled=!!blocked;
    $('asset-status').textContent=!state.videoCodesVersion?'Reabra o servidor atualizado para usar os códigos.':['video_code_export','video_code_import'].includes(state.operation)?state.message:'Informe a mesma pasta compartilhada nos dois PCs.';
  };
  $('fill').addEventListener('change',()=>render(app.state));
  for(const [id,action] of [['asset-export','video_code_export'],['asset-import','video_code_import']]){
    $(id).onclick=async()=>{
      if(!folder.value.trim()){folder.focus();return toast('Informe a pasta compartilhada');}
      $(id).disabled=true;
      try{await call(action,{folder:folder.value.trim(),video:app.video,fill:$('fill').checked,code:$('asset-code').value.trim()});await refresh();}
      catch(error){toast(error.message);render(app.state);}
    };
  }
})();
