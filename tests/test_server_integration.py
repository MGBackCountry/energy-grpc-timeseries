import types
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from energy_server import server
from support import FakeRedisStore, make_entry, make_key


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


def test_set_entry_converts_datetime_timestamp_to_milliseconds(servicer):
    timestamp = server.Timestamp()
    timestamp.FromDatetime(datetime(2024, 1, 15, 10, 30, tzinfo=UTC))
    request = types.SimpleNamespace(
        entry=types.SimpleNamespace(
            key=types.SimpleNamespace(
                meter_id="m-1",
                stream="power",
                timestamp_ms=timestamp,
            ),
            value=12.5,
        )
    )

    reply = servicer.SetEntry(request, context=Mock())

    assert reply.ok is True
    assert servicer.store.get_point("m-1", "power", 1705314600000) == pytest.approx(12.5)


def test_set_entry_is_idempotent_when_value_matches(servicer):
    request = types.SimpleNamespace(entry=make_entry(value=12.5))

    first = servicer.SetEntry(request, context=Mock())
    second = servicer.SetEntry(request, context=Mock())

    assert first.ok is True
    assert first.message == "set"
    assert second.ok is True
    assert second.message == "set"
    assert servicer.store.get_point("m-1", "power", 1000) == pytest.approx(12.5)


def test_set_entry_returns_conflict_when_value_differs(servicer):
    initial_request = types.SimpleNamespace(entry=make_entry(value=12.5))
    conflict_request = types.SimpleNamespace(entry=make_entry(value=99.0))

    first = servicer.SetEntry(initial_request, context=Mock())
    second = servicer.SetEntry(conflict_request, context=Mock())

    assert first.ok is True
    assert second.ok is False
    assert second.message == "conflict"
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
    assert reply.entry.key.timestamp_ms.ToMilliseconds() == 1000
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


def test_query_range_includes_start_and_end_boundaries(servicer):
    servicer.store.set_point("m-1", "power", 1000, 10.0)
    servicer.store.set_point("m-1", "power", 2000, 20.0)
    servicer.store.set_point("m-1", "power", 3000, 30.0)

    request = types.SimpleNamespace(
        meter_id="m-1",
        stream="power",
        start_ms=1000,
        end_ms=3000,
        limit=0,
    )

    reply = servicer.QueryRange(request, context=Mock())

    assert [(point.timestamp_ms, point.value) for point in reply.points] == [
        (1000, pytest.approx(10.0)),
        (2000, pytest.approx(20.0)),
        (3000, pytest.approx(30.0)),
    ]


def test_query_range_treats_negative_limit_as_unlimited(servicer):
    servicer.store.set_point("m-1", "power", 1000, 10.0)
    servicer.store.set_point("m-1", "power", 2000, 20.0)
    servicer.store.set_point("m-1", "power", 3000, 30.0)

    request = types.SimpleNamespace(
        meter_id="m-1",
        stream="power",
        start_ms=0,
        end_ms=9999,
        limit=-5,
    )

    reply = servicer.QueryRange(request, context=Mock())

    assert len(reply.points) == 3
    assert [point.timestamp_ms for point in reply.points] == [1000, 2000, 3000]


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
