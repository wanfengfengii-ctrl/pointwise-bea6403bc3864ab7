"""Finite, reproducible v1 archive builder, through the public business API."""
import argparse
from .db import Store
from vendor.trend1 import Inconsistent


def point(name, time):
    return {'id': name, 'terms': [[time, 1]]}


def build(store):
    diffuse = {'initial': [None, None], 'process': [0, 0]}
    first = store.apply('river', 'river-v1', diffuse, [[0, 5, 0]])['revision']
    store.create_task('one-reading', first, 1, [
        point('future', 2),
        {'id': 'curvature', 'terms': [[2, 1], [1, -2], [0, 1]]}])
    store.analyze('one-reading')
    second = store.apply('river', 'river-v2', diffuse, [[0, 5, 0], [1, 7, 0]])['revision']
    store.create_task('two-readings', second, 2, [point('x2', 2), point('x3', 3)])
    store.analyze('two-readings')
    store.create_task('frozen-pending', first, 1, [point('future', 4)])
    bad = store.apply('river', 'river-v3', diffuse,
                      [[0, 5, 0], [1, 7, 0], [2, 10, 0]])['revision']
    store.create_task('contradiction', bad, 3, [point('future', 3)])
    try:
        store.analyze('contradiction')
    except Inconsistent:
        pass
    mixed = {'initial': [None, [1, 2]], 'process': [1, 1]}
    fourth = store.apply('air', 'air-v1', mixed,
                         [[0, 5, 1], [1, None, 0], [2, 9, 2]])['revision']
    store.create_task('mixed', fourth, 3, [point('x2', 2), point('x3', 3)])
    store.analyze('mixed')
    proper = {'initial': [[2, 4], [1, 1]], 'process': [1, 0]}
    fifth = store.apply('baseline', 'baseline-v1', proper, [])['revision']
    store.create_task('proper', fifth, 0, [point('x1', 1), point('x2', 2)])
    store.analyze('proper')
    return {'revisions': [first, second, bad, fourth, fifth],
            'tasks': ['one-reading', 'two-readings', 'frozen-pending',
                      'contradiction', 'mixed', 'proper']}


def main():
    parser = argparse.ArgumentParser(description='Build a complete SDK1 trend archive')
    parser.add_argument('database')
    args = parser.parse_args()
    from .codec import dumps
    with Store(args.database) as store:
        print(dumps(build(store)))


if __name__ == '__main__':
    main()
