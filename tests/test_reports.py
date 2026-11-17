from fractions import Fraction as F
from trend import Inconsistent, Unknown
from .support import ArchiveCase, DIFFUSE, query


class TestTrendReports(ArchiveCase):
    def test_proper_joint(self):
        model = {'initial': [[2, 4], [1, 1]], 'process': [1, 0]}
        revision = self.revision(model)
        result = self.run_task(revision, 0, [query('one', (1, 1)), query('two', (2, 1))])
        self.assertEqual(result, {
            'items': [{'id': 'one', 'status': 'estimable'},
                      {'id': 'two', 'status': 'estimable'}],
            'estimable': ['one', 'two'], 'mean': [F(3), F(4)],
            'covariance': [[F(6), F(7)], [F(7), F(10)]]})
        self.assertIsInstance(result['covariance'][0][1], F)

    def test_diffuse_combination(self):
        revision = self.revision(observations=[[0, 5, 0]])
        result = self.run_task(revision, 1, [
            query('future', (2, 1)),
            query('curvature', (2, 1), (1, -2), (0, 1)),
            query('level', (0, 1)), query('twice', (0, 2))])
        self.assertEqual([x['status'] for x in result['items']],
                         ['unidentified', 'estimable', 'estimable', 'estimable'])
        self.assertEqual(result['estimable'], ['curvature', 'level', 'twice'])
        self.assertEqual(result['mean'], [0, 5, 10])
        self.assertEqual(result['covariance'], [[0, 0, 0]] * 3)

    def test_missing_and_identification(self):
        revision = self.revision(observations=[[0, 5, 0], [1, None, 0], [2, 9, 2]])
        queries = [query('future', (3, 1)), query('halfway', (1, 1))]
        before = self.run_task(revision, 2, queries, 'before')
        self.assertEqual(before['estimable'], [])
        self.assertEqual(before['covariance'], [])
        after = self.run_task(revision, 3, queries, 'after')
        self.assertEqual(after['mean'], [11, 7])
        self.assertEqual(after['covariance'], [[F(9, 2), F(3, 2)],
                                              [F(3, 2), F(1, 2)]])
        exact = self.revision(observations=[[0, 5, 0], [1, 7, 0]], request='exact')
        self.assertEqual(self.run_task(exact, 2, [query('x2', (2, 1))], 'exact')['mean'], [9])

    def test_inconsistent_exact(self):
        revision = self.revision(observations=[[0, 5, 0], [1, 7, 0], [2, 10, 0]])
        self.store.create_task('bad', revision, 3, [query('first', (0, 1)),
                                                   query('last', (3, 1))])
        with self.assertRaises(Inconsistent):
            self.store.analyze('bad')
        result = self.store.read_report('bad')
        self.assertEqual(result['status'], 'error')
        self.assertIsNone(result['report'])
        self.assertEqual(result['receipt']['status'], 'error')
        self.assertEqual(self.store.connection.execute('SELECT count(*) FROM reports').fetchone()[0], 0)
        with self.assertRaises(Inconsistent):
            self.store.analyze('bad')
        self.assertEqual(self.store.read_report('bad'), result)

    def test_mixed_initial_process_and_cross_covariance(self):
        model = {'initial': [None, [1, 2]], 'process': [1, 1]}
        revision = self.revision(model, [[0, 5, 1], [1, None, 0], [2, 9, 2]])
        result = self.run_task(revision, 3, [query('x2', (2, 1)), query('x3', (3, 1))])
        self.assertEqual(result['mean'], [F(61, 7), F(73, 7)])
        self.assertEqual(result['covariance'], [[F(12, 7), F(17, 7)],
                                              [F(17, 7), F(89, 14)]])

    def test_no_observations_and_cancelling_terms(self):
        revision = self.revision()
        result = self.run_task(revision, 0, [
            query('point', (0, 1)), query('cancel', (4, 1), (4, -1)),
            query('curvature', (2, 1), (1, -2), (0, 1)), query('empty')])
        self.assertEqual(result['estimable'], ['cancel', 'curvature', 'empty'])
        self.assertEqual(result['mean'], [0, 0, 0])
        self.assertEqual(result['covariance'], [[0, 0, 0]] * 3)

    def test_empty_queries_still_validate_observations(self):
        revision = self.revision(observations=[[0, 5, 0], [1, 7, 0], [2, 10, 0]])
        self.store.create_task('empty', revision, 3, [])
        with self.assertRaises(Inconsistent):
            self.store.analyze('empty')
        self.assertIsNone(self.store.read_report('empty')['report'])

    def test_pending_and_unknown(self):
        revision = self.revision()
        self.store.create_task('pending', revision, 0, [])
        self.assertEqual(self.store.read_report('pending')['status'], 'pending')
        self.assertIsNone(self.store.read_report('pending')['receipt'])
        with self.assertRaises(Unknown):
            self.store.read_report('absent')

    def test_missing_is_not_zero(self):
        model = {'initial': [[5, 0], [0, 0]], 'process': [0, 0]}
        revision = self.revision(model, [[0, None, 0], [1, 0, 0]])
        result = self.run_task(revision, 1, [query('x1', (1, 1))], 'missing')
        self.assertEqual(result['mean'], [5])
        self.store.create_task('zero', revision, 2, [])
        with self.assertRaises(Inconsistent):
            self.store.analyze('zero')

    def test_diffuse_process_combinations_keep_negative_cross_covariance(self):
        model = {'initial': [None, None], 'process': [1, 1]}
        revision = self.revision(model, [[0, 5, 0]])
        result = self.run_task(revision, 1, [
            query('point', (3, 1)),
            query('c2', (2, 1), (1, -2), (0, 1)),
            query('c3', (3, 1), (2, -2), (1, 1))])
        self.assertEqual(result['items'][0]['status'], 'unidentified')
        self.assertEqual(result['estimable'], ['c2', 'c3'])
        self.assertEqual(result['mean'], [0, 0])
        self.assertEqual(result['covariance'], [[3, -1], [-1, 3]])
