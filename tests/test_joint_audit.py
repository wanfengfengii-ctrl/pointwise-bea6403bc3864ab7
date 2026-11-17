"""Independent joint audit: hand-worked data plus a primitive-noise oracle.

The oracle below rebuilds every joint problem from independent primitive
random variables (initial directions, per-step innovations, one shared Z,
per-row measurement noise) through vendor.gaussian2.  It shares no code with
trend.joint_math, so matching full means and complete covariance matrices is
an independent numeric check rather than a self-consistency test.
"""
import unittest
from fractions import Fraction as F
from trend import Store, Inconsistent, Invalid, Unknown, Conflict
from vendor.gaussian2 import Normal
from joint_examples import examples


class JointCase(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.addCleanup(self.store.close)

    def apply_calibration(self, name='sensor', request='cal-1',
                          mean=0, variance=4):
        return self.store.apply_calibration(
            name, request, mean, variance)['calibration_revision']

    def apply_station(self, series, model, observations, request=None):
        return self.store.apply(
            series, request or series + '-req', model,
            observations)['revision']

    def build_task(self, name, calibration_revision, specs, queries=()):
        """specs: (binding_id, revision, prefix, loading) tuples in order."""
        bindings = [{'id': bid, 'revision': rev, 'prefix': prefix,
                     'loading': loading}
                    for bid, rev, prefix, loading in specs]
        self.store.create_joint_task(
            name, calibration_revision, bindings, list(queries))


# --------------------------------------------------------------------------
# Independent primitive-noise oracle
# --------------------------------------------------------------------------

HORIZON = 8


def _level_rows(model):
    """Level(0..8) as affine rows over one station's 18 primitive variables."""
    rows = []
    for t in range(HORIZON + 1):
        row = [F(1), F(t)] + [F(0)] * (2 * HORIZON)
        for k in range(1, t + 1):
            row[2 + 2 * (k - 1)] = F(1)
            row[3 + 2 * (k - 1)] = F(t - k)
        rows.append(row)
    return rows


def _primitive_cov(model, diffuse_scale):
    """Diagonal covariance of the station's primitive variables (18 x 18)."""
    diag = []
    for direction in model['initial']:
        diag.append(F(diffuse_scale) if direction is None else F(direction[1]))
    for k in range(1, HORIZON + 1):
        diag.append(F(model['process'][0]))
        diag.append(F(model['process'][1]))
    return [[diag[i] if i == j else F(0) for j in range(len(diag))]
            for i in range(len(diag))]


def _primitive_mean(model):
    return [F(0) if d is None else F(d[0]) for d in model['initial']] + \
        [F(0)] * (2 * HORIZON)


class Oracle:
    def __init__(self, models, calibration, loadings):
        """models/loadings aligned with binding order; calibration = (mu, v)."""
        self.blocks = [_level_rows(m) for m in models]
        mu, variance = calibration
        means, widths = [], []
        cov_blocks = []
        for model in models:
            means.extend(_primitive_mean(model))
            widths.append(2 + 2 * HORIZON)
            cov_blocks.append(_primitive_cov(model, F(10) ** 18))
        self.z_position = len(means)
        means.append(F(mu))
        size = len(means)
        covariance = _block_diagonal(cov_blocks, size - 1)
        for row in covariance:
            row.append(F(0))
        covariance.append([F(0)] * (size - 1) + [F(variance)])
        self.prior = Normal(means, covariance)
        self.widths = widths
        self.loadings = [F(a) for a in loadings]

    def run(self, observations, queries):
        """observations: per binding list of [t, value, noise]; queries: rows."""
        rows, values, noises = [], [], []
        diag = []
        for position, station_rows in enumerate(observations):
            start = sum(self.widths[:position])
            for t, value, noise in station_rows:
                if value is None:
                    continue
                row = [F(0)] * (self.z_position + 1)
                for j, coefficient in enumerate(self.blocks[position][t]):
                    row[start + j] = coefficient
                row[self.z_position] = self.loadings[position]
                rows.append(row)
                values.append(F(value))
                diag.append(F(noise))
        count = len(diag)
        noise = Normal([F(0)] * count,
                       [[diag[i] if i == j else F(0) for j in range(count)]
                        for i in range(count)])
        posterior = self.prior.condition(rows, values, noise)
        query_rows = []
        for terms in queries:
            row = [F(0)] * (self.z_position + 1)
            for binding_position, t, coefficient in terms:
                start = sum(self.widths[:binding_position])
                for j, c in enumerate(self.blocks[binding_position][t]):
                    row[start + j] += F(coefficient) * c
            query_rows.append(row)
        projected = posterior.project(query_rows)
        return projected


def _block_diagonal(blocks, size):
    out = [[F(0) for _ in range(size)] for _ in range(size)]
    offset = 0
    for block in blocks:
        for i, row in enumerate(block):
            for j, value in enumerate(row):
                out[offset + i][offset + j] = value
        offset += len(block)
    return out


def oracle_query_terms(queries, positions):
    return [[(positions[binding_id], t, F(coefficient))
             for binding_id, t, coefficient in query['terms']]
            for query in queries]


class TestJointHandWorked(JointCase):
    def test_all_hand_worked_scenarios(self):
        for scenario in examples():
            with self.subTest(scenario=scenario['name']):
                store = Store()
                self.addCleanup(store.close)
                cal = scenario['calibration']
                cal_rev = store.apply_calibration(
                    cal['calibration'], cal['request'],
                    cal['mean'], cal['variance'])['calibration_revision']
                revisions = {}
                for station in scenario['series']:
                    revisions[station['series']] = store.apply(
                        station['series'], station['request'],
                        station['model'], station['observations'])['revision']
                bindings = []
                for binding in scenario['bindings']:
                    item = dict(binding)
                    item['revision'] = revisions[item.pop('series')]
                    bindings.append(item)
                store.create_joint_task(
                    scenario['name'], cal_rev, bindings, scenario['queries'])
                if 'expected_error' in scenario:
                    with self.assertRaises(Inconsistent):
                        store.analyze_joint(scenario['name'])
                    read = store.read_joint_report(scenario['name'])
                    self.assertEqual(read['status'], 'error')
                    self.assertIsNone(read['report'])
                    self.assertEqual(
                        read['receipt'],
                        {'task': scenario['name'], 'status': 'error',
                         'receipt': 'joint-analysis:' + scenario['name']})
                    with self.assertRaises(Inconsistent):
                        store.analyze_joint(scenario['name'])
                    self.assertEqual(
                        store.read_joint_report(scenario['name']), read)
                    continue
                result = store.analyze_joint(scenario['name'])['report']
                expected = scenario['expected']
                self.assertEqual(result['items'], expected['items'])
                self.assertEqual(result['estimable'], expected['estimable'])
                self.assertEqual(result['mean'], expected['mean'])
                self.assertEqual(result['covariance'], expected['covariance'])
                self.assertTrue(
                    all(isinstance(x, F) for row in result['covariance']
                        for x in row))


PROPER = {'initial': [[0, 1], [0, 0]], 'process': [0, 0]}
PROCESS = {'initial': [[1, 2], [3, 4]], 'process': [F(1, 2), F(2, 3)]}
DIFFUSE = {'initial': [None, None], 'process': [0, 0]}
MIXED = {'initial': [None, [2, 5]], 'process': [1, 0]}


def make_query(name, *terms):
    return {'id': name, 'terms': [list(term) for term in terms]}


class TestJointOracleAudit(JointCase):
    def _oracle_check(self, models, observations, loadings, calibration,
                      query_terms, prefixes=None):
        cal_rev = self.apply_calibration(
            mean=calibration[0], variance=calibration[1])
        specs, positions = [], {}
        for i, (model, rows) in enumerate(zip(models, observations)):
            bid = chr(ord('a') + i)
            positions[bid] = i
            prefix = len(rows) if prefixes is None else prefixes[i]
            rev = self.apply_station(bid, model, rows, request='req-' + bid)
            specs.append((bid, rev, prefix, loadings[i]))
        queries = [make_query('q%d' % i, *terms)
                   for i, terms in enumerate(query_terms)]
        self.build_task('joint', cal_rev, specs, queries)
        actual = self.store.analyze_joint('joint')['report']
        oracle = Oracle(models, calibration, loadings)
        projected = oracle.run(observations,
                               oracle_query_terms(queries, positions))
        self.assertEqual(actual['estimable'],
                         [q['id'] for q in queries])
        self.assertEqual(actual['mean'], list(projected.mean))
        self.assertEqual(actual['covariance'],
                         [list(row) for row in projected.covariance])

    def test_proper_stations_negative_and_zero_loadings(self):
        self._oracle_check(
            [PROPER, PROPER, PROPER],
            [[[0, 5, 1]], [[1, 7, 2]], [[2, 3, 0]]],
            [1, -2, 0], (1, 9),
            [[('a', 0, 1)], [('b', 1, 1), ('a', 0, -1)],
             [('c', 2, 1), ('b', 1, F(1, 2))]])

    def test_process_innovations_and_cross_time(self):
        self._oracle_check(
            [PROCESS, PROPER],
            [[[0, 4, 1], [2, 6, 1]], [[1, 2, F(1, 3)]]],
            [F(1, 2), 3], (-1, 2),
            [[('a', 3, 1)], [('a', 2, 1), ('a', 1, -2), ('a', 0, 1)],
             [('a', 0, 1), ('b', 1, -1)]])

    def test_missing_rows_and_partial_prefixes(self):
        self._oracle_check(
            [PROCESS, PROPER],
            [[[0, 4, 1], [1, None, 0], [2, 6, 1]],
             [[0, 1, 1], [1, None, 2]]],
            [2, 1], (0, 1),
            [[('a', 1, 1)], [('b', 0, 1)],
             [('a', 2, 1), ('b', 1, -1)]],
            prefixes=[3, 1])

    def test_redundant_consistent_deterministic_conditions(self):
        # Repeated exact conditions (an exact row duplicated across another
        # time on a fixed trajectory) carry the same information and are
        # accepted; the shared Z is fully pinned and queried levels are certain.
        self._oracle_check(
            [PROPER, PROPER],
            [[[0, 5, 0], [1, 5, 0]], [[0, 3, 0], [1, 3, 0]]],
            [1, 1], (2, 0),
            [[('a', 0, 1)], [('b', 0, 1)],
             [('a', 0, 1), ('b', 0, -1)]])

    def test_single_binding_loading_zero_breaks_calibration_link(self):
        self._oracle_check(
            [PROPER], [[[0, 5, 1]]], [0], (4, 16),
            [[('a', 0, 1)]])

    def test_empty_queries_still_condition_observations(self):
        cal_rev = self.apply_calibration(mean=0, variance=4)
        fixed = {'initial': [[0, 0], [0, 0]], 'process': [0, 0]}
        rev_a = self.apply_station('a', fixed, [[0, 5, 0]], request='ra')
        rev_b = self.apply_station('b', fixed, [[0, 7, 0]], request='rb')
        self.build_task('joint', cal_rev,
                        [('a', rev_a, 1, 1), ('b', rev_b, 1, 1)], [])
        with self.assertRaises(Inconsistent):
            self.store.analyze_joint('joint')
        self.assertIsNone(
            self.store.read_joint_report('joint')['report'])


class TestDiffuseLimit(JointCase):
    def test_mixed_diffuse_station_deterministic_identities(self):
        cal_rev = self.apply_calibration(mean=1, variance=4)
        rev_a = self.apply_station('a', DIFFUSE, [[0, 5, 0]], request='ra')
        rev_b = self.apply_station('b', MIXED, [[0, 7, 1]], request='rb')
        self.build_task(
            'joint', cal_rev,
            [('a', rev_a, 1, 1), ('b', rev_b, 1, 2)],
            [make_query('level-a', ('a', 0, 1)),
             make_query('future-a', ('a', 1, 1)),
             make_query('curvature', ('a', 2, 1), ('a', 1, -2), ('a', 0, 1)),
             make_query('difference', ('a', 0, 1), ('b', 0, -1)),
             make_query('empty'),
             make_query('cancel', ('a', 1, 1), ('a', 1, -1))])
        report = self.store.analyze_joint('joint')['report']
        statuses = {item['id']: item['status'] for item in report['items']}
        self.assertEqual(statuses['future-a'], 'unidentified')
        self.assertEqual(statuses['level-a'], 'estimable')
        self.assertEqual(statuses['curvature'], 'estimable')
        self.assertEqual(statuses['difference'], 'estimable')
        self.assertEqual(statuses['empty'], 'estimable')
        self.assertEqual(statuses['cancel'], 'estimable')
        values = dict(zip(report['estimable'], report['mean']))
        # Hand derivation: station b gives E[Z|obs]=1+8/21 and E[b0|obs]=26/21.
        # Station a is fully diffuse with an exact reading a0+Z=5, so its level
        # is anchored to the reading: E[a0|obs] = 5 - E[Z|obs] = 76/21 only if
        # a carries a finite prior; under the diffuse limit the reading fixes
        # a0 at 5 - 1 = 4, and the diffuse scale absorbs the residual.
        self.assertEqual(values['level-a'], F(4))
        self.assertEqual(values['curvature'], F(0))
        self.assertEqual(values['empty'], F(0))
        self.assertEqual(values['cancel'], F(0))
        # Deterministic identities have zero full-matrix covariance.
        for name in ('curvature', 'empty', 'cancel'):
            i = report['estimable'].index(name)
            self.assertTrue(all(x == 0 for x in report['covariance'][i]))

    def test_diffuse_limit_matches_large_finite_scale_oracle(self):
        # With a very large finite D the oracle's identified block approaches
        # the exact D->infinity limit of the product kernel.
        cal_rev = self.apply_calibration(mean=0, variance=4)
        rev_a = self.apply_station('a', DIFFUSE, [[0, 5, 0]], request='ra')
        rev_b = self.apply_station('b', DIFFUSE, [[0, 7, 0]], request='rb')
        self.build_task(
            'joint', cal_rev,
            [('a', rev_a, 1, 1), ('b', rev_b, 1, 1)],
            [make_query('a0', ('a', 0, 1)),
             make_query('b0', ('b', 0, 1)),
             make_query('diff', ('a', 0, 1), ('b', 0, -1)),
             make_query('curvature', ('a', 2, 1), ('a', 1, -2), ('a', 0, 1))])
        report = self.store.analyze_joint('joint')['report']
        oracle = Oracle([DIFFUSE, DIFFUSE], (0, 4), [1, 1])
        projected = oracle.run(
            [[[0, 5, 0]], [[0, 7, 0]]],
            oracle_query_terms(
                [make_query('a0', ('a', 0, 1)),
                 make_query('b0', ('b', 0, 1)),
                 make_query('diff', ('a', 0, 1), ('b', 0, -1)),
                 make_query('curvature', ('a', 2, 1), ('a', 1, -2),
                            ('a', 0, 1))],
                {'a': 0, 'b': 1}))
        for got, approximate in zip(report['mean'], projected.mean):
            self.assertLess(abs(float(got - approximate)), 1e-6)
        for i, row in enumerate(report['covariance']):
            for j, got in enumerate(row):
                self.assertLess(
                    abs(float(got - projected.covariance[i][j])), 1e-6)

    def test_diffuse_process_noise_cross_station_limit(self):
        # Both stations diffuse with process innovations; identified
        # combinations (level differences, curvatures, anchored levels) still
        # converge to the exact limit under a huge finite diffuse scale.
        noisy_diffuse = {'initial': [None, None], 'process': [1, 1]}
        cal_rev = self.apply_calibration(mean=2, variance=3)
        rev_a = self.apply_station(
            'a', noisy_diffuse, [[0, 5, 1], [2, 6, 1]], request='ra')
        rev_b = self.apply_station(
            'b', noisy_diffuse, [[1, 7, 2]], request='rb')
        queries = [
            make_query('diff0', ('a', 0, 1), ('b', 0, -1)),
            make_query('curv-a', ('a', 2, 1), ('a', 1, -2), ('a', 0, 1)),
            make_query('a0', ('a', 0, 1)),
            make_query('future', ('a', 8, 1))]
        self.build_task(
            'joint', cal_rev,
            [('a', rev_a, 2, 1), ('b', rev_b, 1, -1)], queries)
        report = self.store.analyze_joint('joint')['report']
        # Only the diffuse t=0 level difference is unidentified; anchored
        # levels stay finite (with finite-variance Z) and propagate forward.
        self.assertEqual(
            [item['status'] for item in report['items']],
            ['unidentified', 'estimable', 'estimable', 'estimable'])
        estimable_indexes = [1, 2, 3]
        oracle = Oracle([noisy_diffuse, noisy_diffuse], (2, 3), [1, -1])
        projected = oracle.run(
            [[[0, 5, 1], [2, 6, 1]], [[1, 7, 2]]],
            oracle_query_terms(queries, {'a': 0, 'b': 1}))
        for column, got in zip(estimable_indexes, report['mean']):
            self.assertLess(abs(float(got - projected.mean[column])), 1e-6)
        for i, row in enumerate(report['covariance']):
            for j, got in enumerate(row):
                self.assertLess(abs(float(
                    got - projected.covariance[estimable_indexes[i]][
                        estimable_indexes[j]])), 1e-6)
