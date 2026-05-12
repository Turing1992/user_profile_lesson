#!/bin/bash

# ScyllaDB处理服务构建脚本
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Building ScyllaDB processing service..."

docker build -t zhxgharbor.istarshine.com/dflow/draw_and_to_scylla_mq:0.0.1 \
    -f "$SCRIPT_DIR/dockerfiles/Dockerfile_draw_and_to_scylla_mq" "$SCRIPT_DIR"

docker push zhxgharbor.istarshine.com/dflow/draw_and_to_scylla_mq:0.0.1

echo "ScyllaDB processing service build completed!"
