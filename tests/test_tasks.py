import tempfile
from pathlib import Path
from trend import Store, Conflict, Invalid, Unknown
from .support import ArchiveCase, DIFFUSE, query


class TestRevisionTasks(ArchiveCase):
    def test_fixed_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'archive.sqlite'
            with Store(path) as store:
                first = store.apply('s', 'first', DIFFUSE, [[0, 5, 0], [1, 7, 0]])['revision']
                store.create_task('old', first, 2, [query('x2', (2, 1))])
                old = store.analyze('old')
                second = store.apply('s', 'second', DIFFUSE, [[0, 5, 0], [1, 8, 0]])['revision']
                store.create_task('new', second, 2, [query('x2', (2, 1))])
                self.assertEqual(store.analyze('new')['report']['mean'], [11])
                self.assertEqual(store.analyze('old'), old)
                store.create_task('old-pending', first, 2, [query('x2', (2, 1))])
            with Store(path) as store:
                self.assertEqual(store.head('s'), second)
                self.assertEqual(store.read_report('old'), old)
                self.assertEqual(store.analyze('old-pending')['report']['mean'], [9])
                self.assertEqual(store.read_report('old')['source']['revision'], first)
                self.assertEqual(store.read_report('new')['source']['revision'], second)

    def test_invalid_binding(self):
        revision = self.revision(observations=[[0, 5, 0]])
        with self.assertRaises(Unknown):
            self.store.create_task('unknown', revision + 100, 0, [])
        with self.assertRaises(Invalid):
            self.store.create_task('overflow', revision, 2, [])
        self.assertEqual(self.store.connection.execute('SELECT count(*) FROM tasks').fetchone()[0], 0)

    def test_identity_and_order(self):
        revision = self.revision(observations=[[0, 5, 0]])
        queries = [query('b', (0, 2)), query('a', (0, 1))]
        task = self.store.create_task('t', revision, 1, queries)
        self.assertEqual(self.store.create_task('t', revision, 1, queries), task)
        with self.assertRaises(Conflict):
            self.store.create_task('t', revision, 1, list(reversed(queries)))
        with self.assertRaises(Invalid):
            self.store.create_task('dup', revision, 1, [query('a'), query('a')])
        result = self.store.analyze('t')['report']
        self.assertEqual(result['estimable'], ['b', 'a'])
        self.assertEqual(result['mean'], [10, 5])

    def test_task_creation_rollback(self):
        revision = self.revision()
        def fail(label):
            if label == 'create_task':
                raise OSError('task boundary')
        self.store.before_commit = fail
        with self.assertRaises(OSError):
            self.store.create_task('t', revision, 0, [])
        self.store.before_commit = None
        with self.assertRaises(Unknown):
            self.store.task('t')

    def test_memory_revision_binding(self):
        first = self.revision(observations=[[0, 5, 0], [1, 7, 0]])
        self.store.create_task('old', first, 2, [query('x2', (2, 1))])
        second = self.revision(observations=[[0, 5, 0], [1, 8, 0]], request='new')
        self.assertNotEqual(first, second)
        self.assertEqual(self.store.analyze('old')['report']['mean'], [9])
