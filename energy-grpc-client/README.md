# energy-grpc-client

Standalone Python gRPC client for the energy-grpc-timeseries server.

## Location

This scaffold is stored inside the current cloned repository at:

`energy-grpc-client`

## Quick start

```bash
cd energy-grpc-client
uv sync
make gen-protos
python examples/demo.py
```

Start the server separately from the main repository root:

```bash
cd ..
docker compose up -d
```
