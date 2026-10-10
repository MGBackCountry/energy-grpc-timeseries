import pytest

from grpc_timeseries import server
from support import FakeRedisStore


@pytest.fixture
def servicer() -> server.TimeSeriesServicer:
    return server.TimeSeriesServicer(store=FakeRedisStore())
