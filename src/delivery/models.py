"""Core data types。純資料類別，無業務邏輯。"""
from dataclasses import dataclass, field
from typing import Callable, Literal, Protocol

# 騎手在餐廳可容忍的最長等待秒數（3 分鐘）。超過此門檻的等待視為「空等」，
# 演算法應盡量改變停靠順序去做其他有用的事，而非在餐廳乾等。
WAIT_TOLERANCE_S = 180.0
# 對「超過容忍門檻」的等待秒數施加的成本權重：每多等 1 秒額外計為此倍數，
# 讓演算法願意多花一點行駛時間來避免長時間空等（順路的短暫等待則不受罰）。
WAIT_OVERAGE_WEIGHT = 5.0


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
