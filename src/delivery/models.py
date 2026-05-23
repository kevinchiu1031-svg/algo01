"""Core data types。純資料類別，無業務邏輯。"""
from dataclasses import dataclass, field
from typing import Callable, Literal, Protocol


@dataclass(frozen=True)
class Order:
    id: int
    restaurant_node: int
    customer_node: int
    place_time: float
    prep_time: float

    @property
    def food_ready_time(self) -> float:
        return self.place_time + self.prep_time


@dataclass(frozen=True)
class Stop:
    order_id: int
    kind: Literal["pickup", "dropoff"]
    node: int


@dataclass
class DriverState:
    location_node: int
    current_time: float
    in_hand: list[Stop] = field(default_factory=list)


@dataclass
class Decision:
    accept: bool
    new_route: list[Stop] | None = None


class DistanceMatrix:
    """Lazy Dijkstra wrapper。第一次查詢觸發底層 lookup，之後走 cache。"""

    def __init__(
        self,
        lookup_fn: Callable[[int, int], float],
        symmetric: bool = False,
    ) -> None:
        self._lookup = lookup_fn
        self._symmetric = symmetric
        self._cache: dict[tuple[int, int], float] = {}

    def __getitem__(self, key: tuple[int, int]) -> float:
        u, v = key
        if u == v:
            return 0.0
        canonical = (min(u, v), max(u, v)) if self._symmetric else (u, v)
        if canonical not in self._cache:
            self._cache[canonical] = self._lookup(u, v)
        return self._cache[canonical]


class Dispatcher(Protocol):
    name: str

    def plan(
        self,
        state: DriverState,
        candidate: Order,
        all_orders: dict[int, Order],
        dist: DistanceMatrix,
    ) -> Decision: ...
