"""Publish prepared video bundles as GitHub Release assets, never Git blobs."""
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.parse

from video_codes import digest, video_code
from video_online import build_bundle, online_code


def github_token(repo_directory):
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token:
        return token
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
    try:
        result = subprocess.run(['git', 'credential', 'fill'],
                                input='protocol=https\nhost=github.com\n\n', text=True,
                                capture_output=True, cwd=repo_directory, env=env, timeout=30,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        if result.returncode == 0 and fields.get('password'):
            return fields['password']
    except (OSError, subprocess.TimeoutExpired):
        pass
    raise ValueError('Conecte o Git ao GitHub neste PC ou configure GITHUB_TOKEN no ambiente do servidor. Não cole sua chave no código do vídeo.')


class GitHub:
    def __init__(self, token):
        self.token = token

    def request(self, method, url, body=None, file=None, progress=lambda amount: None):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname not in ('api.github.com', 'uploads.github.com') or parsed.username:
            raise ValueError('Destino GitHub inválido')
        headers = {'Authorization': 'Bearer ' + self.token, 'User-Agent': 'Emulation-Video-Codes',
                   'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
        payload = json.dumps(body).encode() if body is not None else b''
        headers['Content-Length'] = str(Path(file).stat().st_size if file else len(payload))
        headers['Content-Type'] = 'application/octet-stream' if file else 'application/json'
        connection = http.client.HTTPSConnection(parsed.hostname, timeout=120)
        try:
            connection.putrequest(method, parsed.path + ('?' + parsed.query if parsed.query else ''))
            for key, value in headers.items(): connection.putheader(key, value)
            connection.endheaders()
            if file:
                sent = 0
                with open(file, 'rb') as stream:
                    while chunk := stream.read(4 * 1024 ** 2):
                        connection.send(chunk); sent += len(chunk); progress(sent)
            elif payload:
                connection.send(payload)
            response = connection.getresponse()
            content = response.read(4 * 1024 ** 2)
            if not 200 <= response.status < 300:
                raise ValueError(f'GitHub respondeu HTTP {response.status}. Confira conexão, permissões de escrita e tente novamente; partes concluídas serão reutilizadas.')
            return json.loads(content) if content else None
        finally:
            connection.close()


def publish_video(source, cache, repository, area, repo_directory, progress=lambda message, percent: None,
                  client=None):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Informe o repositório como dono/nome')
    client = client or GitHub(github_token(repo_directory))
    api = 'https://api.github.com/repos/' + repository
    repo = client.request('GET', api)
    if repo.get('private'):
        raise ValueError('Este fluxo exige um repositório público para permitir download sem login em qualquer PC')
    code = video_code(cache['sha256'], cache['fill'])
    tag = 'video-' + code
    manifest_url = f'https://github.com/{repository}/releases/download/{tag}/manifest.json'
    parent = Path(area) / 'online-publish'
    parent.mkdir(parents=True, exist_ok=True)
    bundle = parent / code
    if not (bundle / 'manifest.json').exists():
        progress('Preparando partes para publicação; o tempo depende do tamanho do vídeo.', 0)
        temporary = Path(tempfile.mkdtemp(prefix='building-', dir=parent))
        try:
            build_bundle(source, cache, temporary / 'bundle', manifest_url)
            (temporary / 'bundle').rename(bundle)
        finally:
            shutil.rmtree(temporary)
    manifest = json.loads((bundle / 'manifest.json').read_bytes())
    assets = [part for parts in manifest['files'].values() for part in parts]
    assets.append(dict(name='manifest.json', size=(bundle / 'manifest.json').stat().st_size,
                       sha256=digest(bundle / 'manifest.json')))
    if len(assets) > 1000:
        raise ValueError('Pacote ultrapassa 1000 partes; use outro armazenamento')
    for asset in assets:
        path = bundle / asset['name']
        if path.stat().st_size != asset['size'] or digest(path) != asset['sha256']:
            raise ValueError('Pacote local alterado; não será publicado')
    release = None
    for page in range(1, 101):
        releases = client.request('GET', api + f'/releases?per_page=100&page={page}')
        release = next((item for item in releases if item['tag_name'] == tag), None)
        if release or len(releases) < 100: break
    if release is None:
        release = client.request('POST', api + '/releases', dict(tag_name=tag,
            name='Vídeo preparado: ' + Path(source).name,
            body='Pacote de vídeo e quadros para importação pelo painel Emulation.',
            draft=True, make_latest='false'))
    existing = {}
    for page in range(1, 12):
        page_assets = client.request('GET', api + f'/releases/{release["id"]}/assets?per_page=100&page={page}')
        existing.update({asset['name']: asset for asset in page_assets})
        if len(page_assets) < 100: break
    total = sum(asset['size'] for asset in assets)
    done = 0
    for asset in assets:
        old = existing.get(asset['name'])
        if old and old.get('state') == 'uploaded' and old.get('digest') == 'sha256:' + asset['sha256']:
            done += asset['size']; progress('Reutilizando parte já publicada: ' + asset['name'], done / total * 99)
            continue
        if old:
            if not release['draft']:
                raise ValueError('Release publicado contém uma parte diferente; não será sobrescrito')
            client.request('DELETE', api + f'/releases/assets/{old["id"]}')
        upload_url = release['upload_url'].split('{', 1)[0] + '?name=' + urllib.parse.quote(asset['name'])
        uploaded = client.request('POST', upload_url, file=bundle / asset['name'],
            progress=lambda amount: progress('Enviando ' + asset['name'], (done + amount) / total * 99))
        if uploaded.get('digest') != 'sha256:' + asset['sha256'] or uploaded.get('size') != asset['size']:
            raise ValueError('GitHub não confirmou a integridade da parte; tente novamente')
        done += asset['size']
    if release['draft']:
        client.request('PATCH', api + f'/releases/{release["id"]}', dict(draft=False, make_latest='false'))
    result = online_code(manifest_url, assets[-1]['sha256'])
    (bundle / 'published-code.txt').write_text(result, encoding='utf-8')
    progress('Publicado online. Copie o código para usar em outro PC.', 100)
    return result


def published_code(cache, area):
    if not cache: return None
    if cache.get('onlineCode'): return cache['onlineCode']
    try:
        path = Path(area) / 'online-publish' / video_code(cache['sha256'], cache['fill']) / 'published-code.txt'
        return path.read_text(encoding='utf-8')
    except (OSError, KeyError, ValueError):
        return None
