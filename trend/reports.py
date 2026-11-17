"""Atomic numeric publication, terminal status and stable execution receipt."""
from . import codec
from .tasks import task as read_task


def publish(store, name, result=None, checkpoint=None, error=None):
    if (error is None) != (result is not None and checkpoint is not None):
        raise codec.Invalid('publication must be either a whole result or an error')
    status = 'error' if error is not None else 'done'
    receipt = {'task': name, 'status': status, 'receipt': 'analysis:' + name}
    with store.transaction('publish') as connection:
        row = connection.execute('SELECT status FROM tasks WHERE task=?', (name,)).fetchone()
        if row is None:
            raise codec.Unknown(name)
        if row['status'] != 'pending':
            raise codec.Conflict('task is already terminal')
        if error is None:
            connection.execute('INSERT INTO reports VALUES(?,?,?)',
                               (name, codec.dumps(result), codec.dumps(checkpoint)))
        connection.execute('UPDATE tasks SET status=?,error=? WHERE task=?',
                           (status, error, name))
        connection.execute('INSERT INTO task_receipts VALUES(?,?)',
                           (name, codec.dumps(receipt)))


def read_report(store, name):
    source = read_task(store, name)
    row = store.connection.execute('SELECT result FROM reports WHERE task=?',
                                   (name,)).fetchone()
    receipt = store.connection.execute('SELECT receipt FROM task_receipts WHERE task=?',
                                       (name,)).fetchone()
    return {'source': source, 'status': source['status'], 'error': source['error'],
            'report': None if row is None else codec.loads(row['result']),
            'receipt': None if receipt is None else codec.loads(receipt['receipt'])}
