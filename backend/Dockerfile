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

# 新增 Intel oneAPI APT 軟體庫
RUN wget -O- https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | \
    gpg --dearmor | tee /usr/share/keyrings/oneapi-archive-keyring.gpg > /dev/null && \
    echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main" \
    > /etc/apt/sources.list.d/oneAPI.list

# 安裝 Intel Media Runtime 及 GPU 驅動
RUN apt-get update && apt-get install -y \
    intel-media-va-driver-non-free \
    libva-drm2 \
    libva-x11-2 \
    vainfo \
    i965-va-driver \
    libmfx1 \
    libmfx-gen1 \
    libvpl2 && \
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
