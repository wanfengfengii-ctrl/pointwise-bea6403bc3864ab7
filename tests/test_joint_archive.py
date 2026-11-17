"""Archive behavior for calibration revisions and fixed joint tasks."""
import tempfile
import unittest
from fractions import Fraction as F
from pathlib import Path
from trend import Store, Conflict, Invalid, Unknown, Inconsistent
from .support import DIFFUSE


PROPER = {'initial': [[0, 1], [0, 0]], 'process': [0, 0]}
FIXED = {'initial': [[0, 0], [0, 0]], 'process': [0, 0]}


class CalibrationCase(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.addCleanup(self.store.close)

    def test_acceptance_replay_head_and_independent_copy(self):
        first = self.store.apply_calibration('sensor', 'cal-1', '2/4', 4)
        self.assertEqual(first, {'request': 'cal-1', 'calibration': 'sensor',
                                 'calibration_revision': 1})
        replay = self.store.apply_calibration('sensor', 'cal-1', F(1, 2), '4')
        self.assertEqual(replay, first)
        second = self.store.apply_calibration('sensor', 'cal-2', 3, 0)['calibration_revision']
        self.assertEqual(second, 2)
        self.assertEqual(self.store.calibration_head('sensor'), 2)
        self.assertEqual(self.store.calibration_revision(1), {
            'calibration': 'sensor', 'calibration_revision': 1,
            'mean': '1/2', 'variance': '4'})
        self.assertEqual(
            self.store.calibration_revision(1)['calibration_revision'], 1)
        # Revision numbering is an identity space separate from series revisions.
        series_revision = self.store.apply(
            'station', 'req-1', DIFFUSE, [[0, 1, 0]])['revision']
        self.assertEqual(series_revision, 1)
        self.assertEqual(self.store.calibration_head('sensor'), 2)

    def test_calibration_conflict_keeps_head(self):
        self.store.apply_calibration('sensor', 'cal-1', 0, 4)
        with self.assertRaises(Conflict):
            self.store.apply_calibration('other', 'cal-1', 1, 4)
        with self.assertRaises(Conflict):
            self.store.apply_calibration('sensor', 'cal-1', 0, 5)
        self.assertEqual(self.store.calibration_head('sensor'), 1)
        self.assertEqual(self.store.connection.execute(
            'SELECT count(*) FROM calibration_revisions').fetchone()[0], 1)

    def test_calibration_invalid_and_unknown(self):
        for mean, variance in [(1.0, 1), (True, 1), (0, -1), (0, 1.5),
                               ('nope', 1)]:
            with self.assertRaises(Invalid):
                self.store.apply_calibration('sensor', 'r' + str(variance),
                                             mean, variance)
        with self.assertRaises(Invalid):
            self.store.apply_calibration('sensor', 'r-bool', 0, False)
        with self.assertRaises(Invalid):
            self.store.apply_calibration('', 'r', 0, 1)
        with self.assertRaises(Unknown):
            self.store.calibration_head('missing')
        with self.assertRaises(Unknown):
            self.store.calibration_revision(99)
        with self.assertRaises(Invalid):
            self.store.calibration_revision(1.5)
        self.assertEqual(self.store.connection.execute(
            'SELECT count(*) FROM calibration_revisions').fetchone()[0], 0)

    def test_calibration_commit_failure_rolls_back(self):
        def fail(label):
            if label == 'apply_calibration':
                raise OSError('calibration boundary')
        self.store.before_commit = fail
        with self.assertRaises(OSError):
            self.store.apply_calibration('sensor', 'cal-1', 0, 4)
        self.store.before_commit = None
        with self.assertRaises(Unknown):
            self.store.calibration_head('sensor')
        self.assertEqual(self.store.connection.execute(
            'SELECT count(*) FROM calibration_receipts').fetchone()[0], 0)


class JointTaskCase(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.addCleanup(self.store.close)
        self.cal = self.store.apply_calibration(
            'sensor', 'cal-1', 1, 4)['calibration_revision']
        self.rev_a = self.store.apply(
            'a', 'a-1', PROPER, [[0, 5, 1]])['revision']
        self.rev_b = self.store.apply(
            'b', 'b-1', PROPER, [[0, 7, 1]])['revision']

    def binding(self, bid='a', revision=None, prefix=1, loading=1):
        return {'id': bid, 'revision': self.rev_a if revision is None else revision,
                'prefix': prefix, 'loading': loading}

    def create(self, name='joint', bindings=None, queries=()):
        return self.store.create_joint_task(
            name, self.cal,
            [self.binding('a'), self.binding('b', self.rev_b)]
            if bindings is None else bindings, list(queries))

    def test_source_structure_and_canonical_strings(self):
        task = self.create(queries=[
            {'id': 'q', 'terms': [['a', 0, '2/4'], ['b', 1, -1]]}])
        self.assertEqual(task['status'], 'pending')
        self.assertIsNone(task['error'])
        self.assertEqual(task['calibration'], {
            'calibration': 'sensor', 'calibration_revision': self.cal,
            'mean': '1', 'variance': '4'})
        self.assertEqual(task['bindings'], [
            {'id': 'a', 'series': 'a', 'revision': self.rev_a,
             'prefix': 1, 'loading': '1'},
            {'id': 'b', 'series': 'b', 'revision': self.rev_b,
             'prefix': 1, 'loading': '1'}])
        self.assertEqual(task['queries'], [
            {'id': 'q', 'terms': [['a', 0, '1/2'], ['b', 1, '-1']]}])
        self.assertEqual(self.store.joint_task('joint'), task)

    def test_idempotent_replay_and_binding_conflict(self):
        task = self.create()
        self.assertEqual(self.create(), task)
        with self.assertRaises(Conflict):
            self.store.create_joint_task(
                'joint', self.cal,
                [self.binding('a', loading=2), self.binding('b', self.rev_b)], [])
        other_cal = self.store.apply_calibration(
            'sensor', 'cal-2', 0, 4)['calibration_revision']
        with self.assertRaises(Conflict):
            self.store.create_joint_task('joint', other_cal,
                                         [self.binding('a'),
                                          self.binding('b', self.rev_b)], [])
        self.assertEqual(self.store.joint_task('joint'), task)

    def test_unknown_references(self):
        with self.assertRaises(Unknown):
            self.store.create_joint_task('t', 99, [self.binding()], [])
        with self.assertRaises(Unknown):
            self.store.create_joint_task(
                't', self.cal,
                [self.binding('a', revision=99)], [])
        with self.assertRaises(Unknown):
            self.store.create_joint_task(
                't', self.cal, [self.binding('a')],
                [{'id': 'q', 'terms': [['missing', 0, 1]]}])
        self.assertEqual(self.store.connection.execute(
            'SELECT count(*) FROM joint_tasks').fetchone()[0], 0)

    def test_invalid_shapes_and_limits(self):
        def expect(bindings, queries=()):
            with self.assertRaises(Invalid):
                self.store.create_joint_task('t', self.cal, bindings, queries)
        expect([])
        expect([self.binding(chr(ord('a') + i),
                             self.rev_a if i == 0 else self.rev_b,
                             1, 1) for i in range(5)])
        # Same series through two bindings.
        expect([self.binding('a'), self.binding('a2', self.rev_a)])
        # Duplicate binding id.
        expect([self.binding('a'), self.binding('a', self.rev_b)])
        # Prefix beyond the eight-row cap and beyond the revision rows.
        expect([self.binding('a', prefix=9)])
        expect([self.binding('a', prefix=2)])
        # Malformed binding and query payloads.
        expect([{'id': 'a', 'revision': self.rev_a, 'prefix': 1}])
        expect([self.binding('a', loading=1.5)])
        expect([self.binding('a', prefix=True)])
        expect([self.binding('a', revision=1.0)], [])
        with self.assertRaises(Invalid):
            self.store.create_joint_task(
                'bad-time', self.cal, [self.binding('a')],
                [{'id': 'q', 'terms': [['a', 9, 1]]}])
        with self.assertRaises(Invalid):
            self.store.create_joint_task(
                'dup-query', self.cal, [self.binding('a')],
                [{'id': 'q', 'terms': [['a', 0, 1]]},
                 {'id': 'q', 'terms': [['a', 1, 1]]}])
        with self.assertRaises(Invalid):
            self.store.create_joint_task(
                'many', self.cal, [self.binding('a')],
                [{'id': 'q%d' % i, 'terms': []} for i in range(13)])
        self.assertEqual(self.store.connection.execute(
            'SELECT count(*) FROM joint_tasks').fetchone()[0], 0)

    def test_selected_times_outside_window_rejected(self):
        rev = self.store.apply(
            'late', 'late-req', DIFFUSE, [[9, 1, 0]])['revision']
        with self.assertRaises(Invalid):
            self.store.create_joint_task(
                'late', self.cal,
                [self.binding('a', revision=rev, prefix=1)], [])
        # Unselected rows beyond t=8 are tolerated.
        task = self.store.create_joint_task(
            'late-ok', self.cal,
            [self.binding('a', revision=rev, prefix=0)], [])
        self.assertEqual(task['bindings'][0]['prefix'], 0)

    def test_zero_coefficient_still_validates_binding_and_time(self):
        with self.assertRaises(Unknown):
            self.store.create_joint_task(
                't', self.cal, [self.binding('a')],
                [{'id': 'q', 'terms': [['missing', 0, 0]]}])
        with self.assertRaises(Invalid):
            self.store.create_joint_task(
                't', self.cal, [self.binding('a')],
                [{'id': 'q', 'terms': [['a', 9, 0]]}])

    def test_task_identity_space_separate_from_legacy_tasks(self):
        legacy_rev = self.rev_a
        self.store.create_task('same-name', legacy_rev, 1,
                               [{'id': 'x', 'terms': [[0, 1]]}])
        joint = self.create('same-name')
        self.assertEqual(joint['task'], 'same-name')
        self.assertEqual(self.store.task('same-name')['revision'], legacy_rev)
        with self.assertRaises(Unknown):
            self.store.read_joint_report('absent')

    def test_creation_rollback_on_commit_failure(self):
        def fail(label):
            if label == 'create_joint_task':
                raise OSError('joint task boundary')
        self.store.before_commit = fail
        with self.assertRaises(OSError):
            self.create()
        self.store.before_commit = None
        with self.assertRaises(Unknown):
            self.store.joint_task('joint')


class JointFreezeCase(unittest.TestCase):
    def build(self, path):
        store = Store(path)
        cal = store.apply_calibration('sensor', 'cal-1', 0, 4)['calibration_revision']
        rev_a = store.apply('a', 'a-1', DIFFUSE, [[0, 5, 0]])['revision']
        rev_b = store.apply('b', 'b-1', DIFFUSE, [[0, 7, 0]])['revision']
        store.create_joint_task('frozen', cal, [
            {'id': 'a', 'revision': rev_a, 'prefix': 1, 'loading': 1},
            {'id': 'b', 'revision': rev_b, 'prefix': 1, 'loading': 1}],
            [{'id': 'difference',
              'terms': [['a', 0, 1], ['b', 0, -1]]}])
        store.create_joint_task('done-task', cal, [
            {'id': 'a', 'revision': rev_a, 'prefix': 1, 'loading': 1},
            {'id': 'b', 'revision': rev_b, 'prefix': 1, 'loading': 1}],
            [{'id': 'a0', 'terms': [['a', 0, 1]]}])
        done = store.analyze_joint('done-task')
        return store, done

    def test_corrections_and_reopen_do_not_rebind_old_tasks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'joint.sqlite'
            store, done = self.build(path)
            # Corrections after the joint tasks were frozen.
            new_cal = store.apply_calibration(
                'sensor', 'cal-2', 100, 1)['calibration_revision']
            new_a = store.apply('a', 'a-2', DIFFUSE, [[0, 50, 0]])['revision']
            new_b = store.apply('b', 'b-2', DIFFUSE, [[0, 70, 0]])['revision']
            store.close()
            with Store(path) as reopened:
                self.assertEqual(reopened.calibration_head('sensor'), new_cal)
                self.assertEqual(reopened.head('a'), new_a)
                self.assertEqual(reopened.head('b'), new_b)
                pending = reopened.joint_task('frozen')
                self.assertEqual(
                    pending['calibration']['calibration_revision'], 1)
                self.assertEqual(
                    [b['revision'] for b in pending['bindings']], [1, 2])
                result = reopened.analyze_joint('frozen')['report']
                # Frozen inputs: levels 5 and 7 share one Z; difference is -2.
                self.assertEqual(result['mean'], [F(-2)])
                self.assertEqual(result['covariance'], [[F(0)]])
                self.assertEqual(reopened.read_joint_report('done-task'), done)
                # New tasks may bind the new corrections.
                reopened.create_joint_task('fresh', new_cal, [
                    {'id': 'a', 'revision': new_a, 'prefix': 1, 'loading': 1},
                    {'id': 'b', 'revision': new_b, 'prefix': 1, 'loading': 1}],
                    [{'id': 'difference',
                      'terms': [['a', 0, 1], ['b', 0, -1]]}])
                fresh = reopened.analyze_joint('fresh')['report']
                self.assertEqual(fresh['mean'], [F(-20)])

    def test_pending_persists_and_error_task_re_raises_after_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'joint.sqlite'
            store, _ = self.build(path)
            store.create_joint_task('contradiction', 1, [
                {'id': 'a', 'revision':
                 store.apply('c', 'c-1', FIXED, [[0, 5, 0]])['revision'],
                 'prefix': 1, 'loading': 1},
                {'id': 'b', 'revision':
                 store.apply('d', 'd-1', FIXED, [[0, 7, 0]])['revision'],
                 'prefix': 1, 'loading': 1}], [])
            with self.assertRaises(Inconsistent):
                store.analyze_joint('contradiction')
            store.close()
            with Store(path) as reopened:
                self.assertEqual(
                    reopened.joint_task('frozen')['status'], 'pending')
                with self.assertRaises(Inconsistent):
                    reopened.analyze_joint('contradiction')
                read = reopened.read_joint_report('contradiction')
                self.assertEqual(read['status'], 'error')
                self.assertTrue(read['error'])
                self.assertIsNone(read['report'])
                self.assertEqual(read['receipt']['status'], 'error')


class JointIsolationCase(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.addCleanup(self.store.close)
        self.cal = self.store.apply_calibration(
            'sensor', 'cal-1', 0, 4)['calibration_revision']
        self.rev = self.store.apply(
            'a', 'a-1', PROPER, [[0, 5, 1]])['revision']

    def test_input_and_return_mutation_cannot_change_archive(self):
        bindings = [{'id': 'a', 'revision': self.rev,
                     'prefix': 1, 'loading': 1}]
        queries = [{'id': 'q', 'terms': [['a', 0, 1]]}]
        input_snapshot = [dict(b) for b in bindings]
        created = self.store.create_joint_task('joint', self.cal,
                                               bindings, queries)
        bindings[0]['loading'] = 99
        bindings.append({'id': 'b', 'revision': self.rev,
                         'prefix': 0, 'loading': 1})
        queries[0]['terms'][0] = ['a', 1, 1]
        stored = self.store.joint_task('joint')
        self.assertEqual(stored, created)
        self.assertEqual(stored['bindings'][0]['loading'], '1')
        self.assertEqual(len(stored['bindings']), 1)
        created['bindings'][0]['loading'] = '999'
        created['queries'][0]['terms'].append(['a', 2, 1])
        again = self.store.joint_task('joint')
        self.assertEqual(again['bindings'][0]['loading'], '1')
        self.assertEqual(len(again['queries'][0]['terms']), 1)
        self.assertEqual(input_snapshot[0]['loading'], 1)
        result = self.store.analyze_joint('joint')
        result['report']['mean'][0] = F(12345)
        result['source']['bindings'][0]['id'] = 'changed'
        reread = self.store.read_joint_report('joint')
        self.assertNotEqual(reread['report']['mean'][0], F(12345))
        self.assertEqual(reread['source']['bindings'][0]['id'], 'a')

    def test_publish_failure_leaves_pending_and_retryable(self):
        self.store.create_joint_task('joint', self.cal, [
            {'id': 'a', 'revision': self.rev, 'prefix': 1, 'loading': 1}],
            [{'id': 'q', 'terms': [['a', 0, 1]]}])
        def fail(label):
            if label == 'publish_joint':
                raise OSError('joint publish boundary')
        self.store.before_commit = fail
        with self.assertRaises(OSError):
            self.store.analyze_joint('joint')
        self.store.before_commit = None
        read = self.store.read_joint_report('joint')
        self.assertEqual(read['status'], 'pending')
        self.assertIsNone(read['report'])
        self.assertIsNone(read['receipt'])
        self.assertEqual(self.store.connection.execute(
            'SELECT count(*) FROM joint_reports').fetchone()[0], 0)
        self.assertEqual(self.store.connection.execute(
            'SELECT count(*) FROM joint_task_receipts').fetchone()[0], 0)
        result = self.store.analyze_joint('joint')
        self.assertEqual(result['status'], 'done')
        self.assertEqual(result['receipt'], {
            'task': 'joint', 'status': 'done',
            'receipt': 'joint-analysis:joint'})
        self.assertEqual(self.store.analyze_joint('joint'), result)

    def test_storage_error_during_publish_is_not_inconsistent(self):
        self.store.create_joint_task('joint', self.cal, [
            {'id': 'a', 'revision': self.rev, 'prefix': 1, 'loading': 1}], [])
        def fail(label):
            if label == 'publish_joint':
                raise OSError('storage down')
        self.store.before_commit = fail
        with self.assertRaises(OSError):
            self.store.analyze_joint('joint')
        self.assertEqual(
            self.store.read_joint_report('joint')['status'], 'pending')


if __name__ == '__main__':
    unittest.main()
