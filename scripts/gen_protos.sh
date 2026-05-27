#!/usr/bin/env bash
set -e

python -m grpc_tools.protoc \
  -I./protos \
  --python_out=./src/energy_server/generated \
  --grpc_python_out=./src/energy_server/generated \
  ./protos/energy.proto