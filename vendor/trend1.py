"""SDK1: exact diffuse local-linear trend, using a formal D -> infinity."""
from fractions import Fraction as F
from .rational import RF


class Inconsistent(ValueError):
    pass


def seed(model):
    means, variances = [], []
    for direction in model['initial']:
        means.append(RF(0 if direction is None else direction[0]))
        variances.append(RF((0, 1)) if direction is None else RF(direction[1]))
    return {
        'format': 'trend1.initial/1',
        'mean': [x.dump() for x in means],
        'covariance': [[(variances[i] if i == j else RF(0)).dump()
                        for j in range(2)] for i in range(2)],
        'process': model['process'],
    }


def condition(state, observations, horizon):
    """Build and condition a joint level trajectory; missing rows still set time."""
    if state['format'] != 'trend1.initial/1':
        raise ValueError('expected SDK1 initial state')
    initial_mean = list(map(RF.load, state['mean']))
    initial_cov = [list(map(RF.load, row)) for row in state['covariance']]
    ql, qs = map(F, state['process'])
    n = horizon + 1
    mean = [initial_mean[0] + t * initial_mean[1] for t in range(n)]
    cov = []
    for i in range(n):
        row = []
        for j in range(n):
            c = (initial_cov[0][0] + j * initial_cov[0][1] +
                 i * initial_cov[1][0] + i * j * initial_cov[1][1])
            c += sum((ql + (i - k) * (j - k) * qs
                      for k in range(1, min(i, j) + 1)), F(0))
            row.append(c)
        cov.append(row)
    for t, value, noise in observations:
        if value is None:
            continue
        variance = cov[t][t] + F(noise)
        residual = RF(value) - mean[t]
        if not variance:
            if residual:
                raise Inconsistent('contradictory deterministic observation at t=' + str(t))
            continue
        column = [cov[i][t] for i in range(n)]
        mean = [mean[i] + column[i] * residual / variance for i in range(n)]
        cov = [[cov[i][j] - column[i] * column[j] / variance
                for j in range(n)] for i in range(n)]
    return {
        'format': 'trend1.trajectory/1', 'horizon': horizon,
        'mean': [x.dump() for x in mean],
        'covariance': [[x.dump() for x in row] for row in cov],
    }


def project(checkpoint, queries):
    if checkpoint['format'] != 'trend1.trajectory/1':
        raise ValueError('expected SDK1 trajectory')
    mean = list(map(RF.load, checkpoint['mean']))
    cov = [list(map(RF.load, row)) for row in checkpoint['covariance']]
    weights = []
    for query in queries:
        row = [F(0)] * len(mean)
        for t, coefficient in query['terms']:
            row[t] += F(coefficient)
        weights.append(row)
    projected_mean = [sum((c * m for c, m in zip(w, mean)), RF(0))
                      for w in weights]
    projected_cov = [[sum((a * b * cov[i][j]
                           for i, a in enumerate(w) if a
                           for j, b in enumerate(v) if b), RF(0))
                      for v in weights] for w in weights]
    statuses, indexes = [], []
    for i, query in enumerate(queries):
        try:
            projected_cov[i][i].limit()
            projected_mean[i].limit()
        except OverflowError:
            status = 'unidentified'
        else:
            status = 'estimable'
            indexes.append(i)
        statuses.append({'id': query['id'], 'status': status})
    return {
        'items': statuses,
        'estimable': [queries[i]['id'] for i in indexes],
        'mean': [projected_mean[i].limit() for i in indexes],
        'covariance': [[projected_cov[i][j].limit() for j in indexes]
                       for i in indexes],
    }
