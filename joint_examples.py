"""Public hand-worked inputs for the new joint trend capability.

These are data, not an implementation or an executable acceptance suite.
Run this module to inspect the complete examples. Existing APIs are unchanged.
"""
from fractions import Fraction as F
from trend.codec import dumps


def examples():
    """Return fresh inputs; each list entry is a separate archive scenario."""
    proper = {'initial': [[0, 1], [0, 0]], 'process': [0, 0]}
    diffuse = {'initial': [None, None], 'process': [0, 0]}
    fixed = {'initial': [[0, 0], [0, 0]], 'process': [0, 0]}
    base_queries = [
        {'id': 'a', 'terms': [['a', 0, 1]]},
        {'id': 'b', 'terms': [['b', 0, 1]]},
        {'id': 'difference', 'terms': [['a', 0, 1], ['b', 0, -1]]},
    ]
    return [
        {
            'name': 'shared-proper',
            'calibration': {'calibration': 'sensor', 'request': 'cal-1',
                            'mean': 0, 'variance': 4},
            'series': [
                {'series': 'station-a', 'request': 'a-1', 'model': proper,
                 'observations': [[0, 5, 0]]},
                {'series': 'station-b', 'request': 'b-1', 'model': proper,
                 'observations': [[0, 7, 0]]},
            ],
            'bindings': [
                {'id': 'a', 'series': 'station-a', 'prefix': 1, 'loading': 1},
                {'id': 'b', 'series': 'station-b', 'prefix': 1, 'loading': 1},
            ],
            'queries': base_queries,
            'expected': {
                'items': [{'id': q['id'], 'status': 'estimable'} for q in base_queries],
                'estimable': ['a', 'b', 'difference'],
                'mean': [F(-1, 3), F(5, 3), F(-2)],
                'covariance': [[F(4, 9), F(4, 9), F(0)],
                               [F(4, 9), F(4, 9), F(0)],
                               [F(0), F(0), F(0)]],
            },
        },
        {
            'name': 'shared-diffuse',
            'calibration': {'calibration': 'sensor', 'request': 'cal-1',
                            'mean': 0, 'variance': 4},
            'series': [
                {'series': 'station-a', 'request': 'a-1', 'model': diffuse,
                 'observations': [[0, 5, 0]]},
                {'series': 'station-b', 'request': 'b-1', 'model': diffuse,
                 'observations': [[0, 7, 0]]},
            ],
            'bindings': [
                {'id': 'a', 'series': 'station-a', 'prefix': 1, 'loading': 1},
                {'id': 'b', 'series': 'station-b', 'prefix': 1, 'loading': 1},
            ],
            'queries': base_queries + [
                {'id': 'future', 'terms': [['a', 1, 1]]},
                {'id': 'curvature', 'terms': [['a', 2, 1], ['a', 1, -2],
                                             ['a', 0, 1]]},
            ],
            'expected': {
                'items': [{'id': q['id'], 'status': 'estimable'} for q in base_queries]
                         + [{'id': 'future', 'status': 'unidentified'},
                            {'id': 'curvature', 'status': 'estimable'}],
                'estimable': ['a', 'b', 'difference', 'curvature'],
                'mean': [F(5), F(7), F(-2), F(0)],
                'covariance': [[F(4), F(4), F(0), F(0)],
                               [F(4), F(4), F(0), F(0)],
                               [F(0), F(0), F(0), F(0)],
                               [F(0), F(0), F(0), F(0)]],
            },
        },
        {
            'name': 'shared-contradiction',
            'calibration': {'calibration': 'sensor', 'request': 'cal-1',
                            'mean': 0, 'variance': 4},
            'series': [
                {'series': 'station-a', 'request': 'a-1', 'model': fixed,
                 'observations': [[0, 5, 0]]},
                {'series': 'station-b', 'request': 'b-1', 'model': fixed,
                 'observations': [[0, 7, 0]]},
            ],
            'bindings': [
                {'id': 'a', 'series': 'station-a', 'prefix': 1, 'loading': 1},
                {'id': 'b', 'series': 'station-b', 'prefix': 1, 'loading': 1},
            ],
            'queries': [],
            'expected_error': 'Inconsistent',
        },
    ]


if __name__ == '__main__':
    print(dumps(examples()))
