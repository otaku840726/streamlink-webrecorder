DEBIAN_FRONTEND=noninteractive && TZ=Asia/Taipei &&\
apt-get update && apt-get install -y \
    git build-essential pkg-config \
    yasm nasm cmake ninja-build \
    python3 python3-pip python3-venv \
    wget curl ca-certificates tzdata \
    libgtk-4-1 libgraphene-1.0-0 \
    gstreamer1.0-gl gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
    gstreamer1.0-libav libwoff1 libavif13  libharfbuzz-icu0 \
    libenchant-2-2 libhyphen0 libmanette-0.2-0 && \
    apt-get update

python3 -m venv /venv
export PATH="/venv/bin:$PATH"
pip install --upgrade pip  --break-system-packages
pip install -r requirements.txt  --break-system-packages
pip install streamlink  --break-system-packages

playwright install
# 安装系统依赖
python3 -m playwright install-deps
python3 -m playwright install-deps

