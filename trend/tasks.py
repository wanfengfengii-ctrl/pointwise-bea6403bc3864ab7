"""Task identities freeze a revision, row prefix, and ordered combinations."""
from . import codec
from .series import revision as read_revision


def task(store, name):
    name = codec.identifier(name)
    row = store.connection.execute('SELECT * FROM tasks WHERE task=?', (name,)).fetchone()
    if row is None:
        raise codec.Unknown(name)
    revision = read_revision(store, row['revision'])
    return {'task': name, 'series': revision['series'], 'revision': row['revision'],
            'prefix': row['prefix'], 'queries': codec.loads(row['queries']),
            'status': row['status'], 'error': row['error']}


def create_task(store, name, revision_id, prefix, queries):
    name, revision_id = codec.identifier(name), codec.natural(revision_id)
    prefix, queries = codec.natural(prefix), codec.queries(queries)
    encoded = codec.dumps(queries)
    with store.transaction('create_task') as connection:
        revision = read_revision(store, revision_id)
        if prefix > len(revision['observations']):
            raise codec.Invalid('prefix exceeds observation row count')
        old = connection.execute('SELECT * FROM tasks WHERE task=?', (name,)).fetchone()
        if old:
            if (old['revision'], old['prefix'], old['queries']) != (revision_id, prefix, encoded):
                raise codec.Conflict('task identity already bound')
        else:
            connection.execute('INSERT INTO tasks VALUES(?,?,?,?,?,NULL)',
                               (name, revision_id, prefix, encoded, 'pending'))
    return task(store, name)
