"""Portable prepared-camera assets in a user-selected shared folder."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

PROFILE = 'i420-640x360-30-v1'
FRAME_BYTES = 640 * 360 * 3 // 2

def video_code(source_sha, fill=False):
    if not re.fullmatch(r'[a-f0-9]{64}', source_sha):
        raise ValueError('SHA-256 inválido')
    return 'VC1-' + hashlib.sha256((source_sha + ':' + PROFILE + ':' + str(bool(fill))).encode()).hexdigest()

def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as stream:
        while chunk:=stream.read(8*1024*1024):h.update(chunk)
    return h.hexdigest()

def copy_checked(source, target, expected=None):
    h=hashlib.sha256()
    with open(source,'rb') as inp, open(target,'xb') as out:
        while chunk:=inp.read(8*1024*1024):
            out.write(chunk);h.update(chunk)
    result=h.hexdigest()
    if expected and result!=expected:raise ValueError('Arquivo corrompido ou alterado durante a transferência')
    return result

def manifest_for(root, code):
    if not re.fullmatch(r'VC1-[a-f0-9]{64}',code):raise ValueError('Código de vídeo inválido')
    base=Path(root).resolve();folder=base/code
    if not folder.resolve().is_relative_to(base):raise ValueError('Pacote fora da pasta compartilhada')
    data=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if data.get('profile')!=PROFILE or type(data.get('fill')) is not bool:
        raise ValueError('Perfil de câmera incompatível')
    if data.get('code')!=code or video_code(data['sourceSha256'],data['fill'])!=code:
        raise ValueError('Código não corresponde ao pacote')
    name=data.get('name','')
    if not name or name!=Path(name).name or any(c in name for c in '/\\:') or name in ('.','..'):
        raise ValueError('Nome de vídeo inválido')
    if Path(name).suffix.lower() not in ('.mp4','.mov','.mkv','.avi','.webm','.m4v'):
        raise ValueError('Formato do original não suportado')
    for file,size in [('original',data['sourceSize']),('frames.i420',data['rawSize'])]:
        path=folder/file
        if path.is_symlink() or not path.is_file() or path.stat().st_size!=size:
            raise ValueError('Pacote incompleto: '+file)
    if data['rawSize']<=0 or data['rawSize']%FRAME_BYTES:
        raise ValueError('Tamanho dos quadros inválido')
    return folder,data

def export_video(root, source, cache):
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    source=Path(source);raw=Path(cache['rawPath'])
    if source.stat().st_size!=cache['sourceSize'] or source.stat().st_mtime_ns!=cache['sourceMtime']:
        raise ValueError('Prepare novamente: original alterado')
    if raw.stat().st_size!=cache['rawSize'] or cache['rawSize']<=0 or cache['rawSize']%FRAME_BYTES:
        raise ValueError('Cache de quadros inválido')
    code=video_code(cache['sha256'],cache['fill']);target=root/code
    if target.exists():
        folder,data=manifest_for(root,code)
        if digest(folder/'original')!=data['sourceSha256'] or digest(folder/'frames.i420')!=data['rawSha256']:
            raise ValueError('Pacote existente corrompido; preserve-o e use outra pasta de destino')
        return code
    if shutil.disk_usage(root).free<cache['sourceSize']+cache['rawSize']+256*1024**2:
        raise ValueError('Sem espaço para original e quadros no destino')
    staging=Path(tempfile.mkdtemp(prefix='.video-',dir=root))
    try:
        copy_checked(source,staging/'original',cache['sha256'])
        raw_sha=copy_checked(raw,staging/'frames.i420')
        data=dict(code=code,profile=PROFILE,name=source.name,fill=bool(cache['fill']),
                  sourceSha256=cache['sha256'],rawSha256=raw_sha,
                  sourceSize=cache['sourceSize'],rawSize=cache['rawSize'])
        (staging/'manifest.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        staging.rename(target)
        return code
    finally:
        if staging.exists():shutil.rmtree(staging)

def import_video(root, code, videos, area, metadata_path):
    folder,data=manifest_for(root,code)
    videos=Path(videos).resolve();videos.mkdir(parents=True,exist_ok=True)
    raw_folder=Path(area).resolve()/'frame-cache';raw_folder.mkdir(parents=True,exist_ok=True)
    required=data['sourceSize']+data['rawSize']+256*1024**2
    if min(shutil.disk_usage(videos).free,shutil.disk_usage(raw_folder).free)<required:
        raise ValueError('Sem espaço para baixar original e quadros')
    name=data['name'];target=videos/name
    number=2
    while target.exists():
        if target.stat().st_size==data['sourceSize'] and digest(target)==data['sourceSha256']:break
        target=videos/(Path(name).stem+f' ({number})'+Path(name).suffix);number+=1
    temp_source=videos/('.'+uuid.uuid4().hex+'.importing')
    temp_raw=raw_folder/('.'+uuid.uuid4().hex+'.importing')
    raw=raw_folder/(code+'.i420')
    try:
        if not target.exists():copy_checked(folder/'original',temp_source,data['sourceSha256'])
        if not raw.exists():copy_checked(folder/'frames.i420',temp_raw,data['rawSha256'])
        elif raw.stat().st_size!=data['rawSize'] or digest(raw)!=data['rawSha256']:
            raise ValueError('Cache local corrompido; não será substituído enquanto pode estar em uso')
        if temp_source.exists():os.replace(temp_source,target)
        if temp_raw.exists():os.replace(temp_raw,raw)
        meta=dict(name=target.name,sha256=data['sourceSha256'],fill=data['fill'],
                  sourceSize=target.stat().st_size,sourceMtime=target.stat().st_mtime_ns,
                  rawSize=data['rawSize'],rawPath=str(raw))
        metadata=Path(metadata_path(str(target),data['fill']))
        pending=metadata.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        pending.write_text(json.dumps(meta),encoding='utf-8');os.replace(pending,metadata)
        return target.name
    finally:
        for temporary in (temp_source,temp_raw):
            if temporary.exists():temporary.unlink()
