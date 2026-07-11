"""Real gRPC client integration tests."""

from concurrent import futures

import grpc
import pytest

from energy_server import server
from energy_server.generated import energy_pb2, energy_pb2_grpc
from google.protobuf import empty_pb2

from support import FakeRedisStore


@pytest.fixture
def grpc_server_and_channel():
    """
    Start a real gRPC server on an ephemeral port and provide a client channel.
    Cleanup is handled automatically after the test completes.
    """
    fake_store = FakeRedisStore()
    servicer = server.EnergyStoreServicer(store=fake_store)

    grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    energy_pb2_grpc.add_EnergyStoreServicer_to_server(servicer, grpc_server)
    port = grpc_server.add_insecure_port("127.0.0.1:0")
    grpc_server.start()

    channel = grpc.insecure_channel(f"127.0.0.1:{port}")
    grpc.channel_ready_future(channel).result(timeout=5)

    yield grpc_server, channel, fake_store

    channel.close()
    grpc_server.stop(grace=1)


@pytest.fixture
def client(grpc_server_and_channel):
    """Provide a gRPC client stub."""
    _, channel, _ = grpc_server_and_channel
    return energy_pb2_grpc.EnergyStoreStub(channel)


class TestGrpcClientIntegration:
    """Integration tests using real gRPC client/server communication."""

    def test_get_version_via_grpc(self, client):
        """Test GetVersion RPC call."""
        response = client.GetVersion(empty_pb2.Empty())

        assert response.version == server.APP_VERSION

    def test_set_entry_via_grpc(self, client):
        """Test SetEntry RPC call with real energy meter data."""
        # Simulate meter data: home consumption at 2024-01-15 10:30:00 UTC
        timestamp_ms = 1705318200000  # 2024-01-15 10:30:00 UTC

        request = energy_pb2.SetEntryRequest(
            entry=energy_pb2.Entry(
                key=energy_pb2.EntryKey(
                    meter_id="home-meter-001",
                    stream="consumed_kwh",
                    timestamp_ms=timestamp_ms,
                ),
                value=42.5,  # 42.5 kWh consumed
            )
        )

        response = client.SetEntry(request)

        assert response.ok is True
        assert response.message == "set"

    def test_get_entry_via_grpc(self, client, grpc_server_and_channel):
        """Test GetEntry RPC call."""
        _, _, fake_store = grpc_server_and_channel
        timestamp_ms = 1705318200000
        meter_id = "home-meter-001"
        stream = "consumed_kwh"
        value = 42.5

        # Set data directly in the store
        fake_store.set_point(meter_id, stream, timestamp_ms, value)

        # Retrieve via gRPC
        request = energy_pb2.GetEntryRequest(
            key=energy_pb2.EntryKey(
                meter_id=meter_id,
                stream=stream,
                timestamp_ms=timestamp_ms,
            )
        )

        response = client.GetEntry(request)

        assert response.found is True
        assert response.entry.key.meter_id == meter_id
        assert response.entry.key.stream == stream
        assert response.entry.key.timestamp_ms == timestamp_ms
        assert response.entry.value == pytest.approx(value)

    def test_get_entry_not_found_via_grpc(self, client):
        """Test GetEntry returns found=False for missing data."""
        request = energy_pb2.GetEntryRequest(
            key=energy_pb2.EntryKey(
                meter_id="nonexistent-meter",
                stream="power",
                timestamp_ms=9999999,
            )
        )

        response = client.GetEntry(request)

        assert response.found is False

    def test_update_entry_via_grpc(self, client, grpc_server_and_channel):
        """Test UpdateEntry RPC call."""
        _, _, fake_store = grpc_server_and_channel
        timestamp_ms = 1705318200000
        meter_id = "home-meter-001"
        stream = "produced_kwh"

        # Set initial value
        fake_store.set_point(meter_id, stream, timestamp_ms, 10.0)

        # Update via gRPC
        request = energy_pb2.UpdateEntryRequest(
            entry=energy_pb2.Entry(
                key=energy_pb2.EntryKey(
                    meter_id=meter_id,
                    stream=stream,
                    timestamp_ms=timestamp_ms,
                ),
                value=25.5,  # Updated value
            )
        )

        response = client.UpdateEntry(request)

        assert response.ok is True
        assert response.message == "updated"

        # Verify the update
        get_request = energy_pb2.GetEntryRequest(
            key=energy_pb2.EntryKey(
                meter_id=meter_id,
                stream=stream,
                timestamp_ms=timestamp_ms,
            )
        )
        get_response = client.GetEntry(get_request)
        assert get_response.entry.value == pytest.approx(25.5)

    def test_update_entry_not_found_via_grpc(self, client):
        """Test UpdateEntry fails when entry doesn't exist."""
        request = energy_pb2.UpdateEntryRequest(
            entry=energy_pb2.Entry(
                key=energy_pb2.EntryKey(
                    meter_id="nonexistent",
                    stream="power",
                    timestamp_ms=1000,
                ),
                value=50.0,
            )
        )

        response = client.UpdateEntry(request)

        assert response.ok is False
        assert response.message == "not_found"

    def test_delete_entry_via_grpc(self, client, grpc_server_and_channel):
        """Test DeleteEntry RPC call."""
        _, _, fake_store = grpc_server_and_channel
        timestamp_ms = 1705318200000
        meter_id = "home-meter-001"
        stream = "consumed_kwh"

        # Set initial value
        fake_store.set_point(meter_id, stream, timestamp_ms, 42.5)

        # Delete via gRPC
        request = energy_pb2.DeleteEntryRequest(
            key=energy_pb2.EntryKey(
                meter_id=meter_id,
                stream=stream,
                timestamp_ms=timestamp_ms,
            )
        )

        response = client.DeleteEntry(request)

        assert response.ok is True
        assert response.message == "deleted"

        # Verify deletion
        get_request = energy_pb2.GetEntryRequest(
            key=energy_pb2.EntryKey(
                meter_id=meter_id,
                stream=stream,
                timestamp_ms=timestamp_ms,
            )
        )
        get_response = client.GetEntry(get_request)
        assert get_response.found is False

    def test_delete_entry_not_found_via_grpc(self, client):
        """Test DeleteEntry fails when entry doesn't exist."""
        request = energy_pb2.DeleteEntryRequest(
            key=energy_pb2.EntryKey(
                meter_id="nonexistent",
                stream="power",
                timestamp_ms=1000,
            )
        )

        response = client.DeleteEntry(request)

        assert response.ok is False
        assert response.message == "not_found"

    def test_query_range_with_real_meter_data(self, client, grpc_server_and_channel):
        """Test QueryRange RPC with realistic energy meter dataset."""
        _, _, fake_store = grpc_server_and_channel

        # Simulate a day of energy consumption data for home meter
        # Data points every hour for a 24-hour period starting at 2024-01-15 00:00:00 UTC
        base_timestamp = 1705276800000  # 2024-01-15 00:00:00 UTC

        meter_id = "home-meter-001"
        stream = "consumed_kwh"

        # Realistic hourly power consumption pattern (kWh per hour)
        # Lower consumption at night, peak during morning and evening
        hourly_consumption = [
            0.5,   # 00:00 - night
            0.4,   # 01:00 - night
            0.3,   # 02:00 - night
            2.1,   # 03:00 - early morning heating
            2.5,   # 04:00 - morning peak
            2.8,   # 05:00 - morning peak
            3.2,   # 06:00 - breakfast, heating
            2.9,   # 07:00 - morning
            1.5,   # 08:00 - daytime low
            1.2,   # 09:00 - daytime low
            1.3,   # 10:00 - daytime
            1.4,   # 11:00 - daytime
            2.0,   # 12:00 - lunch
            1.8,   # 13:00 - afternoon
            1.6,   # 14:00 - afternoon
            1.7,   # 15:00 - afternoon
            2.2,   # 16:00 - afternoon
            2.8,   # 17:00 - evening peak (dinner prep)
            3.5,   # 18:00 - evening peak
            3.2,   # 19:00 - evening
            2.9,   # 20:00 - evening
            2.5,   # 21:00 - night activity
            1.8,   # 22:00 - winding down
            0.8,   # 23:00 - night
        ]

        # Populate fake store with hourly data
        for hour, consumption in enumerate(hourly_consumption):
            timestamp = base_timestamp + (hour * 3600 * 1000)  # Convert to milliseconds
            fake_store.set_point(meter_id, stream, timestamp, consumption)

        # Query the entire day
        start_timestamp = base_timestamp
        end_timestamp = base_timestamp + (24 * 3600 * 1000) - 1  # End of day

        request = energy_pb2.QueryRangeRequest(
            meter_id=meter_id,
            stream=stream,
            start_ms=start_timestamp,
            end_ms=end_timestamp,
            limit=0,  # No limit
        )

        response = client.QueryRange(request)

        # Verify we got all 24 data points
        assert len(response.points) == 24

        # Verify first and last points
        assert response.points[0].timestamp_ms == base_timestamp
        assert response.points[0].value == pytest.approx(0.5)  # First hour consumption

        assert response.points[-1].timestamp_ms == base_timestamp + (23 * 3600 * 1000)
        assert response.points[-1].value == pytest.approx(0.8)  # Last hour consumption

        # Verify the peak hour (18:00, index 18)
        peak_point = response.points[18]
        assert peak_point.timestamp_ms == base_timestamp + (18 * 3600 * 1000)
        assert peak_point.value == pytest.approx(3.5)

        # Calculate total daily consumption
        total_consumption = sum(point.value for point in response.points)
        assert total_consumption == pytest.approx(sum(hourly_consumption))

    def test_query_range_with_limit(self, client, grpc_server_and_channel):
        """Test QueryRange with limit parameter."""
        _, _, fake_store = grpc_server_and_channel

        meter_id = "home-meter-002"
        stream = "produced_kwh"
        base_timestamp = 1705276800000

        # Add 10 data points
        for i in range(10):
            timestamp = base_timestamp + (i * 3600 * 1000)
            fake_store.set_point(meter_id, stream, timestamp, float(i + 1) * 0.5)

        # Query with limit=5
        request = energy_pb2.QueryRangeRequest(
            meter_id=meter_id,
            stream=stream,
            start_ms=base_timestamp,
            end_ms=base_timestamp + (10 * 3600 * 1000),
            limit=5,
        )

        response = client.QueryRange(request)

        assert len(response.points) == 5
        assert response.points[0].value == pytest.approx(0.5)
        assert response.points[4].value == pytest.approx(2.5)

    def test_query_range_includes_boundary_timestamps(self, client, grpc_server_and_channel):
        """Test QueryRange includes points exactly on both boundaries."""
        _, _, fake_store = grpc_server_and_channel

        meter_id = "home-meter-003"
        stream = "consumed_kwh"
        fake_store.set_point(meter_id, stream, 1000, 1.0)
        fake_store.set_point(meter_id, stream, 2000, 2.0)
        fake_store.set_point(meter_id, stream, 3000, 3.0)

        request = energy_pb2.QueryRangeRequest(
            meter_id=meter_id,
            stream=stream,
            start_ms=1000,
            end_ms=3000,
            limit=0,
        )

        response = client.QueryRange(request)

        assert [(point.timestamp_ms, point.value) for point in response.points] == [
            (1000, pytest.approx(1.0)),
            (2000, pytest.approx(2.0)),
            (3000, pytest.approx(3.0)),
        ]

    def test_query_range_negative_limit_behaves_as_unlimited(self, client, grpc_server_and_channel):
        """Test QueryRange treats negative limits like no limit."""
        _, _, fake_store = grpc_server_and_channel

        meter_id = "home-meter-004"
        stream = "produced_kwh"
        for index, value in enumerate((0.5, 1.0, 1.5), start=1):
            fake_store.set_point(meter_id, stream, index * 1000, value)

        request = energy_pb2.QueryRangeRequest(
            meter_id=meter_id,
            stream=stream,
            start_ms=0,
            end_ms=9999,
            limit=-3,
        )

        response = client.QueryRange(request)

        assert len(response.points) == 3
        assert [point.timestamp_ms for point in response.points] == [1000, 2000, 3000]

    def test_query_range_empty_result(self, client):
        """Test QueryRange returns empty list when no data matches."""
        request = energy_pb2.QueryRangeRequest(
            meter_id="nonexistent-meter",
            stream="power",
            start_ms=1000,
            end_ms=2000,
            limit=0,
        )

        response = client.QueryRange(request)

        assert len(response.points) == 0

    def test_complete_workflow_multi_meter(self, client, grpc_server_and_channel):
        """
        Test a complete workflow with multiple meters and streams.
        Simulates a real-world scenario with multiple households.
        """
        _, _, fake_store = grpc_server_and_channel

        timestamp = 1705318200000  # 2024-01-15 10:30:00 UTC

        # Household 1: Power consumption
        meter1_consumed_request = energy_pb2.SetEntryRequest(
            entry=energy_pb2.Entry(
                key=energy_pb2.EntryKey(
                    meter_id="household-1",
                    stream="consumed_kwh",
                    timestamp_ms=timestamp,
                ),
                value=2.5,
            )
        )
        response1 = client.SetEntry(meter1_consumed_request)
        assert response1.ok is True

        # Household 1: Solar production
        meter1_produced_request = energy_pb2.SetEntryRequest(
            entry=energy_pb2.Entry(
                key=energy_pb2.EntryKey(
                    meter_id="household-1",
                    stream="produced_kwh",
                    timestamp_ms=timestamp,
                ),
                value=1.2,
            )
        )
        response2 = client.SetEntry(meter1_produced_request)
        assert response2.ok is True

        # Household 2: Power consumption
        meter2_consumed_request = energy_pb2.SetEntryRequest(
            entry=energy_pb2.Entry(
                key=energy_pb2.EntryKey(
                    meter_id="household-2",
                    stream="consumed_kwh",
                    timestamp_ms=timestamp,
                ),
                value=3.1,
            )
        )
        response3 = client.SetEntry(meter2_consumed_request)
        assert response3.ok is True

        # Query household 1 consumption
        query_h1 = energy_pb2.QueryRangeRequest(
            meter_id="household-1",
            stream="consumed_kwh",
            start_ms=timestamp - 1000,
            end_ms=timestamp + 1000,
            limit=0,
        )
        result_h1 = client.QueryRange(query_h1)
        assert len(result_h1.points) == 1
        assert result_h1.points[0].value == pytest.approx(2.5)

        # Query household 1 production
        query_h1_prod = energy_pb2.QueryRangeRequest(
            meter_id="household-1",
            stream="produced_kwh",
            start_ms=timestamp - 1000,
            end_ms=timestamp + 1000,
            limit=0,
        )
        result_h1_prod = client.QueryRange(query_h1_prod)
        assert len(result_h1_prod.points) == 1
        assert result_h1_prod.points[0].value == pytest.approx(1.2)

        # Query household 2 consumption
        query_h2 = energy_pb2.QueryRangeRequest(
            meter_id="household-2",
            stream="consumed_kwh",
            start_ms=timestamp - 1000,
            end_ms=timestamp + 1000,
            limit=0,
        )
        result_h2 = client.QueryRange(query_h2)
        assert len(result_h2.points) == 1
        assert result_h2.points[0].value == pytest.approx(3.1)
