"""共用 test fixtures。"""
import pytest

from delivery.models import DistanceMatrix


def make_dist(table: dict[tuple[int, int], float]) -> DistanceMatrix:
    """從 dict 建一個 DistanceMatrix。對稱補齊缺項。"""
    full: dict[tuple[int, int], float] = {}
    for (u, v), d in table.items():
        full[(u, v)] = d
        full[(v, u)] = d
    for u, v in list(full):
        full.setdefault((u, u), 0.0)
        full.setdefault((v, v), 0.0)

    def lookup(a: int, b: int) -> float:
        return full[(a, b)]
    return DistanceMatrix(lookup)


@pytest.fixture
def dist_factory():
    """用法：def test_xxx(dist_factory): dist = dist_factory({(0,1): 10, ...})"""
    return make_dist
