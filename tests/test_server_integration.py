import types
from unittest.mock import Mock

import pytest

from energy_server import server
from energy_server.generated import energy_pb2


class FakeRedisStore:
    """In-memory fake voor RedisTimeSeriesStore."""

    def __init__(self):
        self.data = {}

    def _key(self, meter_id: str, stream: str, ts_ms: int):
        return (meter_id, stream, ts_ms)

    def set_point(self, meter_id: str, stream: str, ts_ms: int, value: float) -> None:
        self.data[self._key(meter_id, stream, ts_ms)] = float(value)

    def get_point(self, meter_id: str, stream: str, ts_ms: int):
        return self.data.get(self._key(meter_id, stream, ts_ms))

    def exists_point(self, meter_id: str, stream: str, ts_ms: int) -> bool:
        return self._key(meter_id, stream, ts_ms) in self.data

    def delete_point(self, meter_id: str, stream: str, ts_ms: int) -> bool:
        return self.data.pop(self._key(meter_id, stream, ts_ms), None) is not None

    def query_range(self, meter_id: str, stream: str, start_ms: int, end_ms: int, limit: int = 0):
        points = []
        for (m_id, s, ts), value in self.data.items():
            if m_id == meter_id and s == stream and start_ms <= ts <= end_ms:
                points.append((ts, value))
        points.sort(key=lambda item: item[0])
        if limit and limit > 0:
            points = points[:limit]
        return points


@pytest.fixture
def servicer():
    return server.EnergyStoreServicer(store=FakeRedisStore())


# noinspection PyUnresolvedReferences
def make_entry(meter_id="m-1", stream="power", timestamp_ms=1000, value=12.5):
    return energy_pb2.Entry(
        key=energy_pb2.EntryKey(
            meter_id=meter_id,
            stream=stream,
            timestamp_ms=timestamp_ms,
        ),
        value=value,
    )

# noinspection PyUnresolvedReferences
def make_key(meter_id="m-1", stream="power", timestamp_ms=1000):
    return energy_pb2.EntryKey(
        meter_id=meter_id,
        stream=stream,
        timestamp_ms=timestamp_ms,
    )


def test_init_uses_mocked_redis_store():
    fake_store = FakeRedisStore()
    svc = server.EnergyStoreServicer(store=fake_store)
    assert svc.store is fake_store


def test_get_version_returns_app_version(servicer):
    reply = servicer.GetVersion(request=Mock(), context=Mock())

    assert reply.version == server.APP_VERSION


def test_set_entry_persists_value_and_returns_status(servicer):
    request = types.SimpleNamespace(entry=make_entry(value=12.5))

    reply = servicer.SetEntry(request, context=Mock())

    assert reply.ok is True
    assert reply.message == "set"
    assert servicer.store.get_point("m-1", "power", 1000) == pytest.approx(12.5)


def test_get_entry_returns_found_false_when_missing(servicer):
    request = types.SimpleNamespace(
        key=make_key(meter_id="m-404", stream="power", timestamp_ms=9999)
    )

    reply = servicer.GetEntry(request, context=Mock())

    assert reply.found is False


def test_get_entry_returns_entry_when_present(servicer):
    servicer.store.set_point("m-1", "power", 1000, 42.25)
    request = types.SimpleNamespace(
        key=make_key(meter_id="m-1", stream="power", timestamp_ms=1000)
    )

    reply = servicer.GetEntry(request, context=Mock())

    assert reply.found is True
    assert reply.entry.key.meter_id == "m-1"
    assert reply.entry.key.stream == "power"
    assert reply.entry.key.timestamp_ms == 1000
    assert reply.entry.value == pytest.approx(42.25)


def test_update_entry_returns_not_found_when_entry_missing(servicer):
    request = types.SimpleNamespace(
        entry=make_entry(meter_id="m-1", stream="power", timestamp_ms=1000, value=55.0)
    )

    reply = servicer.UpdateEntry(request, context=Mock())

    assert reply.ok is False
    assert reply.message == "not_found"


