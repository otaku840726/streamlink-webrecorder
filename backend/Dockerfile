FROM ubuntu:25.04

WORKDIR /app

# 安裝基本工具
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libavcodec-extra \
    libavfilter-extra \
    python3 \
    python3-pip \
    wget \
    gnupg \
    software-properties-common \
    curl && \
    rm -rf /var/lib/apt/lists/*

# 僅安裝能在 Ubuntu 25.04 找到的 Intel Media 驅動
RUN apt-get update && apt-get install -y \
    intel-media-va-driver-non-free \
    libva-drm2 \
    libva-x11-2 \
    vainfo \
    i965-va-driver && \
    rm -rf /var/lib/apt/lists/*

# 安裝 python 依賴與 streamlink
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
RUN pip install streamlink

RUN mkdir -p /root/.local/share/streamlink/plugins
COPY stripchat.py /root/.local/share/streamlink/plugins/stripchat.py

COPY . .

EXPOSE 8800

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8800"]
