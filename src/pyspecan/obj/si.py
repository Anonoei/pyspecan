class SI:
    __slots__ = ("_val", "_mul", "_si")
    _units = {
        0: ("",""),
        3: ("",""),
        6: ("",""),
        9: ("","")
    }
    def __init__(self, val: float, mul=None):
        if mul is None:
            self._val: float = val
            self._mul: int = 0
            self._si: float = 0
            self._calc()
        else:
            self._mul: int = mul
            self._val: float = val * self._factor()
            self._si: float = val

    def __str__(self):
        return self.to_str()

    def __repr__(self):
        return f"{type(self).__name__} ({self._si}, v{self._val}, m{self._mul})"

    @classmethod
    def get(cls, val):
        if isinstance(val, str):
            return cls.fm_str(val)
        elif isinstance(val, cls):
            return val
        else:
            return cls(val)

    def to_str(self):
        fmt = f"{self._si:.3f}"
        unit = self._units[self._mul][1]
        if not unit == "":
            fmt += f"{unit}"
        return fmt

    @classmethod
    def fm_str(cls, val: str):
        for mul, fmt in cls._units.items():
            if mul == 0:
                continue
            if fmt[0] in val:
                v = val.split(fmt[0])[0]
                return cls(float(v), mul)
            elif fmt[1] in val:
                v = val.split(fmt[1])[0]
                return cls(float(v), mul)
        return cls(float(val))

    @property
    def value(self):
        return self._si

    @property
    def raw(self):
        return self._val

    @raw.setter
    def raw(self, val):
        self._val = val
        self._calc()

    def _factor(self, mul=None):
        if mul is None:
            mul = self._mul
        return 10**mul

    def _calc(self):
        mul = 0
        v = abs(self._val)
        if v > 0:
            while v > 1000:
                v = v/1000
                mul += 3
        self._mul = mul
        self._si = self._val / self._factor(self._mul)

    def __add__(self, other):
        if issubclass(other, SI):
            return self.raw + other.raw # type: ignore
        else:
            return self.raw + other
    def __radd__(self, other):
        return self.__add__(other)

    def __sub__(self, other):
        if isinstance(other, SI):
            return self.raw - other.raw # type: ignore
        else:
            return self.raw - other
    def __rsub__(self, other):
        if isinstance(other, SI):
            return other.raw - self.raw
        else:
            return other - self.raw
    def __mul__(self, other):
        if isinstance(other, SI):
            return self.raw * other.raw # type: ignore
        else:
            return self.raw * other
    def __rmul__(self, other):
        return self.__mul__(other)

    def __truediv__(self, other):
        if isinstance(other, SI):
            return self.raw / other.raw # type: ignore
        else:
            return self.raw / other
    def __rtruediv__(self, other):
        if isinstance(other, SI):
            return other.raw / self.raw # type: ignore
        else:
            return other / self.raw


class Frequency(SI):
    _units = {
        0: ("Hz",""),
        3: ("kHz","k"),
        6: ("MHz","M"),
        9: ("GHz","G")
    }

if __name__ == "__main__":
    unit = Frequency(1_000_000)
    print(f"original: {unit}")
    freq_str = str(unit)
    new_unit = Frequency.fm_str(freq_str)
    print(f"from_str: {new_unit}")
    print(f"from freq: {Frequency.get(unit)}")
