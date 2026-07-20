SHELL := /bin/bash

UV := uv
PYTHON := python

PROTO_DIR := protos
GEN_DIR := generated
STAMP := $(GEN_DIR)/.protos.stamp
PROTO_FILES := $(wildcard $(PROTO_DIR)/*.proto)

.PHONY: help install gen-protos clean

help:
	@echo "Available targets:"
	@echo "  install     Install dependencies with uv"
	@echo "  gen-protos  Regenerate protobuf/gRPC bindings"
	@echo "  clean       Remove generated protobuf outputs"

install:
	$(UV) sync

gen-protos: $(STAMP)

$(STAMP): $(PROTO_FILES)
	@echo "Protos changed -> regenerating..."
	$(UV) run $(PYTHON) -m grpc_tools.protoc \
		-I $(PROTO_DIR) \
		--python_out=$(GEN_DIR) \
		--grpc_python_out=$(GEN_DIR) \
		$(PROTO_DIR)/*.proto
	sed -i 's/^import energy_pb2/from . import energy_pb2/' $(GEN_DIR)/energy_pb2_grpc.py
	@touch $(STAMP)

clean:
	find $(GEN_DIR) -type f -name "*.py" ! -name "__init__.py" -delete
	find $(GEN_DIR) -type f -name "*.pyi" -delete
	rm -f $(STAMP)
