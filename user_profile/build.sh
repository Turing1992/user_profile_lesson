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

# ===== 已下线：统一身份判断管线（实时，消费 spider_data） =====
# 实时路已停用，改为预警账号每日批量 + 历史回溯两路。需要时取消注释。
# docker build --platform=linux/amd64 \
#   -t zhxgharbor.istarshine.com/dflow/unified_identity:0.0.1 \
#   -f "$SCRIPT_DIR/dockerfiles/Dockerfile_unified_identity" "$SCRIPT_DIR"
# docker push zhxgharbor.istarshine.com/dflow/unified_identity:0.0.1

# ===== 预警账号身份识别（当前线上）=====
# 同一个镜像承载两路，靠启动命令区分：
#   增量路：CronJob 每天跑 daily_identity_job（默认 CMD）
#   历史路：一次性 Job 跑 backfill_identity_job，可中断续跑
docker build --platform=linux/amd64 \
  -t zhxgharbor.istarshine.com/dflow/warning_daily_identity:0.0.2 \
  -f "$SCRIPT_DIR/dockerfiles/Dockerfile_warning_daily_identity" "$SCRIPT_DIR"
docker push zhxgharbor.istarshine.com/dflow/warning_daily_identity:0.0.2
