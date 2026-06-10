import argparse
from concurrent import futures
from importlib.metadata import version, PackageNotFoundError
from typing import Callable, Any

import grpc

from .config import GRPC_PORT
from .generated import energy_pb2, energy_pb2_grpc
from .redis_store import RedisTimeSeriesStore

# Type alias for output function
OutFn = Callable[[str], Any]

try:
    APP_VERSION = version("energy-grpc-timeseries")
except PackageNotFoundError:
    APP_VERSION = "dev"


class EnergyStoreServicer(energy_pb2_grpc.EnergyStoreServicer):
    def __init__(self, store=None):
        self.store = store or RedisTimeSeriesStore()

    def GetVersion(self, request, context):
        return energy_pb2.VersionReply(version=APP_VERSION)

    def SetEntry(self, request, context):
        e = request.entry
        k = e.key
        self.store.set_point(k.meter_id, k.stream, k.timestamp_ms, e.value)

        return energy_pb2.StatusReply(ok=True, message="set")

    def GetEntry(self, request, context):
        k = request.key
        v = self.store.get_point(k.meter_id, k.stream, k.timestamp_ms)
        if v is None:
            return energy_pb2.GetEntryReply(found=False)
        entry = energy_pb2.Entry(
            key=energy_pb2.EntryKey(meter_id=k.meter_id, stream=k.stream, timestamp_ms=k.timestamp_ms),
            value=v
        )
        return energy_pb2.GetEntryReply(found=True, entry=entry)

    def UpdateEntry(self, request, context):
        e = request.entry
        k = e.key
        if not self.store.exists_point(k.meter_id, k.stream, k.timestamp_ms):
            return energy_pb2.StatusReply(ok=False, message="not_found")
        self.store.set_point(k.meter_id, k.stream, k.timestamp_ms, e.value)

        return energy_pb2.StatusReply(ok=True, message="updated")

    def DeleteEntry(self, request, context):
        k = request.key
        ok = self.store.delete_point(k.meter_id, k.stream, k.timestamp_ms)
        return energy_pb2.StatusReply(ok=ok, message="deleted" if ok else "not_found")

    def QueryRange(self, request, context):
        pts = self.store.query_range(request.meter_id, request.stream, request.start_ms, request.end_ms, request.limit)
        return energy_pb2.QueryRangeReply(
            points=[energy_pb2.QueryPoint(timestamp_ms=ts, value=val) for ts, val in pts]
        )

def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="store_true")
    return parser


def serve(
        args=None,
        grpc_server_factory=None,
        register_servicer=None,
        servicer_factory=None,
        port=None,
        out: OutFn = print):

    args = args or build_parser().parse_args()
    grpc_server_factory = grpc_server_factory or (lambda: grpc.server(futures.ThreadPoolExecutor(max_workers=10)))
    register_servicer = register_servicer or energy_pb2_grpc.add_EnergyStoreServicer_to_server
    servicer_factory = servicer_factory or EnergyStoreServicer
    port = port if port is not None else GRPC_PORT

    if args.version:
        out(APP_VERSION)
        return

    grpc_server = grpc_server_factory()
    servicer = servicer_factory()
    register_servicer(servicer, grpc_server)
    grpc_server.add_insecure_port(f"[::]:{port}")
    grpc_server.start()
    out(f"gRPC EnergyStore running on port {port}")
    grpc_server.wait_for_termination()



if __name__ == "__main__":
    serve()
