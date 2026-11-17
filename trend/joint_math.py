"""Exact joint kernel for stations sharing one calibration offset.

Full recomputation (no reuse of archived SDK1 checkpoints): every station's
local-linear level trajectory for times 0..HORIZON is stacked with the single
shared calibration offset Z.  Diffuse initial directions keep SDK1's formal
scale D as a rational function; the D -> +infinity limit is taken only after
all joint observations have been conditioned and all query combinations have
been projected, so shared error is never treated as independent noise.
"""
from fractions import Fraction as F
from vendor.rational import RF
from vendor.trend1 import Inconsistent

HORIZON = 8
_STEPS = HORIZON + 1
MAX_BINDINGS = 4
MAX_OBSERVATION_ROWS = 8
MAX_QUERIES = 12


def _station_prior(initial_state):
    """Mean and covariance of one station's levels at times 0..HORIZON."""
    if initial_state['format'] != 'trend1.initial/1':
        raise ValueError('expected SDK1 initial state')
    initial_mean = list(map(RF.load, initial_state['mean']))
    initial_cov = [list(map(RF.load, row)) for row in initial_state['covariance']]
    ql, qs = map(F, initial_state['process'])
    n = _STEPS
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
    return mean, cov


def build_joint(bindings, calibration):
    """Stack independent station priors with the shared calibration offset.

    bindings entries: {'id', 'state' (trend1.initial/1), 'loading' (Fraction)}.
    calibration: {'mean' (Fraction), 'variance' (Fraction)}.
    Returns the unconditional joint mean/covariance and the index map.
    """
    means, blocks = [], []
    for binding in bindings:
        mean, cov = _station_prior(binding['state'])
        means.extend(mean)
        blocks.append(cov)
    z_index = len(means)
    means.append(RF(calibration['mean']))
    size = z_index + 1
    cov = [[RF(0) for _ in range(size)] for _ in range(size)]
    for b, block in enumerate(blocks):
        for i, row in enumerate(block):
            for j, value in enumerate(row):
                cov[b * _STEPS + i][b * _STEPS + j] = value
    cov[z_index][z_index] = RF(calibration['variance'])
    return {'mean': means, 'covariance': cov, 'z_index': z_index}


def level_index(binding_position, time):
    return binding_position * _STEPS + time


def condition_joint(prior, bindings, observations):
    """Condition the stacked vector on every effective station observation.

    Each observation row is [time, value, measurement_variance]; missing rows
    (value is None) advance the station clock but create no condition.  All
    observations share the single Z with their binding's fixed loading.
    """
    mean, cov = list(prior['mean']), [list(row) for row in prior['covariance']]
    z_index = prior['z_index']
    size = len(mean)
    for position, (binding, rows) in enumerate(zip(bindings, observations)):
        loading = F(binding['loading'])
        for time, value, noise in rows:
            if value is None:
                continue
            h = [F(0)] * size
            h[level_index(position, time)] = F(1)
            h[z_index] = loading
            column = [sum((h[j] * cov[i][j] for j in range(size)), RF(0))
                      for i in range(size)]
            variance = sum((h[i] * column[i] for i in range(size)), RF(0)) + F(noise)
            residual = RF(value) - sum(
                (h[i] * mean[i] for i in range(size)), RF(0))
            if not variance:
                if residual:
                    raise Inconsistent(
                        'contradictory deterministic joint observation at t='
                        + str(time))
                continue
            mean = [mean[i] + column[i] * residual / variance for i in range(size)]
            cov = [[cov[i][j] - column[i] * column[j] / variance
                    for j in range(size)] for i in range(size)]
    return {'format': 'joint.trajectory/1', 'horizon': HORIZON,
            'binding_ids': [b['id'] for b in bindings],
            'z_index': z_index,
            'mean': [x.dump() for x in mean],
            'covariance': [[x.dump() for x in row] for row in cov]}


def _query_weights(query, positions):
    row = {}
    for binding_id, time, coefficient in query['terms']:
        index = level_index(positions[binding_id], time)
        row[index] = row.get(index, RF(0)) + RF(coefficient)
    return row


def project_joint(checkpoint, queries):
    """Project named level combinations and take the exact diffuse limit."""
    if checkpoint['format'] != 'joint.trajectory/1':
        raise ValueError('expected joint trajectory checkpoint')
    mean = list(map(RF.load, checkpoint['mean']))
    cov = [list(map(RF.load, row)) for row in checkpoint['covariance']]
    positions = {binding_id: i
                 for i, binding_id in enumerate(checkpoint['binding_ids'])}
    weights = [_query_weights(query, positions) for query in queries]

    def dot_weight(weight, vector):
        return sum((coefficient * vector[index]
                    for index, coefficient in weight.items()), RF(0))

    projected_mean = [dot_weight(weight, mean) for weight in weights]
    projected_cov = [
        [sum((a * b * cov[i][j] for i, a in w.items() for j, b in v.items()),
             RF(0)) for v in weights]
        for w in weights]
    items, indexes = [], []
    for i, query in enumerate(queries):
        try:
            projected_cov[i][i].limit()
            projected_mean[i].limit()
        except OverflowError:
            status = 'unidentified'
        else:
            status = 'estimable'
            indexes.append(i)
        items.append({'id': query['id'], 'status': status})
    return {
        'items': items,
        'estimable': [queries[i]['id'] for i in indexes],
        'mean': [projected_mean[i].limit() for i in indexes],
        'covariance': [[projected_cov[i][j].limit() for j in indexes]
                       for i in indexes],
    }
