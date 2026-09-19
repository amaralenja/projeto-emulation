import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from video_codes import FRAME_BYTES, import_video
from video_online import build_bundle, decode_code, download_bundle, online_code, import_online
from github_video import publish_video, published_code


class OnlineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'video.mov'; self.source.write_bytes(b'original movie')
        self.raw = self.root / 'raw.i420'; self.raw.write_bytes(b'x' * FRAME_BYTES)
        self.cache = dict(sha256=hashlib.sha256(self.source.read_bytes()).hexdigest(), fill=False,
            sourceSize=self.source.stat().st_size, sourceMtime=self.source.stat().st_mtime_ns,
            rawPath=str(self.raw), rawSize=FRAME_BYTES)
        self.bundle = self.root / 'bundle'
        self.url = 'https://example.test/video/manifest.json'
        self.code = build_bundle(self.source, self.cache, self.bundle, self.url, chunk_size=100000)
        self.calls = []

    def open(self, url):
        self.calls.append(url)
        return io.BytesIO((self.bundle / url.rsplit('/', 1)[-1]).read_bytes())

    def test_download_and_import_without_source_pc(self):
        self.source.unlink(); self.raw.unlink()
        progress = []
        root, code = download_bundle(self.code, self.root / 'area', lambda a,b: progress.append((a,b)), self.open)
        name = import_video(root, code, self.root / 'videos', self.root / 'area',
                            lambda src,fill: self.root / 'area/frame-cache/test.json')
        self.assertEqual((self.root / 'videos' / name).read_bytes(), b'original movie')
        meta = json.loads((self.root / 'area/frame-cache/test.json').read_bytes())
        self.assertEqual(Path(meta['rawPath']).read_bytes(), b'x' * FRAME_BYTES)
        self.assertEqual(progress[-1][0], progress[-1][1])

    def test_retry_reuses_completed_parts(self):
        def failing(url):
            if url.endswith('frames.i420.0001.part'): raise OSError('connection lost')
            return self.open(url)
        with self.assertRaises(OSError): download_bundle(self.code, self.root / 'area', opener=failing)
        self.calls.clear()
        download_bundle(self.code, self.root / 'area', opener=self.open)
        self.assertFalse(any(url.endswith('frames.i420.0000.part') for url in self.calls))
        self.assertFalse(any(url.endswith('original.0000.part') for url in self.calls))

    def test_import_remembers_online_code_and_removes_download_staging(self):
        area = self.root / 'area'
        metadata = lambda src,fill: area / 'frame-cache/test.json'
        with patch('video_online.download_bundle', side_effect=lambda code,area,progress: download_bundle(code,area,progress,self.open)):
            name = import_online(self.code, self.root / 'videos', area, metadata)
        cache = json.loads(metadata('',False).read_bytes())
        self.assertEqual(published_code(cache,area),self.code)
        self.assertTrue((self.root / 'videos' / name).exists())
        self.assertEqual(list((area / 'online-downloads').iterdir()),[])

    def test_tampered_manifest_rejected_before_parts(self):
        with (self.bundle / 'manifest.json').open('ab') as stream: stream.write(b' ')
        with self.assertRaises(ValueError): download_bundle(self.code, self.root / 'area', opener=self.open)
        self.assertEqual(self.calls, [self.url])

    def test_corrupt_and_oversized_parts_rejected(self):
        part = self.bundle / 'original.0000.part'
        for content in [b'bad', b'x' * 100]:
            part.write_bytes(content)
            with self.assertRaises(ValueError): download_bundle(self.code, self.root / 'area', opener=self.open)
        self.assertFalse(list((self.root / 'area').rglob('*.downloading')))

    def test_credentials_and_plain_http_rejected(self):
        for url in ['http://example.com/manifest.json', 'https://user:secret@example.com/manifest.json']:
            with self.assertRaises(ValueError): online_code(url, 'a' * 64)
        self.assertEqual(decode_code(self.code)[0], self.url)
        with self.assertRaises(ValueError): decode_code('VC2.invalid.hash')

    def test_publish_only_after_all_parts_confirmed_and_reuse(self):
        client = FakeGitHub()
        code = publish_video(self.source, self.cache, 'owner/repo', self.root / 'area', self.root, client=client)
        self.assertTrue(code.startswith('VC2.'))
        self.assertFalse(client.release['draft'])
        self.assertEqual(client.events[-1], 'publish')
        self.assertEqual(published_code(self.cache, self.root / 'area'), code)
        self.assertEqual(len(client.assets), 3)
        client.events.clear()
        self.assertEqual(publish_video(self.source, self.cache, 'owner/repo', self.root / 'area', self.root, client=client), code)
        self.assertEqual(client.events, [])

    def test_failed_upload_keeps_draft_and_no_online_code(self):
        client = FakeGitHub(fail_upload=True)
        with self.assertRaises(OSError):
            publish_video(self.source, self.cache, 'owner/repo', self.root / 'area', self.root, client=client)
        self.assertTrue(client.release['draft'])
        self.assertIsNone(published_code(self.cache, self.root / 'area'))


class FakeGitHub:
    def __init__(self, fail_upload=False):
        self.release = None; self.assets = []; self.events = []; self.fail_upload = fail_upload

    def request(self, method, url, body=None, file=None, progress=lambda n: None):
        if file:
            if self.fail_upload: raise OSError('upload interrupted')
            path = Path(file)
            asset = dict(name=path.name, size=path.stat().st_size, digest='sha256:' + hashlib.sha256(path.read_bytes()).hexdigest(), state='uploaded')
            self.assets.append(asset); self.events.append('upload'); progress(asset['size'])
            return asset
        if method == 'POST':
            self.release = dict(body, id=1, upload_url='https://uploads.github.com/repos/owner/repo/releases/1/assets{?name}')
            self.events.append('draft'); return self.release
        if method == 'PATCH':
            self.release.update(body); self.events.append('publish'); return self.release
        if '/assets?' in url: return self.assets
        if '/releases?' in url: return [self.release] if self.release else []
        return dict(private=False)


if __name__ == '__main__': unittest.main()