def test_update_entry_overwrites_existing_value(servicer):
    servicer.store.set_point("m-1", "power", 1000, 10.0)
    request = types.SimpleNamespace(
        entry=make_entry(meter_id="m-1", stream="power", timestamp_ms=1000, value=55.0)
    )

    reply = servicer.UpdateEntry(request, context=Mock())

    assert reply.ok is True
    assert reply.message == "updated"
    assert servicer.store.get_point("m-1", "power", 1000) == pytest.approx(55.0)


def test_delete_entry_returns_not_found_when_missing(servicer):
    request = types.SimpleNamespace(
        key=make_key(meter_id="m-1", stream="power", timestamp_ms=1000)
    )

    reply = servicer.DeleteEntry(request, context=Mock())

    assert reply.ok is False
    assert reply.message == "not_found"


def test_delete_entry_removes_existing_value(servicer):
    servicer.store.set_point("m-1", "power", 1000, 10.0)
    request = types.SimpleNamespace(
        key=make_key(meter_id="m-1", stream="power", timestamp_ms=1000)
    )

    reply = servicer.DeleteEntry(request, context=Mock())

    assert reply.ok is True
    assert reply.message == "deleted"
    assert servicer.store.get_point("m-1", "power", 1000) is None


def test_query_range_returns_points_in_requested_window(servicer):
    servicer.store.set_point("m-1", "power", 1000, 10.0)
    servicer.store.set_point("m-1", "power", 2000, 20.0)
    servicer.store.set_point("m-1", "power", 3000, 30.0)
    servicer.store.set_point("m-1", "voltage", 2000, 230.0)

    request = types.SimpleNamespace(
        meter_id="m-1",
        stream="power",
        start_ms=1500,
        end_ms=3000,
        limit=0,
    )

    reply = servicer.QueryRange(request, context=Mock())

    assert len(reply.points) == 2
    assert reply.points[0].timestamp_ms == 2000
    assert reply.points[0].value == pytest.approx(20.0)
    assert reply.points[1].timestamp_ms == 3000
    assert reply.points[1].value == pytest.approx(30.0)


def test_query_range_applies_limit(servicer):
    servicer.store.set_point("m-1", "power", 1000, 10.0)
    servicer.store.set_point("m-1", "power", 2000, 20.0)
    servicer.store.set_point("m-1", "power", 3000, 30.0)

    request = types.SimpleNamespace(
        meter_id="m-1",
        stream="power",
        start_ms=0,
        end_ms=9999,
        limit=2,
    )

    reply = servicer.QueryRange(request, context=Mock())

    assert len(reply.points) == 2
    assert reply.points[0].timestamp_ms == 1000
    assert reply.points[0].value == pytest.approx(10.0)
    assert reply.points[1].timestamp_ms == 2000
    assert reply.points[1].value == pytest.approx(20.0)


def test_serve_prints_version_and_does_not_start_server(capsys):
    fake_server = Mock(name="grpc_server")
    grpc_server_factory = Mock(name="grpc_server_factory", return_value=fake_server)

    server.serve(
        args=types.SimpleNamespace(version=True),
        grpc_server_factory=grpc_server_factory,
        out=print,
    )

    output = capsys.readouterr().out.strip()
    assert output == server.APP_VERSION
    grpc_server_factory.assert_not_called()

def test_serve_configures_and_starts_grpc_server(capsys):
    fake_store = FakeRedisStore()
    fake_servicer = server.EnergyStoreServicer(store=fake_store)

    fake_server = Mock(name="grpc_server_instance")
    grpc_server_factory = Mock(return_value=fake_server)

    added = {}

    def fake_add_servicer_to_server(servicer, grpc_server):
        added["servicer"] = servicer
        added["grpc_server"] = grpc_server

    server.serve(
        args=types.SimpleNamespace(version=False),
        grpc_server_factory=grpc_server_factory,
        register_servicer=fake_add_servicer_to_server,
        servicer_factory=lambda: fake_servicer,
        port=50051,
    )

    grpc_server_factory.assert_called_once_with()
    fake_server.add_insecure_port.assert_called_once_with("[::]:50051")
    fake_server.start.assert_called_once_with()
    fake_server.wait_for_termination.assert_called_once_with()

    assert added["servicer"] is fake_servicer
    assert added["servicer"].store is fake_store
    assert added["grpc_server"] is fake_server

    output = capsys.readouterr().out.strip()
    assert output == "gRPC EnergyStore running on port 50051"
