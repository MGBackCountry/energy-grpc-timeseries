# gRPC Client Integration Tests

This document describes the real gRPC client integration tests for the energy-grpc-timeseries service.

## Overview

The integration tests in `tests/test_grpc_client_integration.py` test the full gRPC stack with real client-server communication. Unlike unit tests that mock the server, these tests:

- Start a real gRPC server in a background thread
- Create a real gRPC client connection
- Execute actual RPC calls over the network
- Use realistic energy meter data

## Test Coverage

### 1. **test_get_version_via_grpc**
Tests the `GetVersion` RPC call, which returns the application version.

```python
# Verifies that the server responds with the correct version
response = client.GetVersion(empty_pb2.Empty())
assert response.version == server.APP_VERSION
```

### 2. **test_set_entry_via_grpc**
Tests setting energy meter data via the `SetEntry` RPC.

```python
# Store 42.5 kWh consumption at a specific timestamp
request = energy_pb2.SetEntryRequest(
    entry=energy_pb2.Entry(
        key=energy_pb2.EntryKey(
            meter_id="home-meter-001",
            stream="consumed_kwh",
            timestamp_ms=1705318200000,
        ),
        value=42.5,
    )
)
response = client.SetEntry(request)
assert response.ok is True
```

### 3. **test_get_entry_via_grpc**
Tests retrieving a single energy meter data point via `GetEntry` RPC.

```python
# Retrieve previously stored consumption data
request = energy_pb2.GetEntryRequest(
    key=energy_pb2.EntryKey(
        meter_id="home-meter-001",
        stream="consumed_kwh",
        timestamp_ms=1705318200000,
    )
)
response = client.GetEntry(request)
assert response.found is True
assert response.entry.value == pytest.approx(42.5)
```

### 4. **test_get_entry_not_found_via_grpc**
Tests that `GetEntry` correctly returns `found=False` when data doesn't exist.

### 5. **test_update_entry_via_grpc**
Tests updating existing meter data via `UpdateEntry` RPC.

```python
# Update solar production value from 10.0 to 25.5 kWh
request = energy_pb2.UpdateEntryRequest(
    entry=energy_pb2.Entry(
        key=energy_pb2.EntryKey(meter_id="home-meter-001", stream="produced_kwh", ...),
        value=25.5,
    )
)
response = client.UpdateEntry(request)
assert response.ok is True
assert response.message == "updated"
```

### 6. **test_update_entry_not_found_via_grpc**
Tests that `UpdateEntry` fails correctly when trying to update non-existent data.

### 7. **test_delete_entry_via_grpc**
Tests deleting meter data via `DeleteEntry` RPC.

```python
# Delete previously stored data
response = client.DeleteEntry(request)
assert response.ok is True
assert response.message == "deleted"
```

### 8. **test_delete_entry_not_found_via_grpc**
Tests that `DeleteEntry` fails correctly when trying to delete non-existent data.

### 9. **test_query_range_with_real_meter_data** ⭐
This is the most comprehensive test, simulating a **24-hour energy consumption profile** for a household.

```python
# Realistic hourly consumption pattern for a day
hourly_consumption = [
    0.5,   # 00:00 - night
    0.4,   # 01:00 - night
    # ... (peak during morning and evening)
    3.5,   # 18:00 - evening peak
    # ...
    0.8,   # 23:00 - night
]

# Query all 24 hourly data points
response = client.QueryRange(request)
assert len(response.points) == 24
assert response.points[18].value == pytest.approx(3.5)  # Evening peak
total = sum(p.value for p in response.points)
assert total == pytest.approx(sum(hourly_consumption))
```

**Data Pattern**: The test uses realistic energy consumption patterns:
- **Night hours (00:00-07:00 & 22:00-23:59)**: Low consumption (0.3-2.9 kWh)
- **Morning peak (04:00-07:00)**: Higher due to heating and breakfast
- **Daytime (08:00-16:00)**: Stable, lower consumption (1.2-1.7 kWh)
- **Evening peak (17:00-20:00)**: Highest consumption (2.8-3.5 kWh) due to dinner prep and heating

