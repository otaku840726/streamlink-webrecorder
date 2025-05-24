# Streamlink Web Recorder Manager

全自動、多任務、Web UI 管理的 Streamlink 直播錄影定時系統。支援 Docker 一鍵部署，支援同時多任務、錄影自動分類、線上播放、下載、異常紀錄！

## 特色
- 多任務 streamlink 定時錄影
- WebUI 設定/管理任務
- 支援所有 streamlink 來源（YouTube, Twitch, m3u8...）
- 支援多流併發
- 錄影檔案自動分任務分類、線上播放/下載/刪除
- 執行紀錄（開始、結束、異常）Web查詢
- 完整 Docker Compose 部署
- 全中文說明

## 快速安裝

### 1. 先裝好 [Docker](https://www.docker.com/) 和 docker-compose

### 2. 解壓本專案 zip 或 git clone 到本地

### 3. 執行

```bash
docker compose up -d
