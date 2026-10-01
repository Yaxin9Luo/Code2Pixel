# Code2Pixel 统一环境：agent 在这里写代码、渲染、交图。
# 构建：docker build -t code2pixel/env:0.1 env/
# 多架构：docker buildx build --platform linux/amd64,linux/arm64 -t code2pixel/env:0.1 env/
FROM ubuntu:24.04

ARG PLAYWRIGHT_VERSION=1.63.0
ARG THREE_VERSION=0.186.1
ARG CLAUDE_CODE_VERSION=2.1.285
ARG CODEX_VERSION=0.159.2
ARG NODE_MAJOR=22

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PATH=/opt/venv/bin:$PATH \
    NODE_PATH=/opt/node/node_modules

# 系统包：编译器、字体、Blender、SVG 渲染器
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git gnupg build-essential pkg-config \
      python3 python3-venv python3-dev \
      libcairo2-dev librsvg2-bin imagemagick \
      fonts-noto-cjk fonts-noto-color-emoji fonts-dejavu fonts-liberation \
      blender \
      jq procps less \
    && rm -rf /var/lib/apt/lists/*

# resvg（Ubuntu 仓库里没有时跳过，librsvg 和 Chromium 仍可渲染 SVG）
RUN (apt-get update && apt-get install -y --no-install-recommends resvg && rm -rf /var/lib/apt/lists/*) || echo "resvg not available"

# Node
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Python 科学计算栈
RUN python3 -m venv /opt/venv && pip install --no-cache-dir \
      numpy scipy pillow matplotlib scikit-image opencv-python-headless \
      shapely svgwrite cairosvg pycairo \
      playwright==${PLAYWRIGHT_VERSION}

# Chromium（Python 和 Node 两边的 Playwright 同版本，共用这一份）
RUN playwright install --with-deps chromium && chmod -R a+rX /opt/ms-playwright

# Node 库：Three.js、Playwright
RUN mkdir -p /opt/node && cd /opt/node && npm init -y >/dev/null \
    && npm install --no-audit --no-fund three@${THREE_VERSION} playwright@${PLAYWRIGHT_VERSION}

# 两个 agent CLI
RUN npm install -g --no-audit --no-fund \
      @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION} @openai/codex@${CODEX_VERSION}

COPY c2p-render /usr/local/bin/c2p-render
RUN chmod +x /usr/local/bin/c2p-render

# 非 root 用户（Claude Code 在 root 下不允许跳过权限确认）
RUN useradd -m -s /bin/bash agent && mkdir -p /workspace && chown agent:agent /workspace
USER agent
WORKDIR /workspace
