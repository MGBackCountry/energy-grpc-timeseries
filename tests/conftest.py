import pytest

from grpc_timeseries import server
from support import FakeRedisStore


@pytest.fixture
def servicer() -> server.EnergyStoreServicer:
    return server.EnergyStoreServicer(store=FakeRedisStore())
