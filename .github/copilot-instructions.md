# Copilot Instructions for `energy-grpc-timeseries`

## Build, test, and run commands

- Install dependencies with `uv sync`.
- Regenerate protobuf/gRPC bindings after editing `protos/*.proto` with `make gen-protos`.
- Run the test suite with `uv run pytest`.
- Run the lightweight servicer tests with `uv run pytest tests/test_server_integration.py`.
- Run the real gRPC integration tests with `uv run pytest tests/test_grpc_client_integration.py`.
- Run Redis store tests with `uv run pytest tests/test_redis_store.py`.
- Run a single test with `uv run pytest tests/test_server_integration.py::test_query_range_applies_limit`.
- Start the full Redis + gRPC stack with `docker compose up`.
- Build the container image with `docker build -f docker/Dockerfile.python -t energy-server .`.

There is no dedicated lint or type-check command configured in `pyproject.toml` or `Makefile`.

## High-level architecture

This repository is a small Python gRPC service backed by Redis.

- `protos/energy.proto` defines the wire contract for the `EnergyStore` service.
- Generated protobuf and gRPC bindings live in `src/energy_server/generated/` and are consumed by the runtime server code in `src/energy_server/server.py`. They are ignored by Git (other than `__init__.py`) and must be regenerated after contract changes.
- `energy_server.server:serve` is the package entry point. It reads `GRPC_PORT` from `config.py`, creates the gRPC server, and registers `EnergyStoreServicer`; the Compose service supplies the Redis host and port through environment variables.
- `EnergyStoreServicer` depends on the `TimeSeriesStore` protocol rather than a concrete Redis client. Each RPC translates protobuf requests into store operations and maps results back into protobuf replies, which lets direct-servicer and gRPC-client tests inject `FakeRedisStore`.
- `RedisTimeSeriesStore` stores one logical time series per `(meter_id, stream)` pair using two Redis structures: a sorted set for timestamp ordering and a hash for timestamp-to-value lookup. Range queries read ordered timestamps from the sorted set, then fetch values from the hash.
- Docker Compose is the end-to-end runtime shape: a Redis container plus the Python gRPC server container, with the server resolving Redis by service name `redis`.

## Key conventions

- Timestamp handling is always epoch milliseconds (`timestamp_ms`, `start_ms`, `end_ms`) and range queries are inclusive on both ends.
- A time series is keyed by the pair `(meter_id, stream)` everywhere: in protobuf messages, in the Redis key layout, and in tests. Do not collapse different streams for the same meter into one series.
- CRUD-style RPCs return status via protobuf payloads instead of gRPC status errors. In particular, missing records are modeled as `found=False` for `GetEntry` and `ok=False` with message `not_found` for update/delete paths.
- `SetEntry` is idempotent only when a duplicate has the same value; a duplicate timestamp with a different value returns `ok=False, message="conflict"` and does not overwrite the stored point. Use `UpdateEntry` for intentional replacement.
- Tests do not use a real Redis instance. `tests/test_server_integration.py` provides `FakeRedisStore`, and both the direct servicer tests and the real gRPC client/server tests rely on that fake store for fast, isolated coverage.
- The Redis store must preserve its sorted-set/hash pair as one logical record. Its existence, idempotent-write, and delete paths detect disagreements and raise `RedisStoreDriftError` rather than silently repairing or ignoring drift.
- Keep generated-code workflow in mind when touching protobufs: tests work because pytest adds both `src` and `src/energy_server/generated` to `PYTHONPATH`, while the Docker build also patches `src/energy_server/generated/energy_pb2_grpc.py` from `import energy_pb2` to a relative import before installing the package.
