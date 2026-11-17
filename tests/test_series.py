from fractions import Fraction
from trend import Conflict, Invalid, Unknown
from .support import ArchiveCase, DIFFUSE


class TestSeriesArchive(ArchiveCase):
    def test_invalid_revision(self):
        revision = self.revision(observations=[[0, 5, 0]])
        for model, observations in [
            (DIFFUSE, [[2, 3, 0], [1, 2, 0]]),
            (DIFFUSE, [[0, 3, -1]]),
            ({'initial': [None, [0, -1]], 'process': [0, 0]}, []),
            ({'initial': [None, None], 'process': [-1, 0]}, [])]:
            with self.assertRaises(Invalid):
                self.store.apply('sensor', 'invalid', model, observations)
        self.assertEqual(self.store.head('sensor'), revision)
        self.assertEqual(self.store.connection.execute(
            'SELECT count(*) FROM apply_receipts').fetchone()[0], 1)
        self.assertEqual(self.store.connection.execute(
            'SELECT count(*) FROM revisions').fetchone()[0], 1)

    def test_replay_conflict_and_no_head_rewind(self):
        first = self.store.apply('s', 'a', DIFFUSE, [[0, '2/4', 0]])
        second = self.store.apply('s', 'b', DIFFUSE, [[0, 8, 0]])
        replay = self.store.apply('s', 'a', DIFFUSE, [[0, Fraction(1, 2), 0]])
        self.assertEqual(replay, first)
        self.assertEqual(self.store.head('s'), second['revision'])
        with self.assertRaises(Conflict):
            self.store.apply('other', 'a', DIFFUSE, [[0, '1/2', 0]])
        self.assertEqual(self.store.revision(first['revision'])['observations'], [[0, '1/2', '0']])

    def test_strict_exact_inputs(self):
        for observations in [[[True, 1, 0]], [[0, 1.0, 0]],
                             [[0, 1, 0], [0, 2, 0]], [[-1, 1, 0]]]:
            with self.assertRaises(Invalid):
                self.store.apply('s', 'bad', DIFFUSE, observations)
        with self.assertRaises(Unknown):
            self.store.head('s')

    def test_real_old_state_is_archived(self):
        revision = self.revision()
        state = self.store.revision(revision)['sdk1_state']
        self.assertEqual(state['format'], 'trend1.initial/1')
        self.assertEqual(state['covariance'][0][0], [['0', '1'], ['1']])
        self.assertEqual(self.store.schema_version, 1)

    def test_apply_transaction_failure(self):
        revision = self.revision()
        def fail(label):
            if label == 'apply':
                raise OSError('acceptance boundary')
        self.store.before_commit = fail
        with self.assertRaises(OSError):
            self.store.apply('sensor', 'new', DIFFUSE, [[0, 9, 0]])
        self.store.before_commit = None
        self.assertEqual(self.store.head('sensor'), revision)
        self.assertEqual(self.store.connection.execute(
            'SELECT count(*) FROM apply_receipts').fetchone()[0], 1)
