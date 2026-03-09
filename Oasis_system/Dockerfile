FROM centos:7

# 设置时区
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 安装Python 3.6和依赖
RUN yum install -y python3 python3-pip && \
    yum clean all

# 设置工作目录
WORKDIR /app

# 复制项目文件
COPY requirements.txt .
COPY *.py .
COPY example_input.json .

# 安装Python依赖
RUN pip3 install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/

# 创建日志目录
RUN mkdir -p logs

# 暴露API端口
EXPOSE 5001

# 默认启动API服务
CMD ["python3", "api_server.py"]
