# Streamlink Web Recorder

```bash
├── Caddyfile
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
└── frontend/
    ├── Dockerfile
    ├── package.json
    └── src/
        ├── App.js
        ├── api.js
        └── components/
            ├── TaskList.js
            ├── TaskForm.js
            ├── RecordingList.js
            ├── LogList.js
            └── VideoPlayer.js
```

A self-hosted web application for scheduled live stream recording and HLS playback, built with **FastAPI** (backend) and **React + MUI** (frontend). It leverages **Streamlink** for capturing livestreams and **FFmpeg** for format conversion and thumbnail generation.

---

## 🏗️ Architecture

```
User Browser <---> Caddy Reverse Proxy <--->
  ├── Backend (FastAPI + Streamlink + FFmpeg) :8800
  └── Frontend (React + MUI)                  :80
```

- **Backend**: Provides RESTful APIs for managing recording tasks, scheduling recordings via APScheduler, HLS generation, TS→MP4 conversion, and thumbnails.
- **Frontend**: Rich UI for task CRUD, live status, historical recordings, and playback using HLS.js or native video.
- **Caddy**: Handles HTTP routing without TLS (optional), proxies `/tasks`, `/hls`, `/thumbnails` to backend, other paths to frontend.

---

## ⚙️ Features

- **Streamlink integration**: Reliable stream capture from various platforms (YouTube, Twitch, etc.).
- **Scheduled recording**: Configure recurring tasks (interval in minutes) to auto-record.
- **Live HLS**: Real-time streaming via HLS for preview.
- **Post-processing**: Automatic TS→MP4 conversion with Intel VA-API acceleration.
- **Thumbnails & previews**: FFmpeg-powered thumbnails & GIF previews.
- **Task dashboard**: View current recording status, last recording time, and count of recordings.
- **Responsive UI**: Mobile-friendly dialogs for recordings, logs, and task forms.

---

## ⚠️ Licensing & Copyright

- **Streamlink** is licensed under the [GPLv3 License](https://github.com/streamlink/streamlink/blob/master/LICENSE).
- **FFmpeg** libraries are licensed under LGPL/GPL (depending on configuration). Ensure compliance with their licenses when distributing.
- This project’s code is released under the MIT License. See [LICENSE](LICENSE) for details.

---

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- (Optional) `.env` in frontend:
  ```env
  REACT_APP_API=http://localhost
  ```

### 1. Clone & Build

```bash
git clone https://github.com/yourrepo/streamlink-webrecorder.git
cd streamlink-webrecorder
docker-compose build
```

### 2. Run Services

```bash
docker-compose up -d
```

- Browse `http://localhost` for the frontend.
- Backend APIs are at `http://localhost:13052/tasks`.

### 3. Create & Manage Tasks

1. Click **新增任務**, set stream URL, interval, save directory.
2. View **錄影清單** for status and recent recordings.
3. Click **直播觀看** or **播放** to preview.

---

## 📝 Configuration

- **Caddyfile**: Customize routing and ports.
- **backend/requirements.txt**: Python deps.
- **frontend/package.json**: Node deps.

---

## 💡 Tips

- Ensure correct VA-API permissions (`--device /dev/dri/renderD128`).
- For high-frequency checks (<1 min), adjust APScheduler in `main.py`.
- Monitor logs under `/data/logs/<task_id>.log` for errors.
