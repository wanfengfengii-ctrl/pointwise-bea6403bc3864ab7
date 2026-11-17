import unittest
from trend import Store
from trend.samples import build


class TestSamples(unittest.TestCase):
    def test_complete_old_archive(self):
        with Store() as store:
            manifest = build(store)
            self.assertEqual(len(manifest['revisions']), 5)
            self.assertEqual(len(manifest['tasks']), 6)
            self.assertEqual(store.task('frozen-pending')['status'], 'pending')
            self.assertEqual(store.read_report('proper')['report']['covariance'], [[6, 7], [7, 10]])
            self.assertEqual(store.read_report('mixed')['report']['estimable'], ['x2', 'x3'])
            self.assertEqual(store.read_report('contradiction')['status'], 'error')
            self.assertEqual(store.connection.execute(
                'SELECT count(*) FROM reports').fetchone()[0], 4)
