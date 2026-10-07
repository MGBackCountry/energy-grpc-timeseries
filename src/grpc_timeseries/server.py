import argparse
from collections.abc import Callable
from concurrent import futures
from typing import Any

import grpc
from google.protobuf import empty_pb2
from google.protobuf.timestamp_pb2 import Timestamp

from . import __version__
from .cli.client import (
    _build_entry,
    _client_build_entry,
    _format_timestamp,
    _format_timestamp_ms,
    _parse_datetime,
    _run_client_action,
    _timestamp_from_datetime,
    _timestamp_from_milliseconds,
    _timestamp_to_milliseconds,
    build_parser,
)
from .config import GRPC_PORT
from .generated import timeseries_pb2, timeseries_pb2_grpc
from .service.timeseries_store import APP_VERSION, TimeSeriesServicer, Point, TimeSeriesStore
from .store.redis_time_series_store import PointConflictError, RedisStoreDriftError, RedisTimeSeriesStore

OutFn = Callable[[str], Any]
DEFAULT_MAX_WORKERS = 10


def _default_grpc_server_factory() -> grpc.Server:
    return grpc.server(futures.ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS))


def serve(
    args: argparse.Namespace | None = None,
    grpc_server_factory: Callable[[], grpc.Server] | None = None,
    register_servicer: Callable[[TimeSeriesServicer, grpc.Server], None] | None = None,
    servicer_factory: Callable[[], TimeSeriesServicer] | None = None,
    port: int | None = None,
    out: OutFn = print,
) -> int:
    args = args or build_parser().parse_args()
    grpc_server_factory = grpc_server_factory or _default_grpc_server_factory
    register_servicer = register_servicer or timeseries_pb2_grpc.add_TimeSeriesServicer_to_server
    servicer_factory = servicer_factory or TimeSeriesServicer
    port = port if port is not None else GRPC_PORT

    if getattr(args, "version", False):
        out(APP_VERSION)
        return 0

    action = getattr(args, "action", "serve")
    if action in {"get", "set", "update", "delete", "query", "version"}:
        return _run_client_action(args, out=out)

    grpc_server = grpc_server_factory()
    servicer = servicer_factory()
    register_servicer(servicer, grpc_server)
    grpc_server.add_insecure_port(f"[::]:{port}")
    grpc_server.start()
    out(f"gRPC TimeSeries running on port {port}")
    grpc_server.wait_for_termination()
    return 0


__all__ = [
    "APP_VERSION",
    "DEFAULT_MAX_WORKERS",
    "TimeSeriesServicer",
    "OutFn",
    "Point",
    "PointConflictError",
    "RedisStoreDriftError",
    "RedisTimeSeriesStore",
    "TimeSeriesStore",
    "Timestamp",
    "__version__",
    "_build_entry",
    "_client_build_entry",
    "_default_grpc_server_factory",
    "_format_timestamp",
    "_format_timestamp_ms",
    "_parse_datetime",
    "_run_client_action",
    "_timestamp_from_datetime",
    "_timestamp_from_milliseconds",
    "_timestamp_to_milliseconds",
    "build_parser",
    "empty_pb2",
    "timeseries_pb2",
    "timeseries_pb2_grpc",
    "grpc",
    "serve",
]

