"""Portable HTTPS video codes, hashed parts and resumable downloads."""
import base64
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import urllib.parse
import urllib.request

from video_codes import PROFILE, FRAME_BYTES, digest, import_video, video_code

CHUNK_SIZE = 1024 ** 3
MAX_MANIFEST = 1024 ** 2


def https_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('Use uma URL HTTPS pública, sem credenciais ou fragmento')
    return url


def online_code(url, manifest_hash):
    https_url(url)
    if not re.fullmatch('[a-f0-9]{64}', manifest_hash):
        raise ValueError('Hash do manifesto inválido')
    encoded = base64.urlsafe_b64encode(url.encode()).decode().rstrip('=')
    return f'VC2.{encoded}.{manifest_hash}'


def decode_code(code):
    if len(code) > 8192:
        raise ValueError('Código online muito longo')
    try:
        prefix, encoded, checksum = code.split('.')
        if prefix != 'VC2' or not re.fullmatch('[a-f0-9]{64}', checksum):
            raise ValueError()
        url = base64.b64decode(encoded + '=' * (-len(encoded) % 4), altchars=b'-_', validate=True).decode()
        return https_url(url), checksum
    except (ValueError, UnicodeError) as error:
        raise ValueError('Código online inválido') from error


def build_bundle(source, cache, destination, manifest_url, chunk_size=CHUNK_SIZE, store_parts=True):
    """Prepare upload assets. The caller must upload all files before sharing code."""
    https_url(manifest_url)
    if not 1 <= chunk_size <= CHUNK_SIZE:
        raise ValueError('Tamanho de parte inválido')
    source = Path(source)
    if source.stat().st_size != cache['sourceSize'] or source.stat().st_mtime_ns != cache['sourceMtime']:
        raise ValueError('Original alterado; prepare novamente')
    raw = Path(cache['rawPath'])
    if raw.stat().st_size != cache['rawSize'] or not cache['rawSize'] or cache['rawSize'] % FRAME_BYTES:
        raise ValueError('Quadros inválidos')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    total = cache['sourceSize'] + cache['rawSize']
    if shutil.disk_usage(destination).free < (total if store_parts else 0) + 256 * 1024 ** 2:
        raise ValueError('Sem espaço para o pacote online')
    manifest = dict(code=video_code(cache['sha256'], cache['fill']), profile=PROFILE,
                    name=source.name, fill=bool(cache['fill']), sourceSize=cache['sourceSize'],
                    rawSize=cache['rawSize'], sourceSha256=cache['sha256'], files={})
    for label, path in [('original', source), ('frames.i420', raw)]:
        whole = hashlib.sha256()
        parts = []
        with path.open('rb') as stream:
            while True:
                first = stream.read(min(chunk_size, 8 * 1024 ** 2))
                if not first:
                    break
                filename = f'{label}.{len(parts):04d}.part'
                part_hash = hashlib.sha256()
                size = 0
                with ((destination / filename).open('xb') if store_parts else nullcontext(None)) as output:
                    data = first
                    while data:
                        if output is not None: output.write(data)
                        whole.update(data); part_hash.update(data)
                        size += len(data)
                        data = stream.read(min(chunk_size - size, 8 * 1024 ** 2))
                parts.append(dict(name=filename, size=size, sha256=part_hash.hexdigest()))
        expected_size = manifest['sourceSize' if label == 'original' else 'rawSize']
        if sum(part['size'] for part in parts) != expected_size:
            raise ValueError('Arquivo alterado durante o empacotamento')
        if label == 'original' and whole.hexdigest() != cache['sha256']:
            raise ValueError('Original alterado durante o empacotamento')
        if label == 'frames.i420':
            manifest['rawSha256'] = whole.hexdigest()
        manifest['files'][label] = parts
    body = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()
    (destination / 'manifest.json').write_bytes(body)
    return online_code(manifest_url, hashlib.sha256(body).hexdigest())


def open_https(url):
    response = urllib.request.urlopen(https_url(url), timeout=60)
    try:
        https_url(response.geturl())
    except ValueError:
        response.close()
        raise
    return response


