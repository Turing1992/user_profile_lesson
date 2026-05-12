#!/bin/bash
# 账号画像系统 Docker 构建脚本
# 从 user_profile/ 目录执行

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ===== 旧镜像（已发布，不重复推送，需要时取消注释） =====
# docker build --platform=linux/amd64 -t zhxgharbor.istarshine.com/dflow/draw_and_to_es:0.0.3 \
#   -f "$SCRIPT_DIR/dockerfiles/Dockerfile_draw_and_to_es" "$SCRIPT_DIR"
# docker push zhxgharbor.istarshine.com/dflow/draw_and_to_es:0.0.3
#
# docker build --platform=linux/amd64 -t zhxgharbor.istarshine.com/dflow/identity_juge:0.0.2 \
#   -f "$SCRIPT_DIR/dockerfiles/Dockerfile_identity_juge" "$SCRIPT_DIR"
# docker push zhxgharbor.istarshine.com/dflow/identity_juge:0.0.2
#
# docker build --platform=linux/amd64 -t zhxgharbor.istarshine.com/dflow/identity_juge_tomq:0.0.2 \
#   -f "$SCRIPT_DIR/dockerfiles/Dockerfile_identity_juge_tomq" "$SCRIPT_DIR"
# docker push zhxgharbor.istarshine.com/dflow/identity_juge_tomq:0.0.2

# ===== 统一身份判断管线（新镜像） =====
docker build --platform=linux/amd64 \
  -t zhxgharbor.istarshine.com/dflow/unified_identity:0.0.1 \
  -f "$SCRIPT_DIR/dockerfiles/Dockerfile_unified_identity" "$SCRIPT_DIR"
docker push zhxgharbor.istarshine.com/dflow/unified_identity:0.0.1
