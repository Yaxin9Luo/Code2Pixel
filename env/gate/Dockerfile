# 门槛用的重跑镜像：和 agent 用的镜像完全一样，只多一个 strace，用来记录重跑时打开的文件和网络连接
FROM code2pixel/env:0.1
USER root
RUN apt-get update && apt-get install -y --no-install-recommends strace && rm -rf /var/lib/apt/lists/*
USER agent
