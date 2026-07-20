# energy-grpc-timeseries

Small Python gRPC service for storing and querying energy time-series data in Redis.

Each data point is identified by:

- `meter_id`
- `stream`
- `timestamp_ms`

Examples of streams are `consumed_kwh`, `produced_kwh`, `power`, or `voltage`.

## What the service does

The service exposes an `EnergyStore` gRPC API with CRUD-style operations for single points plus a range query:

- `SetEntry` stores or overwrites one point
- `GetEntry` fetches one point by exact key
- `UpdateEntry` updates an existing point and returns `not_found` if it does not exist
- `DeleteEntry` removes an existing point and returns `not_found` if it does not exist
- `QueryRange` returns points for one `(meter_id, stream)` series between two timestamps
- `GetVersion` returns the application version

The API contract is defined in `protos/energy.proto`.

## Data model

A time series is always scoped to the pair `(meter_id, stream)`. Different streams for the same meter are stored separately.

- `EntryKey.timestamp_ms` accepts a protobuf `Timestamp` date-time (for example, `2024-01-15T10:30:00Z`) and the server converts it to **epoch milliseconds** for storage
- `start_ms` and `end_ms` use **epoch milliseconds**
- `start_ms` and `end_ms` are **inclusive**
- `limit = 0` means no limit
- Negative limits are currently treated the same as no limit

Single-record read/update/delete operations report status in the protobuf response payload instead of using gRPC status codes for missing records:

- `GetEntry` returns `found=false` when the point is missing
- `UpdateEntry` and `DeleteEntry` return `ok=false` with `message="not_found"` when the point is missing

## Redis storage layout

`RedisTimeSeriesStore` stores each logical series in two Redis structures:

1. A **sorted set** for timestamp ordering
2. A **hash** for timestamp-to-value lookup

For a `(meter_id, stream)` pair:

- sorted set key: `energy:ts:{meter_id}:{stream}`
- hash key: `energy:val:{meter_id}:{stream}`

Range queries read timestamps from the sorted set and then fetch matching values from the hash. The store also checks for drift between those two Redis structures and raises an error if they disagree about whether a point exists.

## Project structure

| Path | Purpose |
| --- | --- |
| `protos/energy.proto` | gRPC and protobuf contract |
| `src/energy_server/server.py` | gRPC servicer and server startup |
| `src/energy_server/redis_store.py` | Redis-backed time-series storage |
| `src/energy_server/generated/` | checked-in generated protobuf/gRPC bindings |
| `tests/test_server_integration.py` | fast servicer tests using a fake store |
| `tests/test_grpc_client_integration.py` | real gRPC client/server integration tests |
| `tests/test_redis_store.py` | focused Redis store behavior tests |

## Local development

### Install dependencies

```bash
uv sync
```

### Run the server

```bash
make run
```

or:

```bash
uv run python -m energy_server
```

The server reads these environment variables:

- `REDIS_HOST` (default: `redis`)
- `REDIS_PORT` (default: `6379`)
- `GRPC_PORT` (default: `50051`)

### Regenerate protobuf bindings

After editing `protos/*.proto`, regenerate the Python bindings:

```bash
make gen-protos
```

Generated code is written to `src/energy_server/generated/`.

## Testing

Run the full suite:

```bash
uv run pytest
```

Useful targeted commands:

```bash
make test-server
make test-grpc
make test-one TEST=tests/test_server_integration.py::test_query_range_applies_limit
```

## Docker

Start the Redis + gRPC stack:

```bash
docker compose up
```

Build the Python service image:

```bash
docker build -f docker/Dockerfile.python -t energy-server .
```

## Notes on tests

The test suite does not depend on a real Redis instance. The servicer and gRPC integration tests use an in-memory fake store for fast, isolated coverage, while `tests/test_redis_store.py` covers the Redis-backed store behavior directly with mocks.