### 10. **test_query_range_with_limit**
Tests the `QueryRange` RPC with a limit parameter.

```python
# Add 10 data points, query with limit=5
request = energy_pb2.QueryRangeRequest(
    meter_id="home-meter-002",
    stream="produced_kwh",
    start_ms=base_timestamp,
    end_ms=base_timestamp + (10 * 3600 * 1000),
    limit=5,  # Only return first 5 points
)
response = client.QueryRange(request)
assert len(response.points) == 5
```

### 11. **test_query_range_empty_result**
Tests that `QueryRange` correctly returns an empty list when no data matches.

### 12. **test_complete_workflow_multi_meter** ⭐
Complete end-to-end workflow simulating **multiple households with different streams**.

```python
# Household 1: Track both consumption and solar production
SetEntry(household-1, consumed_kwh, 2.5)    # Consuming 2.5 kWh
SetEntry(household-1, produced_kwh, 1.2)    # Producing 1.2 kWh (solar)

# Household 2: Track consumption only
SetEntry(household-2, consumed_kwh, 3.1)    # Consuming 3.1 kWh

# Query each household and stream independently
query_h1_consumed → [2.5]
query_h1_produced → [1.2]
query_h2_consumed → [3.1]
```

## Running the Tests

### Run all integration tests:
```bash
python -m pytest tests/test_grpc_client_integration.py -v
```

### Run a specific test:
```bash
python -m pytest tests/test_grpc_client_integration.py::TestGrpcClientIntegration::test_query_range_with_real_meter_data -v
```

### Run all tests (unit + integration):
```bash
python -m pytest tests/ -v
```

### Run with coverage:
```bash
python -m pytest tests/test_grpc_client_integration.py --cov=energy_server --cov-report=html
```

## Key Features

✅ **Real gRPC Communication**: Tests use actual synchronous gRPC client/server communication over localhost:<br>
✅ **Realistic Data**: Energy meter simulations with realistic consumption patterns<br>
✅ **Full CRUD Operations**: Tests all Create, Read, Update, Delete operations<br>
✅ **Time Series Queries**: Tests range queries with filters and limits<br>
✅ **Multi-Meter Scenarios**: Tests handling multiple meters and data streams simultaneously<br>
✅ **Error Handling**: Tests both success and failure scenarios<br>
✅ **Fixtures**: Automatic server lifecycle management with pytest fixtures<br>

## Data Model

The tests use the following energy meter data model:

```protobuf
message EntryKey {
  string meter_id          // e.g., "home-meter-001", "household-1"
  string stream            // e.g., "consumed_kwh", "produced_kwh"
  int64 timestamp_ms       // milliseconds since epoch
}

message Entry {
  EntryKey key
  double value             // energy value in kWh
}
```

### Example Scenarios:
- **meter_id**: `"home-meter-001"`, `"household-1"`, `"apartment-2B"`
- **stream**: `"consumed_kwh"` (grid consumption), `"produced_kwh"` (solar production)
- **timestamp_ms**: `1705318200000` (2024-01-15 10:30:00 UTC)
- **value**: `42.5` kWh

## Architecture

```
Test → gRPC Client Stub
           ↓ (synchronous channel)
        gRPC Server
           ↓
     EnergyStoreServicer
           ↓
      FakeRedisStore (in-memory)
```

The tests use a `FakeRedisStore` (in-memory) instead of a real Redis instance, making tests:
- Fast (no network I/O)
- Isolated (no external dependencies)
- Reproducible (deterministic)

## Notes

- Tests run on port `50052` to avoid conflicts with the production server (port `50051`)
- The `grpc_server_and_channel` fixture automatically manages server lifecycle
- All tests use in-memory data stores for isolation and speed
- Tests are synchronized (no async/await), making them straightforward and readable

