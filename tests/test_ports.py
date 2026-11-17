import unittest
from fractions import Fraction as F
from vendor.gaussian2 import Normal, Inconsistent
from vendor.rational import RF
from vendor import trend1
from trend import codec
from .support import query


class TestNumericalPorts(unittest.TestCase):
    def test_exact_diffuse_scale(self):
        d = RF((0, 1))
        self.assertEqual((d / (d + 1)).limit(), 1)
        self.assertEqual(((d * d - 1) / (d - 1) - d).limit(), 1)
        with self.assertRaises(OverflowError):
            d.limit()
        self.assertEqual(RF.load((d / (d + 1)).dump()).limit(), 1)

    def test_native_affine_and_roundtrip(self):
        state = Normal([2, 1], [[4, 0], [0, 1]])
        noise = Normal([0, 0], [[1, 0], [0, 0]])
        advanced = state.affine([[1, 1], [0, 1]], noise=noise)
        self.assertEqual(advanced.mean, (3, 1))
        self.assertEqual(advanced.covariance, ((6, 1), (1, 1)))
        self.assertEqual(Normal.load(advanced.dump()), advanced)
        projected = advanced.project([[1, 0], [1, 1]])
        self.assertEqual(projected.covariance, ((6, 7), (7, 9)))

    def test_singular_and_correlated_conditioning(self):
        singular = Normal([0, 0], [[1, 1], [1, 1]])
        result = singular.condition([[1, 0], [0, 1], [1, -1]], [3, 3, 0])
        self.assertEqual(result.mean, (3, 3))
        self.assertEqual(result.covariance, ((0, 0), (0, 0)))
        with self.assertRaises(Inconsistent):
            singular.condition([[1, 0], [0, 1]], [3, 4])
        state = Normal([0, 0], [[1, 0], [0, 1]])
        noise = Normal([0, 0], [[1, 1], [1, 1]])
        result = state.condition([[1, 0], [0, 1]], [1, 2], noise)
        self.assertEqual(result.mean, (0, 1))
        self.assertEqual(result.covariance, ((F(1, 3), F(1, 3)),
                                           (F(1, 3), F(1, 3))))

    def test_reject_invalid_normal(self):
        for mean, covariance in [([0], [[-1]]), ([0, 0], [[0, 1], [1, 1]]),
                                 ([0, 0], [[1, 2], [0, 1]]),
                                 ([0, 0], [[1]]), ([0.0], [[1]])]:
            with self.assertRaises(ValueError):
                Normal(mean, covariance)
        with self.assertRaises(ValueError):
            Normal([0], [[1]]).affine([[1, 2]])
        self.assertEqual(Normal([], []).condition([], []).dump()['covariance'], [])

    def test_proper_trajectory_against_primitive_noise_oracle(self):
        # An independent finite-Gaussian construction: primitive initial state
        # and each step's two innovations, projected directly into observations.
        # It does not call SDK1's trajectory/covariance construction.
        horizon = 3
        queries = [query('x3', (3, 1)), query('difference', (3, 1), (1, -1)),
                   query('curvature', (2, 1), (1, -2), (0, 1))]
        for ql, qs, r in [(0, 0, 1), (1, 0, 0), (0, 1, 2),
                          (F(1, 3), F(2, 3), F(1, 2))]:
            with self.subTest(process=(ql, qs), noise=r):
                model = codec.model({'initial': [[2, 4], [1, 1]], 'process': [ql, qs]})
                observations = codec.observations([[0, 3, 1], [1, None, 0], [2, 5, r]])
                variances = [F(4), F(1)] + [F(x) for _ in range(horizon) for x in (ql, qs)]
                n = len(variances)
                primitive = Normal([2, 1] + [0] * (n - 2),
                                   [[variances[i] if i == j else 0 for j in range(n)]
                                    for i in range(n)])
                levels = []
                for t in range(horizon + 1):
                    row = [F(1), F(t)] + [F(0)] * (n - 2)
                    for k in range(1, t + 1):
                        row[2 + 2 * (k - 1)] = 1
                        row[3 + 2 * (k - 1)] = t - k
                    levels.append(row)
                present = [row for row in observations if row[1] is not None]
                noise = Normal([0] * len(present),
                               [[F(row[2]) if i == j else 0
                                 for j in range(len(present))]
                                for i, row in enumerate(present)])
                conditioned = primitive.condition([levels[row[0]] for row in present],
                                                  [row[1] for row in present], noise)
                rows = [[sum((F(coefficient) * levels[t][j]
                              for t, coefficient in query['terms']), F(0))
                         for j in range(n)] for query in queries]
                expected = conditioned.project(rows)
                checkpoint = trend1.condition(trend1.seed(model), observations, horizon)
                actual = trend1.project(checkpoint, queries)
                self.assertEqual(actual['estimable'], [q['id'] for q in queries])
                self.assertEqual(actual['mean'], list(expected.mean))
                self.assertEqual(actual['covariance'], [list(row) for row in expected.covariance])
