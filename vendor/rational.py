"""Exact rational functions in the formal diffuse scale D (SDK1 only)."""
from fractions import Fraction as F


def trim(p):
    p = list(map(F, p))
    while len(p) > 1 and p[-1] == 0:
        p.pop()
    return tuple(p or [F(0)])


def add(a, b):
    return trim([(a[i] if i < len(a) else 0) +
                 (b[i] if i < len(b) else 0)
                 for i in range(max(len(a), len(b)))])


def mul(a, b):
    out = [F(0)] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            out[i + j] += x * y
    return trim(out)


def divmod_poly(a, b):
    a, b = trim(a), trim(b)
    if b == (0,):
        raise ZeroDivisionError
    out = [F(0)] * max(1, len(a) - len(b) + 1)
    while a != (0,) and len(a) >= len(b):
        k, c = len(a) - len(b), a[-1] / b[-1]
        out[k] = c
        a = add(a, [0] * k + [-c * x for x in b])
    return trim(out), a


def gcd(a, b):
    while b != (0,):
        a, b = b, divmod_poly(a, b)[1]
    return tuple(x / a[-1] for x in a) if a != (0,) else (F(1),)


class RF:
    """Canonical quotient of Fraction polynomials, coefficients low to high."""
    def __init__(self, numerator=(0,), denominator=(1,)):
        if isinstance(numerator, RF):
            self.n, self.d = numerator.n, numerator.d
            return
        if isinstance(numerator, (int, F, str)):
            numerator = (F(numerator),)
        n, d = trim(numerator), trim(denominator)
        if d == (0,):
            raise ZeroDivisionError
        g = gcd(n, d)
        n, d = divmod_poly(n, g)[0], divmod_poly(d, g)[0]
        scale = d[-1]
        self.n = tuple(x / scale for x in n)
        self.d = tuple(x / scale for x in d)

    def __add__(self, other):
        other = RF(other)
        return RF(add(mul(self.n, other.d), mul(other.n, self.d)),
                  mul(self.d, other.d))

    __radd__ = __add__

    def __neg__(self):
        return RF([-x for x in self.n], self.d)

    def __sub__(self, other):
        return self + -RF(other)

    def __rsub__(self, other):
        return RF(other) + -self

    def __mul__(self, other):
        other = RF(other)
        return RF(mul(self.n, other.n), mul(self.d, other.d))

    __rmul__ = __mul__

    def __truediv__(self, other):
        other = RF(other)
        return RF(mul(self.n, other.d), mul(self.d, other.n))

    def __bool__(self):
        return self.n != (0,)

    def limit(self):
        if len(self.n) > len(self.d):
            raise OverflowError('unidentified diffuse direction')
        return self.n[-1] / self.d[-1] if len(self.n) == len(self.d) else F(0)

    def dump(self):
        return [[str(x) for x in self.n], [str(x) for x in self.d]]

    @classmethod
    def load(cls, value):
        return cls(*value)
