#!/bin/bash

# ScyllaDB处理服务构建脚本
echo "Building ScyllaDB processing service..."

# 构建Docker镜像
docker build -t zhxgharbor.istarshine.com/dflow/draw_and_to_scylla_mq:0.0.1 \
    -f dockerfiles/Dockerfile_draw_and_to_scylla_mq .

# 推送到镜像仓库
docker push zhxgharbor.istarshine.com/dflow/draw_and_to_scylla_mq:0.0.1

echo "ScyllaDB processing service build completed!"