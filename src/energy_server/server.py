import argparse
from concurrent import futures
from importlib.metadata import version

APP_VERSION = version("energy-grpc-timeseries")

import grpc

from energy_server.config import GRPC_PORT
from energy_server.generated import energy_pb2, energy_pb2_grpc
from energy_server.redis_store import RedisTimeSeriesStore


class EnergyStoreServicer(energy_pb2_grpc.EnergyStoreServicer):
    def __init__(self):
        self.store = RedisTimeSeriesStore()

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


def serve():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args()
    if args.version:
        print(version("energy-grpc-timeseries"))
        return

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    energy_pb2_grpc.add_EnergyStoreServicer_to_server(EnergyStoreServicer(), server)
    server.add_insecure_port(f"[::]:{GRPC_PORT}")
    server.start()
    print(f"gRPC EnergyStore running on port {GRPC_PORT}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
