import os, tempfile, unittest
from pathlib import Path
from core import *
class Tests(unittest.TestCase):
    def test_urls(self):
        self.assertTrue(is_youtube_url("https://youtu.be/abc"))
        self.assertFalse(is_youtube_url("https://youtube.com.evil.test"))
        self.assertFalse(is_youtube_url("https://user@youtube.com/watch"))
    def test_quality(self):
        for q in QUALITY_CHOICES[1:-1]: self.assertIn("height<="+q[:-1],format_for_quality(q))
        self.assertEqual(format_for_quality(QUALITY_CHOICES[-1]),"bestaudio/best")
    def test_options(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); suffix=".exe" if os.name=="nt" else ""
            for f in ("ffmpeg","ffprobe","deno"): (p/(f+suffix)).touch()
            for q in QUALITY_CHOICES:
                opts=make_options(p/"output",q,True,None,None,None,p)
                self.assertFalse(opts["noplaylist"]); self.assertTrue(opts["continuedl"])
                self.assertEqual(opts["concurrent_fragment_downloads"],3)
                self.assertNotIn("cookiesfrombrowser",opts)
                self.assertNotIn("cookiefile",opts)
            self.assertEqual(opts["postprocessors"][0]["preferredquality"],"192")
    def test_direct(self):
        seen=[]
        class Fake:
            def __init__(self,opts): seen.append(opts)
            def __enter__(self): return self
            def __exit__(self,*a): pass
            def download(self,urls): seen.append(urls); return 0
        self.assertEqual(direct_download(Fake,{"cookiefile":"bad","cookiesfrombrowser":("chrome",)},"https://youtu.be/abc"),0)
        self.assertEqual(seen,[{},["https://youtu.be/abc"]])
    def test_error_not_retried(self):
        calls=[]
        class Fake:
            def __init__(self,opts): calls.append(opts)
            def __enter__(self): return self
            def __exit__(self,*a): pass
            def download(self,urls): raise RuntimeError("Sign in required")
        with self.assertRaisesRegex(RuntimeError,"Sign in required"): direct_download(Fake,{},"https://youtu.be/abc")
        self.assertEqual(len(calls),1)
if __name__=="__main__": unittest.main()
