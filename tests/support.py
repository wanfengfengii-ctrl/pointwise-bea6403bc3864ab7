import unittest
from trend import Store


def query(name, *terms):
    return {'id': name, 'terms': [list(term) for term in terms]}


DIFFUSE = {'initial': [None, None], 'process': [0, 0]}


class ArchiveCase(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.addCleanup(self.store.close)

    def revision(self, model=DIFFUSE, observations=(), request='r', series='sensor'):
        return self.store.apply(series, request, model, list(observations))['revision']

    def run_task(self, revision, prefix, queries, name='task'):
        self.store.create_task(name, revision, prefix, queries)
        return self.store.analyze(name)['report']
