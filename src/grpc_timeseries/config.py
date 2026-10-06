import os

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
GRPC_PORT = int(os.getenv("GRPC_PORT", "50051"))