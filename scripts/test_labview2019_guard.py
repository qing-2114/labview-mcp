"""Regression checks for safe rejection of unsupported 2019 class links."""
import contextlib
import io
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / 'aixml-pylabview'))
import aixml2vi


class ClassLinkGuardTests(unittest.TestCase):
    def composer(self, links):
        composer = aixml2vi.Composer.__new__(aixml2vi.Composer)
        composer.target_major = 19
        composer.dyn_links = links
        composer.class_consts = {}
        composer.tcpi = {}
        composer._fp_class_links = lambda: {}
        return composer

    def test_plain_2019_vi_needs_no_class_links(self):
        self.composer({}).write_class_links(None, None, None)

    def test_2019_class_link_is_refused_before_serialization(self):
        composer = self.composer({'call': {'owner': 'Box', 'qual': ['Box', 'Read.vi'], 'lib_ref': []}})
        with self.assertRaisesRegex(aixml2vi.Unsupported, '2019 class-linked'):
            composer.write_class_links(None, None, None)

    def test_write_refusal_preserves_existing_output_and_returns_exit_two(self):
        with tempfile.TemporaryDirectory() as folder:
            output = pathlib.Path(folder) / 'existing.vi'
            output.write_bytes(b'existing VI must survive')
            with patch.object(aixml2vi.resolve, 'parse_args', side_effect=lambda args: args), \
                 patch.object(aixml2vi, 'Composer') as factory, \
                 patch.object(aixml2vi.lvheap, 'rebuild') as rebuild, \
                 contextlib.redirect_stderr(io.StringIO()) as stderr:
                factory.return_value.write.side_effect = aixml2vi.Unsupported('2019 class-linked')
                code = aixml2vi.main(['source.xml', str(output), '--lv-version', '19'])
                self.assertEqual(code, 2)
                self.assertIn('UNSUPPORTED', stderr.getvalue())
                rebuild.assert_not_called()
            self.assertEqual(output.read_bytes(), b'existing VI must survive')


if __name__ == '__main__':
    unittest.main()
