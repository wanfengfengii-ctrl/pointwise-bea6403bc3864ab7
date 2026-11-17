"""SDK2: finite rational normal distributions, including singular normals.

No diffuse initial distribution or trend/archive compatibility facilities.
"""
from dataclasses import dataclass
from fractions import Fraction as F


class Inconsistent(ValueError):
    pass


def q(value):
    if isinstance(value, bool) or not isinstance(value, (int, str, F)):
        raise ValueError('exact rational required')
    return F(value)


def matrix(rows, width):
    out = tuple(tuple(q(x) for x in row) for row in rows)
    if any(len(row) != width for row in out):
        raise ValueError('matrix dimensions')
    return out


def dot(a, b):
    return sum((x * y for x, y in zip(a, b)), F(0))


def psd(cov):
    n = len(cov)
    if any(cov[i][j] != cov[j][i] for i in range(n) for j in range(n)):
        raise ValueError('asymmetric covariance')
    work = [list(row) for row in cov]
    for k in range(n):
        pivot = work[k][k]
        if pivot < 0:
            raise ValueError('negative covariance')
        if not pivot:
            if any(work[i][k] for i in range(k + 1, n)):
                raise ValueError('non-positive-semidefinite covariance')
            continue
        for i in range(k + 1, n):
            for j in range(k + 1, n):
                work[i][j] -= work[i][k] * work[k][j] / pivot


@dataclass(frozen=True)
class Normal:
    mean: tuple
    covariance: tuple

    def __post_init__(self):
        mean = tuple(q(x) for x in self.mean)
        covariance = matrix(self.covariance, len(mean))
        if len(covariance) != len(mean):
            raise ValueError('covariance dimensions')
        psd(covariance)
        object.__setattr__(self, 'mean', mean)
        object.__setattr__(self, 'covariance', covariance)

    def independent(self, other):
        n, m = len(self.mean), len(other.mean)
        cov = [list(row) + [F(0)] * m for row in self.covariance]
        cov += [[F(0)] * n + list(row) for row in other.covariance]
        return Normal(self.mean + other.mean, cov)

    def affine(self, rows, offset=None, noise=None):
        rows = matrix(rows, len(self.mean))
        count = len(rows)
        offset = tuple(q(x) for x in (offset if offset is not None else [0] * count))
        if len(offset) != count:
            raise ValueError('offset dimensions')
        if noise is None:
            noise = Normal([0] * count, [[0] * count for _ in range(count)])
        if len(noise.mean) != count:
            raise ValueError('noise dimensions')
        means = [dot(row, self.mean) + offset[i] + noise.mean[i]
                 for i, row in enumerate(rows)]
        cov = [[sum((a * b * self.covariance[k][l]
                     for k, a in enumerate(row)
                     for l, b in enumerate(col)), F(0)) + noise.covariance[i][j]
                for j, col in enumerate(rows)] for i, row in enumerate(rows)]
        return Normal(means, cov)

    def project(self, rows):
        return self.affine(rows)

    def condition(self, rows, values, noise=None):
        rows = matrix(rows, len(self.mean))
        values = tuple(q(x) for x in values)
        if len(rows) != len(values):
            raise ValueError('condition dimensions')
        count, n = len(rows), len(self.mean)
        if noise is None:
            noise = Normal([0] * count, [[0] * count for _ in range(count)])
        if len(noise.mean) != count:
            raise ValueError('noise dimensions')
        joint = self.independent(noise)
        m, c = list(joint.mean), [list(row) for row in joint.covariance]
        for index, row in enumerate(rows):
            h = list(row) + [F(int(j == index)) for j in range(count)]
            column = [dot(r, h) for r in c]
            variance = dot(h, column)
            residual = values[index] - dot(h, m)
            if not variance:
                if residual:
                    raise Inconsistent('inconsistent deterministic condition')
                continue
            m = [x + a * residual / variance for x, a in zip(m, column)]
            c = [[c[i][j] - column[i] * column[j] / variance
                  for j in range(len(m))] for i in range(len(m))]
        return Normal(m[:n], [row[:n] for row in c[:n]])

    def dump(self):
        return {'format': 'gaussian2.normal/1',
                'mean': [str(x) for x in self.mean],
                'covariance': [[str(x) for x in row] for row in self.covariance]}

    @classmethod
    def load(cls, value):
        if value['format'] != 'gaussian2.normal/1':
            raise ValueError('unsupported normal format')
        return cls(value['mean'], value['covariance'])
