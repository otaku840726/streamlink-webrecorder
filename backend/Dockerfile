FROM python:3.11-slim

WORKDIR /app

# 安裝 ffmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg curl && \
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
