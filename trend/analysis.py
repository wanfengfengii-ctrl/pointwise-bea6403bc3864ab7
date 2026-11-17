"""Fixed-prefix SDK1 execution; publish only after complete joint projection."""
from .tasks import task as read_task
from .series import revision as read_revision
from .reports import publish, read_report
from vendor import trend1


def analyze(store, name):
    task = read_task(store, name)
    if task['status'] == 'done':
        return read_report(store, name)
    if task['status'] == 'error':
        raise trend1.Inconsistent(task['error'])
    revision = read_revision(store, task['revision'])
    observations = revision['observations'][:task['prefix']]
    horizon = max([0] + [row[0] for row in observations] +
                  [term[0] for query in task['queries'] for term in query['terms']])
    try:
        checkpoint = trend1.condition(revision['sdk1_state'], observations, horizon)
        report = trend1.project(checkpoint, task['queries'])
    except trend1.Inconsistent as exc:
        publish(store, name, error=str(exc))
        raise
    publish(store, name, result=report, checkpoint=checkpoint)
    return read_report(store, name)