def download_bundle(code, area, progress=lambda done, total: None, opener=open_https):
    url, checksum = decode_code(code)
    with opener(url) as response:
        body = response.read(MAX_MANIFEST + 1)
    if len(body) > MAX_MANIFEST or hashlib.sha256(body).hexdigest() != checksum:
        raise ValueError('Manifesto online inválido ou alterado')
    data = json.loads(body)
    if data.get('profile') != PROFILE or type(data.get('fill')) is not bool:
        raise ValueError('Perfil online incompatível')
    if data.get('code') != video_code(data['sourceSha256'], data['fill']):
        raise ValueError('Identificador do pacote inválido')
    total = 0
    for label, key in [('original', 'sourceSize'), ('frames.i420', 'rawSize')]:
        parts = data['files'][label]
        if not parts or len(parts) > 1000:
            raise ValueError('Quantidade de partes inválida')
        for index, part in enumerate(parts):
            if (part['name'] != f'{label}.{index:04d}.part' or type(part['size']) is not int
                    or not 0 < part['size'] <= CHUNK_SIZE
                    or not re.fullmatch('[a-f0-9]{64}', part['sha256'])):
                raise ValueError('Parte inválida no manifesto')
        size = sum(part['size'] for part in parts)
        if size != data[key]:
            raise ValueError('Tamanho do pacote inválido')
        total += size
    if data['rawSize'] % FRAME_BYTES:
        raise ValueError('Tamanho dos quadros inválido')
    root = Path(area) / 'online-downloads' / checksum
    package = root / data['code']
    package.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(package).free < total * 2 + CHUNK_SIZE:
        raise ValueError('Reserve espaço para download, montagem e importação do pacote')
    done = 0
    for label, hash_key in [('original', 'sourceSha256'), ('frames.i420', 'rawSha256')]:
        target = package / label
        parts = data['files'][label]
        size = sum(part['size'] for part in parts)
        if target.exists() and target.stat().st_size == size and digest(target) == data[hash_key]:
            done += size; progress(done, total)
            continue
        for part in parts:
            local = root / part['name']
            if not (local.exists() and local.stat().st_size == part['size'] and digest(local) == part['sha256']):
                pending = local.with_suffix('.downloading')
                count = 0; hasher = hashlib.sha256()
                try:
                    with opener(urllib.parse.urljoin(url, part['name'])) as response, pending.open('wb') as output:
                        while chunk := response.read(min(8 * 1024 ** 2, part['size'] - count + 1)):
                            count += len(chunk)
                            if count > part['size']:
                                raise ValueError('Servidor enviou uma parte maior que o esperado')
                            output.write(chunk); hasher.update(chunk)
                            progress(done + count, total)
                    if count != part['size'] or hasher.hexdigest() != part['sha256']:
                        raise ValueError('Parte incompleta ou corrompida; tente novamente para retomar')
                    os.replace(pending, local)
                finally:
                    if pending.exists(): pending.unlink()
            done += part['size']; progress(done, total)
        assembled = target.with_suffix('.assembling')
        try:
            with assembled.open('wb') as output:
                for part in parts:
                    with (root / part['name']).open('rb') as inp:
                        shutil.copyfileobj(inp, output, 8 * 1024 ** 2)
            if digest(assembled) != data[hash_key]:
                raise ValueError('Falha de integridade ao montar o arquivo')
            os.replace(assembled, target)
        finally:
            if assembled.exists(): assembled.unlink()
        for part in parts: (root / part['name']).unlink(missing_ok=True)
    (package / 'manifest.json').write_bytes(body)
    return root, data['code']


def import_online(code, videos, area, metadata_path, progress=lambda done, total: None):
    root, asset_code = download_bundle(code, area, progress)
    name = import_video(root, asset_code, videos, area, metadata_path)
    manifest = json.loads((root / asset_code / 'manifest.json').read_bytes())
    metadata = Path(metadata_path(str(Path(videos) / name), manifest['fill']))
    data = json.loads(metadata.read_bytes()); data['onlineCode'] = code
    pending = metadata.with_suffix('.online.tmp')
    pending.write_text(json.dumps(data), encoding='utf-8'); os.replace(pending, metadata)
    # Only this completed download cache is removed; failed downloads remain resumable.
    shutil.rmtree(root)
    return name
