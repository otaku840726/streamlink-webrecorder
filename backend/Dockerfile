FROM ubuntu:24.04

WORKDIR /app

# 安裝基本工具
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libavcodec-extra \
    libavfilter-extra \
    python3 \
    python3-pip \
    python3-venv \
    wget \
    gnupg \
    software-properties-common \
    curl && \
    rm -rf /var/lib/apt/lists/*

# 安裝 Intel Media 驅動 (QSV/iHD)
RUN apt-get update && apt-get install -y \
    intel-media-va-driver-non-free \
    libva-drm2 \
    libva-x11-2 \
    vainfo \
    i965-va-driver && \
    rm -rf /var/lib/apt/lists/*

# 建立 Python venv 並安裝依賴
COPY requirements.txt .
RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
RUN pip install streamlink

RUN mkdir -p /root/.local/share/streamlink/plugins
COPY stripchat.py /root/.local/share/streamlink/plugins/stripchat.py

COPY . .

EXPOSE 8800

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8800"]
