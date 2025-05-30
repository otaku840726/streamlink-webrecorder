FROM akashisn/ffmpeg:7.0.2

WORKDIR /app

# 安裝必要的 build 及執行期依賴
RUN apt-get update && apt-get install -y \
    git build-essential pkg-config \
    yasm nasm cmake ninja-build \
    python3 python3-pip python3-venv \
    wget curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Taipei
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y tzdata \
    && rm -rf /var/lib/apt/lists/*

# 安装 Playwright 运行时依赖
RUN apt-get update && apt-get install -y \
    libgtk-4-1 libgraphene-1.0-0 libwoff2-1 \
    gstreamer1.0-gl gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
    gstreamer1.0-libav libavif16 libharfbuzz-icu0 \
    libenchant-2-2 libhyphen0 libmanette-0.2-0 \
  && rm -rf /var/lib/apt/lists/*

# python 相關依賴
COPY requirements.txt .
RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
RUN pip install streamlink


# 下载浏览器二进制
RUN playwright install
# 安装系统依赖
RUN python3 -m playwright install-deps
RUN python3 -m playwright install-deps

RUN mkdir -p /root/.local/share/streamlink/plugins
COPY plugins /root/.local/share/streamlink/plugins

COPY . .

EXPOSE 8800
ENTRYPOINT []
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8800"]
