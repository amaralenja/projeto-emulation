const videoProgress=document.createElement('article');
videoProgress.className='panel';
videoProgress.style.cssText='padding:24px;margin:0 0 24px';
videoProgress.innerHTML='<div class="panel-heading"><h2>Importação e envio para as câmeras</h2><strong id="video-stage-percent">0%</strong></div><p id="video-stage">Aguardando</p><div class="progress"><span id="video-stage-bar"></span></div><p id="all-camera-video"></p><div id="camera-transfers"></div>';
document.querySelector('.video-layout').before(videoProgress);
const previousRender=render;
render=function(state){
  if(state.apiVersion!==4){location.replace("http://127.0.0.1:8768/");return}
  previousRender(state);
  const upload=app.uploadProgress;
  const percent=upload?upload.percent:state.progress||0;
  $('video-stage-percent').textContent=`${percent}%`;
  $('video-stage-bar').style.width=`${percent}%`;
  $('video-stage').textContent=upload?`${upload.name} • Importando ${size(upload.loaded)} de ${size(upload.total)}`:`${state.stage||'Aguardando'} • ${state.message||''}`;
  const selected=(state.videos||[]).find(v=>v.name===app.video);
  if(selected)$('preview-meta').textContent+=` • Câmera: ~${size(selected.duration*10368000)}`;
  $('all-camera-video').textContent=state.allVideoName?`Vídeo confirmado em todos: ${state.allVideoName}`:'Os celulares têm vídeos diferentes ou ainda não têm instalação confirmada. Confira abaixo.';
  $('current').textContent=state.allVideoName||'Confira por celular';
  $('current-size').textContent=state.allVideoName?'Confirmado em todos os celulares':'Vídeos diferentes ou não confirmados';
  $('camera-transfers').innerHTML=(state.phones||[]).map(phone=>{
    const transfer=(state.transfers||{})[phone.serial];
    const installed=phone.installedVideo;
    return `<div class="usage-row"><header><strong>${esc(phone.name)}</strong><span>${esc(phone.storage||'')} • ${phone.status==='online'?'Online':phone.status==='off'?'Desligado':'Iniciando'}</span></header><p>Na câmera: <strong>${esc(installed?.name||'Não confirmado')+(installed&&!installed.confirmed?' (aguardando confirmação)':'')}</strong>${installed?` • ${size(installed.bytes)} de quadros`:''}</p>${transfer?`<header><span>${esc(transfer.stage)} • ${esc(transfer.video)}</span><strong>${transfer.percent||0}%</strong></header><div class="mini-track"><i style="width:${transfer.percent||0}%"></i></div><small>${size(transfer.bytes)} / ${size(transfer.total)}${transfer.stage==="Enviando"&&transfer.speed?` • ${size(transfer.speed)}/s • ~${Math.ceil(transfer.eta/60)} min`:""}${transfer.error?` • ${esc(transfer.error)}`:''}</small>`:''}</div>`;
  }).join('');
  for(const id of ['install','install-all','add','upload'])$(id).disabled=!!state.busy||!!app.uploadProgress;
};
$('upload').onchange=async event=>{
  const file=event.target.files[0];if(!file)return;
  app.uploadProgress={name:file.name,percent:0,loaded:0,total:file.size};render(app.state);
  try{
    const body=await new Promise((resolve,reject)=>{
      const xhr=new XMLHttpRequest();xhr.open('POST','/api/upload');xhr.setRequestHeader('X-Filename',encodeURIComponent(file.name));
      xhr.upload.onprogress=e=>{app.uploadProgress={name:file.name,percent:e.lengthComputable?Math.min(99,Math.floor(e.loaded*100/e.total)):0,loaded:e.loaded,total:e.total||file.size};render(app.state)};
      xhr.onload=()=>{try{const body=JSON.parse(xhr.responseText);xhr.status>=200&&xhr.status<300?resolve(body):reject(Error(body.error||'Falha ao importar'))}catch(e){reject(e)}};
      xhr.onerror=()=>reject(Error('Conexão interrompida durante a importação'));
      xhr.onabort=()=>reject(Error('Importação cancelada'));xhr.send(file);
    });
    app.video=body.name;app.videoHash='';toast('Vídeo importado');
  }catch(error){toast(error.message)}
  finally{app.uploadProgress=null;event.target.value='';await refresh()}
};
document.querySelector('.bulk-note span').textContent='“Usar em todos” prepara uma vez e envia a dois celulares por vez. Os que estavam desligados voltam a esse estado após a confirmação.';

const transferStyles=document.createElement("style");transferStyles.textContent="#camera-transfers{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px 24px}#camera-transfers p{margin:8px 0;font-size:13px}#camera-transfers small{display:block;overflow-wrap:anywhere}.usage-row header{gap:10px}";document.head.append(transferStyles);
