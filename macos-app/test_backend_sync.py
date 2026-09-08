import tempfile
import unittest
from pathlib import Path
from check_backend import FILES, compare, require_current


class SyncTests(unittest.TestCase):
    def test_stale_and_missing_sources_stop_build(self):
        with tempfile.TemporaryDirectory() as td:
            source, snapshot = Path(td) / 'source', Path(td) / 'snapshot'
            source.mkdir(); snapshot.mkdir()
            for name in FILES:
                (source / name).parent.mkdir(parents=True, exist_ok=True)
                (snapshot / name).parent.mkdir(parents=True, exist_ok=True)
                (source / name).write_text('original')
                (snapshot / name).write_text('original')
            self.assertTrue(require_current(source, snapshot)['matches'])
            (source / 'vx.py').write_text('Claude new change')
            with self.assertRaisesRegex(RuntimeError, 'vx.py'):
                require_current(source, snapshot)
            self.assertEqual((snapshot / 'vx.py').read_text(), 'original')
            self.assertEqual((source / 'vx.py').read_text(), 'Claude new change')
            (snapshot / 'vx.py').write_text('Claude new change')
            (source / 'vx_wxchannels.py').unlink()
            with self.assertRaisesRegex(RuntimeError, 'vx_wxchannels.py'):
                require_current(source, snapshot)
            (snapshot / 'vx_wxchannels.py').unlink()
            self.assertFalse(compare(source, snapshot)['matches'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
