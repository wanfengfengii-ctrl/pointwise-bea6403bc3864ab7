"""Atomic publication of joint numeric reports and terminal receipts."""
from . import codec
from .joint import _source


def publish_joint(store, name, result=None, checkpoint=None, error=None):
    if (error is None) != (result is not None and checkpoint is not None):
        raise codec.Invalid('publication must be either a whole result or an error')
    status = 'error' if error is not None else 'done'
    receipt = {'task': name, 'status': status,
               'receipt': 'joint-analysis:' + name}
    with store.transaction('publish_joint') as connection:
        row = connection.execute(
            'SELECT status FROM joint_tasks WHERE task=?', (name,)).fetchone()
        if row is None:
            raise codec.Unknown(name)
        if row['status'] != 'pending':
            raise codec.Conflict('joint task is already terminal')
        if error is None:
            connection.execute('INSERT INTO joint_reports VALUES(?,?,?)',
                               (name, codec.dumps(result), codec.dumps(checkpoint)))
        connection.execute(
            'UPDATE joint_tasks SET status=?,error=? WHERE task=?',
            (status, error, name))
        connection.execute('INSERT INTO joint_task_receipts VALUES(?,?)',
                           (name, codec.dumps(receipt)))


def read_joint_report(store, name):
    name = codec.identifier(name)
    row = store.connection.execute(
        'SELECT * FROM joint_tasks WHERE task=?', (name,)).fetchone()
    if row is None:
        raise codec.Unknown(name)
    source = _source(store, name, row)
    report_row = store.connection.execute(
        'SELECT result FROM joint_reports WHERE task=?', (name,)).fetchone()
    receipt_row = store.connection.execute(
        'SELECT receipt FROM joint_task_receipts WHERE task=?',
        (name,)).fetchone()
    return {'source': source, 'status': source['status'],
            'error': source['error'],
            'report': None if report_row is None
            else codec.loads(report_row['result']),
            'receipt': None if receipt_row is None
            else codec.loads(receipt_row['receipt'])}
