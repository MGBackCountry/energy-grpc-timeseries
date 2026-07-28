import types
from datetime import UTC, datetime
from unittest.mock import Mock

import grpc
import pytest

from energy_server import server
from energy_server.generated import energy_pb2_grpc
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

    result = server.serve(
        args=types.SimpleNamespace(version=True),
        grpc_server_factory=grpc_server_factory,
        out=print,
    )

    output = capsys.readouterr().out.strip()
    assert result == 0
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

    result = server.serve(
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
    assert result == 0
    assert output == "gRPC EnergyStore running on port 50051"


def test_serve_routes_client_actions_without_starting_server():
    client_runner = Mock(return_value=0)
    grpc_server_factory = Mock(name="grpc_server_factory")
    original_runner = server._run_client_action
    server._run_client_action = client_runner
    args = types.SimpleNamespace(
        version=False,
        action="get",
        target="localhost:50051",
        meter_id="demo-meter",
        stream="consumed_kwh",
        timestamp_ms=1_725_000_000_000,
        value=None,
    )

    try:
        result = server.serve(args=args, grpc_server_factory=grpc_server_factory)
    finally:
        server._run_client_action = original_runner

    assert result == 0
    client_runner.assert_called_once_with(args, out=print)
    grpc_server_factory.assert_not_called()


def test_build_parser_includes_client_arguments():
    parser = server.build_parser()

    args = parser.parse_args(["--action", "set", "--value", "42.5"])

    assert args.action == "set"
    assert args.value == pytest.approx(42.5)
    assert args.target == "localhost:50051"


def test_build_parser_includes_query_arguments():
    parser = server.build_parser()

    args = parser.parse_args(["--action", "query", "--start-ms", "1000", "--end-ms", "2000", "--limit", "10"])

    assert args.action == "query"
    assert args.start_ms == 1000
    assert args.end_ms == 2000
    assert args.limit == 10


def test_run_client_action_delete(capsys):
    client_mock = Mock()
    delete_reply = Mock(ok=True, message="deleted")
    client_mock.DeleteEntry.return_value = delete_reply

    grpc_channel_mock = Mock()
    grpc_channel_mock.__enter__ = Mock(return_value=grpc_channel_mock)
    grpc_channel_mock.__exit__ = Mock(return_value=False)

    original_channel = grpc.insecure_channel
    grpc.insecure_channel = Mock(return_value=grpc_channel_mock)

    original_ready = grpc.channel_ready_future
    ready_future = Mock()
    ready_future.result = Mock(return_value=None)
    grpc.channel_ready_future = Mock(return_value=ready_future)

    original_stub = energy_pb2_grpc.EnergyStoreStub
    energy_pb2_grpc.EnergyStoreStub = Mock(return_value=client_mock)

    try:
        args = types.SimpleNamespace(
            action="delete",
            target="localhost:50051",
            meter_id="meter-1",
            stream="power",
            timestamp_ms=1000,
        )
        result = server._run_client_action(args)

        assert result == 0
        output = capsys.readouterr().out
        assert "DeleteEntry: ok=True message=deleted" in output
    finally:
        grpc.insecure_channel = original_channel
        grpc.channel_ready_future = original_ready
        energy_pb2_grpc.EnergyStoreStub = original_stub


def test_run_client_action_query(capsys):
    client_mock = Mock()
    point1 = Mock(timestamp_ms=1000, value=10.5)
    point2 = Mock(timestamp_ms=2000, value=20.5)
    query_reply = Mock(points=[point1, point2])
    client_mock.QueryRange.return_value = query_reply

    grpc_channel_mock = Mock()
    grpc_channel_mock.__enter__ = Mock(return_value=grpc_channel_mock)
    grpc_channel_mock.__exit__ = Mock(return_value=False)

    original_channel = grpc.insecure_channel
    grpc.insecure_channel = Mock(return_value=grpc_channel_mock)

    original_ready = grpc.channel_ready_future
    ready_future = Mock()
    ready_future.result = Mock(return_value=None)
    grpc.channel_ready_future = Mock(return_value=ready_future)

    original_stub = energy_pb2_grpc.EnergyStoreStub
    energy_pb2_grpc.EnergyStoreStub = Mock(return_value=client_mock)

    try:
        args = types.SimpleNamespace(
            action="query",
            target="localhost:50051",
            meter_id="meter-1",
            stream="power",
            start_ms=1000,
            end_ms=2000,
            limit=0,
        )
        result = server._run_client_action(args)

        assert result == 0
        output = capsys.readouterr().out
        assert "QueryRange: found 2 points" in output
        assert "timestamp_ms=1000 value=10.5" in output
        assert "timestamp_ms=2000 value=20.5" in output
    finally:
        grpc.insecure_channel = original_channel
        grpc.channel_ready_future = original_ready
        energy_pb2_grpc.EnergyStoreStub = original_stub


def test_run_client_action_version(capsys):
    client_mock = Mock()
    version_reply = Mock(version="1.0.0")
    client_mock.GetVersion.return_value = version_reply

    grpc_channel_mock = Mock()
    grpc_channel_mock.__enter__ = Mock(return_value=grpc_channel_mock)
    grpc_channel_mock.__exit__ = Mock(return_value=False)

    original_channel = grpc.insecure_channel
    grpc.insecure_channel = Mock(return_value=grpc_channel_mock)

    original_ready = grpc.channel_ready_future
    ready_future = Mock()
    ready_future.result = Mock(return_value=None)
    grpc.channel_ready_future = Mock(return_value=ready_future)

    original_stub = energy_pb2_grpc.EnergyStoreStub
    energy_pb2_grpc.EnergyStoreStub = Mock(return_value=client_mock)

    try:
        args = types.SimpleNamespace(
            action="version",
            target="localhost:50051",
            meter_id="demo-meter",
            stream="consumed_kwh",
            timestamp_ms=1_725_000_000_000,
        )
        result = server._run_client_action(args)

        assert result == 0
        output = capsys.readouterr().out
        assert "Version: 1.0.0" in output
    finally:
        grpc.insecure_channel = original_channel
        grpc.channel_ready_future = original_ready
        energy_pb2_grpc.EnergyStoreStub = original_stub


def test_run_client_action_query_missing_start_ms():
    args = types.SimpleNamespace(
        action="query",
        target="localhost:50051",
        meter_id="meter-1",
        stream="power",
        start_ms=None,
        end_ms=2000,
        limit=0,
    )
    
    result = server._run_client_action(args, err=lambda x: None)
    
    assert result == 1


def test_run_client_action_query_missing_end_ms():
    args = types.SimpleNamespace(
        action="query",
        target="localhost:50051",
        meter_id="meter-1",
        stream="power",
        start_ms=1000,
        end_ms=None,
        limit=0,
    )
    
    result = server._run_client_action(args, err=lambda x: None)
    
    assert result == 1
