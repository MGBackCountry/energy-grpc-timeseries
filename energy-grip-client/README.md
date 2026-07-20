# energy-grpc-client

Standalone Python gRPC client for the energy-grpc-timeseries server.

## Location

This scaffold is stored inside the current cloned repository at:

`/home/runner/work/energy-grpc-timeseries/energy-grpc-timeseries/energy-grip-client`

## Quick start

```bash
cd /home/runner/work/energy-grpc-timeseries/energy-grpc-timeseries/energy-grip-client
uv sync
make gen-protos
python examples/demo.py
```

Start the server separately from the main repository root:

```bash
cd /home/runner/work/energy-grpc-timeseries/energy-grpc-timeseries
docker compose up -d
```
