"""Immutable shared-calibration revisions and idempotent acceptance receipts."""
from . import codec


def apply_calibration(store, calibration, request, mean, variance):
    calibration = codec.identifier(calibration)
    request = codec.identifier(request)
    payload = codec.dumps({'calibration': calibration,
                           'mean': str(codec.rational(mean)),
                           'variance': codec.nonnegative(variance)})
    with store.transaction('apply_calibration') as connection:
        old = connection.execute(
            'SELECT * FROM calibration_receipts WHERE request=?',
            (request,)).fetchone()
        if old:
            if old['payload'] != payload:
                raise codec.Conflict(
                    'calibration request already bound to different content')
            return codec.loads(old['receipt'])
        spec = codec.loads(payload)
        revision_id = connection.execute(
            'INSERT INTO calibration_revisions(calibration,mean,variance) '
            'VALUES(?,?,?)',
            (calibration, spec['mean'], spec['variance'])).lastrowid
        connection.execute(
            'INSERT INTO calibration_heads VALUES(?,?) '
            'ON CONFLICT(calibration) DO UPDATE SET '
            'calibration_revision=excluded.calibration_revision',
            (calibration, revision_id))
        receipt = {'request': request, 'calibration': calibration,
                   'calibration_revision': revision_id}
        connection.execute(
            'INSERT INTO calibration_receipts VALUES(?,?,?,?)',
            (request, payload, revision_id, codec.dumps(receipt)))
        return receipt


def calibration_head(store, calibration):
    calibration = codec.identifier(calibration)
    row = store.connection.execute(
        'SELECT calibration_revision FROM calibration_heads WHERE calibration=?',
        (calibration,)).fetchone()
    if row is None:
        raise codec.Unknown(calibration)
    return row['calibration_revision']


def calibration_revision(store, revision_id):
    if isinstance(revision_id, bool) or type(revision_id) is not int \
            or revision_id < 0:
        raise codec.Invalid('nonnegative integer required')
    row = store.connection.execute(
        'SELECT * FROM calibration_revisions WHERE calibration_revision=?',
        (revision_id,)).fetchone()
    if row is None:
        raise codec.Unknown(revision_id)
    return {'calibration': row['calibration'],
            'calibration_revision': row['calibration_revision'],
            'mean': row['mean'], 'variance': row['variance']}