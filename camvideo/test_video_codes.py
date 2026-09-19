import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from video_codes import FRAME_BYTES, export_video, import_video, video_code

class VideoCodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.share=self.root/'share'
        self.src=self.root/'original.mov';self.src.write_bytes(b'original-video')
        self.raw=self.root/'prepared.i420';self.raw.write_bytes(b'0'*FRAME_BYTES)
        self.cache=dict(name=self.src.name,sha256=hashlib.sha256(self.src.read_bytes()).hexdigest(),
            fill=False,sourceSize=self.src.stat().st_size,sourceMtime=self.src.stat().st_mtime_ns,
            rawPath=str(self.raw),rawSize=FRAME_BYTES)
        self.dest=self.root/'destination';self.area=self.root/'area'
    def metadata(self,src,fill):return self.area/'frame-cache'/'meta.json'
    def test_portable_roundtrip_and_repeated_import_reuses_files(self):
        code=export_video(self.share,self.src,self.cache)
        name=import_video(self.share,code,self.dest,self.area,self.metadata)
        self.assertEqual((self.dest/name).read_bytes(),self.src.read_bytes())
        meta=json.loads(self.metadata('',False).read_text())
        self.assertEqual(Path(meta['rawPath']).read_bytes(),self.raw.read_bytes())
        self.assertEqual(meta['sourceMtime'],(self.dest/name).stat().st_mtime_ns)
        self.assertEqual(import_video(self.share,code,self.dest,self.area,self.metadata),name)
        self.assertEqual(len(list(self.dest.iterdir())),1)
    def test_code_stable_and_enquadramento_distinct(self):
        self.assertEqual(video_code(self.cache['sha256']),video_code(self.cache['sha256']))
        self.assertNotEqual(video_code(self.cache['sha256']),video_code(self.cache['sha256'],True))
    def test_corrupted_frames_do_not_publish_local_cache(self):
        code=export_video(self.share,self.src,self.cache)
        (self.share/code/'frames.i420').write_bytes(b'1'*FRAME_BYTES)
        with self.assertRaises(ValueError):import_video(self.share,code,self.dest,self.area,self.metadata)
        self.assertFalse(self.metadata('',False).exists())
        self.assertEqual(list(self.dest.iterdir()),[])
    def test_same_filename_preserves_existing_video(self):
        code=export_video(self.share,self.src,self.cache)
        self.dest.mkdir();(self.dest/self.src.name).write_bytes(b'other')
        name=import_video(self.share,code,self.dest,self.area,self.metadata)
        self.assertNotEqual(name,self.src.name)
        self.assertEqual((self.dest/self.src.name).read_bytes(),b'other')
    def test_traversal_and_profile_rejected(self):
        with self.assertRaises(ValueError):import_video(self.share,'../outside',self.dest,self.area,self.metadata)
        code=export_video(self.share,self.src,self.cache)
        manifest=self.share/code/'manifest.json';data=json.loads(manifest.read_text());data['name']='../bad.mov'
        manifest.write_text(json.dumps(data))
        with self.assertRaises(ValueError):import_video(self.share,code,self.dest,self.area,self.metadata)
        data['name']='fine.mov';data['profile']='unsupported';manifest.write_text(json.dumps(data))
        with self.assertRaises(ValueError):import_video(self.share,code,self.dest,self.area,self.metadata)
    def test_changed_source_rejected(self):
        self.src.write_bytes(b'different size original')
        with self.assertRaises(ValueError):export_video(self.share,self.src,self.cache)
    def test_existing_corrupted_export_rejected(self):
        code=export_video(self.share,self.src,self.cache)
        (self.share/code/'frames.i420').write_bytes(b'1'*FRAME_BYTES)
        with self.assertRaises(ValueError):export_video(self.share,self.src,self.cache)

if __name__=='__main__':unittest.main()
