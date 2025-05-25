FROM ubuntu:24.04

WORKDIR /app

# 安裝必要的 build 及執行期依賴
RUN apt-get update && apt-get install -y \
    git build-essential pkg-config \
    yasm cmake ninja-build \
    python3 python3-pip python3-venv \
    wget curl ca-certificates \
    libva-dev libdrm-dev libvpl-dev \
    intel-media-va-driver-non-free \
    libass-dev libfreetype6-dev libgnutls28-dev \
    libmp3lame-dev libopus-dev libvpx-dev libx264-dev libx265-dev libnuma-dev \
    libvorbis-dev libxcb1-dev libxcb-shm0-dev libxcb-xfixes0-dev \
    libunistring-dev libfribidi-dev libxml2-dev libbluray-dev && \
    rm -rf /var/lib/apt/lists/*

# 編譯並安裝最新 ffmpeg（支援 qsv_params）
RUN git clone --depth 1 https://git.ffmpeg.org/ffmpeg.git ffmpeg && \
    cd ffmpeg && \
    ./configure \
      --prefix=/usr \
      --enable-gpl \
      --enable-nonfree \
      --enable-libass \
      --enable-libfreetype \
      --enable-libmp3lame \
      --enable-libopus \
      --enable-libvorbis \
      --enable-libvpx \
      --enable-libx264 \
      --enable-libx265 \
      --enable-libxml2 \
      --enable-libdrm \
      --enable-libvpl \
      --enable-vaapi \
      --enable-opencl \
      --enable-libbluray \
      --enable-pthreads \
      --enable-shared \
      --enable-version3 \
      --enable-libfribidi \
      --disable-debug \
      --disable-doc && \
    make -j$(nproc) && make install && \
    cd .. && rm -rf ffmpeg

# python 相關依賴
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
