FROM akashisn/ffmpeg:7.0.2

WORKDIR /app

# 安裝必要的 build 及執行期依賴
RUN apt-get update && apt-get install -y \
    git build-essential pkg-config \
    yasm nasm cmake ninja-build \
    python3 python3-pip python3-venv \
    wget curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# python 相關依賴
COPY requirements.txt .
RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
RUN pip install streamlink

RUN mkdir -p /root/.local/share/streamlink/plugins
COPY plugins /root/.local/share/streamlink/plugins

COPY . .

EXPOSE 8800

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8800"]
