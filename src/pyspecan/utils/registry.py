"""Name -> class registries, used for plots, modes, sinks and views"""
from typing import Callable, Generic, Iterator, TypeVar

T = TypeVar("T")

class Registry(Generic[T]):
    """Ordered name -> item mapping with a decorator for registering"""
    def __init__(self, kind: str):
        self.kind = kind
        self._items: dict[str, T] = {}

    def register(self, name: str) -> Callable[[T], T]:
        def deco(item: T) -> T:
            if name in self._items:
                raise ValueError(f"{self.kind} {name!r} is already registered")
            self._items[name] = item
            return item
        return deco

    def get(self, name: str) -> T:
        try:
            return self._items[name]
        except KeyError:
            raise ValueError(f"unknown {self.kind} {name!r}") from None

    def names(self) -> list[str]:
        return list(self._items)

    def items(self):
        return self._items.items()

    def __contains__(self, name) -> bool:
        return name in self._items

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)
