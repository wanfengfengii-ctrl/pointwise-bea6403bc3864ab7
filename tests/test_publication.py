import tempfile
from pathlib import Path
from trend import Store
from .support import ArchiveCase, DIFFUSE, query


class TestReportPublication(ArchiveCase):
    def test_commit_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'archive.sqlite'
            with Store(path) as store:
                revision = store.apply('s', 'r', DIFFUSE, [[0, 5, 0], [1, 7, 0]])['revision']
                store.create_task('t', revision, 2, [query('x2', (2, 1))])
                def fail(label):
                    if label == 'publish':
                        raise OSError('before commit')
                store.before_commit = fail
                with self.assertRaises(OSError):
                    store.analyze('t')
            with Store(path) as store:
                self.assertEqual(store.read_report('t')['status'], 'pending')
                self.assertIsNone(store.read_report('t')['report'])
                self.assertIsNone(store.read_report('t')['receipt'])
                self.assertEqual(store.connection.execute(
                    'SELECT count(*) FROM reports').fetchone()[0], 0)
                self.assertEqual(store.connection.execute(
                    'SELECT count(*) FROM task_receipts').fetchone()[0], 0)
                result = store.analyze('t')
                self.assertEqual(result['report']['mean'], [9])
                self.assertEqual(store.analyze('t'), result)
                self.assertEqual(store.connection.execute(
                    'SELECT count(*) FROM task_receipts').fetchone()[0], 1)
            with Store(path) as store:
                self.assertEqual(store.read_report('t'), result)
                checkpoint = store.connection.execute(
                    'SELECT sdk1_checkpoint FROM reports WHERE task=?', ('t',)).fetchone()[0]
                self.assertIn('trend1.trajectory/1', checkpoint)

    def test_numeric_and_terminal_rollback_in_memory(self):
        revision = self.revision(observations=[[0, 5, 0], [1, 7, 0]])
        self.store.create_task('t', revision, 2, [query('x2', (2, 1))])
        def fail(label):
            if label == 'publish':
                raise OSError('publication boundary')
        self.store.before_commit = fail
        with self.assertRaises(OSError):
            self.store.analyze('t')
        self.assertEqual(self.store.read_report('t')['status'], 'pending')
        self.assertIsNone(self.store.read_report('t')['report'])
        self.assertIsNone(self.store.read_report('t')['receipt'])
        self.store.before_commit = None
        self.assertEqual(self.store.analyze('t')['report']['mean'], [9])

    def test_maintenance_atomicity(self):
        revision = self.revision()
        def fail(connection):
            connection.execute("UPDATE metadata SET value='2' WHERE key='version'")
            connection.execute('DELETE FROM heads')
            raise RuntimeError('maintenance interrupted')
        with self.assertRaises(RuntimeError):
            self.store.maintenance(fail)
        self.assertEqual(self.store.schema_version, 1)
        self.assertEqual(self.store.head('sensor'), revision)
