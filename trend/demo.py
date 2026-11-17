"""Revisions, fixed tasks, diffuse results, and durable report retrieval.

The second phase builds a shared-calibration joint archive, registers joint
tasks before any correction, applies calibration and series corrections,
closes and reopens the database, and only then executes the old pending joint
task: the executed report must still reflect the frozen original bindings,
while a new task is free to use the corrected revisions.
"""
import tempfile
from fractions import Fraction
from pathlib import Path
from .db import Store
from .samples import build
from .codec import dumps


def _joint_demonstration(path):
    with Store(path) as store:
        diffuse = {'initial': [None, None], 'process': [0, 0]}
        proper = {'initial': [[0, 1], [0, 0]], 'process': [0, 0]}
        calibration = store.apply_calibration(
            'sensor', 'cal-v1', 0, 4)['calibration_revision']
        rev_a = store.apply(
            'station-a', 'a-v1', diffuse, [[0, 5, 0]])['revision']
        rev_b = store.apply(
            'station-b', 'b-v1', diffuse, [[0, 7, 0]])['revision']
        bindings = [
            {'id': 'a', 'revision': rev_a, 'prefix': 1, 'loading': 1},
            {'id': 'b', 'revision': rev_b, 'prefix': 1, 'loading': 1}]
        queries = [
            {'id': 'a-level', 'terms': [['a', 0, 1]]},
            {'id': 'b-level', 'terms': [['b', 0, 1]]},
            {'id': 'difference',
             'terms': [['a', 0, 1], ['b', 0, -1]]},
            {'id': 'a-future', 'terms': [['a', 1, 1]]},
            {'id': 'a-curvature',
             'terms': [['a', 2, 1], ['a', 1, -2], ['a', 0, 1]]}]
        store.create_joint_task('joint-frozen', calibration, bindings, queries)
        # A second joint task with a different loading and zero-variance Z;
        # deterministic but compatible redundancy (two exact rows per station
        # pinning one level) must be accepted.
        fixed_c = {'initial': [[3, 0], [0, 0]], 'process': [0, 0]}
        fixed_d = {'initial': [[5, 0], [0, 0]], 'process': [0, 0]}
        exact_cal = store.apply_calibration(
            'gauge', 'gauge-v1', 2, 0)['calibration_revision']
        rev_c = store.apply(
            'station-c', 'c-v1', fixed_c,
            [[0, 5, 0], [1, 5, 0]])['revision']
        rev_d = store.apply(
            'station-d', 'd-v1', fixed_d,
            [[0, 7, 0], [1, 7, 0]])['revision']
        store.create_joint_task('joint-done', exact_cal, [
            {'id': 'c', 'revision': rev_c, 'prefix': 2, 'loading': 1},
            {'id': 'd', 'revision': rev_d, 'prefix': 2, 'loading': 1}],
            [{'id': 'c-level', 'terms': [['c', 0, 1]]}])
        done_before = store.analyze_joint('joint-done')
        assert done_before['report']['mean'] == [Fraction(3)]
        # Corrections registered only after the joint tasks were frozen.
        new_calibration = store.apply_calibration(
            'sensor', 'cal-v2', 100, 1)['calibration_revision']
        new_a = store.apply(
            'station-a', 'a-v2', proper, [[0, 50, 1]])['revision']
        new_b = store.apply(
            'station-b', 'b-v2', proper, [[0, 70, 1]])['revision']
        frozen_source = store.joint_task('joint-frozen')
    with Store(path) as store:
        # Reopened: heads moved on, but the old task keeps its old bindings.
        assert store.calibration_head('sensor') == new_calibration
        assert store.head('station-a') == new_a
        assert store.head('station-b') == new_b
        executed = store.analyze_joint('joint-frozen')
        report = executed['report']
        assert executed['source']['calibration']['calibration_revision'] == 1
        assert [item['status'] for item in report['items']] == \
            ['estimable', 'estimable', 'estimable',
             'unidentified', 'estimable']
        assert report['mean'] == [5, 7, -2, 0]
        assert report['covariance'][0][0] == Fraction(4)
        assert report['covariance'][2] == [Fraction(0)] * 4
        # The earlier done report is byte-stable across the correction/reopen.
        assert store.read_joint_report('joint-done') == done_before
        # A new joint task is free to bind the corrected revisions.
        store.create_joint_task('joint-corrected', new_calibration, [
            {'id': 'a', 'revision': new_a, 'prefix': 1, 'loading': 1},
            {'id': 'b', 'revision': new_b, 'prefix': 1, 'loading': 1}],
            [{'id': 'difference',
              'terms': [['a', 0, 1], ['b', 0, -1]]}])
        corrected = store.analyze_joint('joint-corrected')['report']
        # Corrected readings (50, 70) and corrected priors give a different
        # difference; only the old frozen task keeps its original inputs.
        assert corrected['mean'] == [Fraction(-10)]
        return {
            'frozen_source': executed['source'],
            'frozen_report': report,
            'done_report': store.read_joint_report('joint-done')['report'],
            'corrected_report': corrected}


def main():
    with tempfile.TemporaryDirectory(prefix='trend-demo-') as directory:
        path = Path(directory) / 'archive.sqlite'
        with Store(path) as store:
            manifest = build(store)
            old = store.analyze('one-reading')
            assert old['report']['items'][0]['status'] == 'unidentified'
            assert old['report']['mean'] == [0]
            assert store.analyze('two-readings')['report']['mean'] == [9, 11]
            assert store.read_report('contradiction')['report'] is None
        joint = _joint_demonstration(path)
        with Store(path) as store:
            assert store.read_report('one-reading') == old
            assert store.analyze('frozen-pending')['report']['estimable'] == []
            print(dumps({
                'archive_version': store.schema_version,
                'reports': {name: store.read_report(name)
                            for name in manifest['tasks']},
                'joint': joint}))


if __name__ == '__main__':
    main()
