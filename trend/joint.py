"""Fixed joint tasks: one calibration revision, ordered station bindings."""
from . import codec
from . import joint_math
from .calibration import calibration_revision as read_calibration
from .series import revision as read_series_revision


def _normalize_binding(item):
    if not isinstance(item, dict) or set(item) != {
            'id', 'revision', 'prefix', 'loading'}:
        raise codec.Invalid('binding requires id, revision, prefix and loading')
    return {'id': codec.identifier(item['id']),
            'revision': codec.natural(item['revision']),
            'prefix': codec.natural(item['prefix']),
            'loading': str(codec.rational(item['loading']))}


def _normalize_queries(value):
    out, seen = [], set()
    for item in codec.sequence(value):
        if not isinstance(item, dict) or set(item) != {'id', 'terms'}:
            raise codec.Invalid('query requires id and terms')
        name = codec.identifier(item['id'])
        if name in seen:
            raise codec.Invalid('duplicate combination identity')
        seen.add(name)
        terms = []
        for term in codec.sequence(item['terms']):
            binding_id, time, coefficient = codec.sequence(term, 3)
            time = codec.natural(time)
            if time > joint_math.HORIZON:
                raise codec.Invalid('joint query times must be in 0..8')
            terms.append([codec.identifier(binding_id), time,
                          str(codec.rational(coefficient))])
        out.append({'id': name, 'terms': terms})
    if len(out) > joint_math.MAX_QUERIES:
        raise codec.Invalid('at most 12 joint queries')
    return out


def _source(store, name, row):
    calibration = read_calibration(store, row['calibration_revision'])
    return {'task': name, 'calibration': calibration,
            'bindings': codec.loads(row['bindings']),
            'queries': codec.loads(row['queries']),
            'status': row['status'], 'error': row['error']}


def joint_task(store, name):
    name = codec.identifier(name)
    row = store.connection.execute(
        'SELECT * FROM joint_tasks WHERE task=?', (name,)).fetchone()
    if row is None:
        raise codec.Unknown(name)
    return _source(store, name, row)


def create_joint_task(store, name, calibration_revision_id, bindings, queries):
    name = codec.identifier(name)
    calibration_revision_id = codec.natural(calibration_revision_id)
    raw_bindings = codec.sequence(bindings)
    if not 1 <= len(raw_bindings) <= joint_math.MAX_BINDINGS:
        raise codec.Invalid('joint task requires 1..4 bindings')
    normalized_bindings, binding_ids, series_names = [], set(), set()
    for item in raw_bindings:
        binding = _normalize_binding(item)
        if binding['id'] in binding_ids:
            raise codec.Invalid('duplicate binding identity')
        binding_ids.add(binding['id'])
        normalized_bindings.append(binding)
    normalized_queries = _normalize_queries(queries)
    with store.transaction('create_joint_task') as connection:
        read_calibration(store, calibration_revision_id)
        frozen = []
        for binding in normalized_bindings:
            revision = read_series_revision(store, binding['revision'])
            if revision['series'] in series_names:
                raise codec.Invalid('a series may appear in only one binding')
            series_names.add(revision['series'])
            observations = revision['observations']
            if binding['prefix'] > min(joint_math.MAX_OBSERVATION_ROWS,
                                       len(observations)):
                raise codec.Invalid('joint prefix exceeds the frozen row limit')
            selected = observations[:binding['prefix']]
            if any(row[0] > joint_math.HORIZON for row in selected):
                raise codec.Invalid('selected observation times must be in 0..8')
            frozen.append({'id': binding['id'], 'series': revision['series'],
                           'revision': binding['revision'],
                           'prefix': binding['prefix'],
                           'loading': binding['loading']})
        for query in normalized_queries:
            for binding_id, _time, _coefficient in query['terms']:
                if binding_id not in binding_ids:
                    raise codec.Unknown(binding_id)
        encoded_bindings, encoded_queries = (
            codec.dumps(frozen), codec.dumps(normalized_queries))
        old = connection.execute(
            'SELECT * FROM joint_tasks WHERE task=?', (name,)).fetchone()
        if old:
            if (old['calibration_revision'], old['bindings'], old['queries']) != (
                    calibration_revision_id, encoded_bindings, encoded_queries):
                raise codec.Conflict('joint task identity already bound')
        else:
            connection.execute(
                'INSERT INTO joint_tasks VALUES(?,?,?,?,?,NULL)',
                (name, calibration_revision_id, encoded_bindings,
                 encoded_queries, 'pending'))
    return joint_task(store, name)
