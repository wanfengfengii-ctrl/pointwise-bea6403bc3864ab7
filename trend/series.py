"""Immutable full revisions and idempotent acceptance receipts."""
from . import codec
from vendor import trend1


def apply(store, series, request, model, observations):
    series, request = codec.identifier(series), codec.identifier(request)
    payload = codec.dumps({'series': series, 'model': codec.model(model),
                           'observations': codec.observations(observations)})
    with store.transaction('apply') as connection:
        old = connection.execute(
            'SELECT * FROM apply_receipts WHERE request=?', (request,)).fetchone()
        if old:
            if old['payload'] != payload:
                raise codec.Conflict('request already bound to different content')
            return codec.loads(old['receipt'])
        normalized = codec.loads(payload)
        state = trend1.seed(normalized['model'])
        revision_id = connection.execute(
            'INSERT INTO revisions(series,payload,sdk1_state) VALUES(?,?,?)',
            (series, payload, codec.dumps(state))).lastrowid
        connection.execute(
            'INSERT INTO heads VALUES(?,?) ON CONFLICT(series) DO UPDATE SET revision=excluded.revision',
            (series, revision_id))
        receipt = {'request': request, 'series': series, 'revision': revision_id}
        connection.execute('INSERT INTO apply_receipts VALUES(?,?,?,?)',
                           (request, payload, revision_id, codec.dumps(receipt)))
        return receipt


def head(store, series):
    series = codec.identifier(series)
    row = store.connection.execute('SELECT revision FROM heads WHERE series=?',
                                   (series,)).fetchone()
    if row is None:
        raise codec.Unknown(series)
    return row['revision']


def revision(store, revision_id):
    revision_id = codec.natural(revision_id)
    row = store.connection.execute('SELECT * FROM revisions WHERE revision=?',
                                   (revision_id,)).fetchone()
    if row is None:
        raise codec.Unknown(revision_id)
    out = codec.loads(row['payload'])
    out.update(revision=row['revision'], sdk1_state=codec.loads(row['sdk1_state']))
    return out
