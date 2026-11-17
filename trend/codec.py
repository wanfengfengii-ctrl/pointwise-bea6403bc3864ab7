"""Public input normalization and lossless JSON for Fraction results."""
import json
from fractions import Fraction


class Invalid(ValueError):
    pass


class Conflict(ValueError):
    pass


class Unknown(KeyError):
    pass


def rational(value):
    if isinstance(value, bool) or not isinstance(value, (int, str, Fraction)):
        raise Invalid('use int, Fraction or rational string')
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise Invalid('invalid rational') from exc


def identifier(value):
    if not isinstance(value, str) or not value:
        raise Invalid('nonempty string identity required')
    return value


def natural(value):
    if type(value) is not int or value < 0:
        raise Invalid('nonnegative integer required')
    return value


def sequence(value, size=None):
    if not isinstance(value, (list, tuple)) or (size is not None and len(value) != size):
        raise Invalid('invalid sequence shape')
    return value


def nonnegative(value):
    value = rational(value)
    if value < 0:
        raise Invalid('negative variance')
    return str(value)


def model(value):
    if not isinstance(value, dict) or set(value) != {'initial', 'process'}:
        raise Invalid('model requires initial and process')
    initial = []
    for direction in sequence(value['initial'], 2):
        if direction is None:
            initial.append(None)
        else:
            mean, variance = sequence(direction, 2)
            initial.append([str(rational(mean)), nonnegative(variance)])
    process = [nonnegative(x) for x in sequence(value['process'], 2)]
    return {'initial': initial, 'process': process}


def observations(value):
    out, previous = [], -1
    for row in sequence(value):
        time, reading, variance = sequence(row, 3)
        time = natural(time)
        if time <= previous:
            raise Invalid('observation times must strictly increase')
        previous = time
        out.append([time, None if reading is None else str(rational(reading)),
                    nonnegative(variance)])
    return out


def queries(value):
    out, seen = [], set()
    for item in sequence(value):
        if not isinstance(item, dict) or set(item) != {'id', 'terms'}:
            raise Invalid('query requires id and terms')
        name = identifier(item['id'])
        if name in seen:
            raise Invalid('duplicate combination identity')
        seen.add(name)
        terms = []
        for term in sequence(item['terms']):
            time, coefficient = sequence(term, 2)
            terms.append([natural(time), str(rational(coefficient))])
        out.append({'id': name, 'terms': terms})
    return out


def _default(value):
    if isinstance(value, Fraction):
        return {'$fraction': str(value)}
    raise TypeError(type(value).__name__)


def _object(value):
    if set(value) == {'$fraction'}:
        return Fraction(value['$fraction'])
    return value


def dumps(value):
    return json.dumps(value, default=_default, sort_keys=True, separators=(',', ':'))


def loads(value):
    return json.loads(value, object_hook=_object)
