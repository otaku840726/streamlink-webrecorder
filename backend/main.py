import os
import json
import threading
from fastapi import FastAPI, HTTPException, UploadFile, File, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from typing import List, Optional
import subprocess
from uuid import uuid4
from datetime import datetime
import signal
import sys
from fastapi.responses import FileResponse, StreamingResponse
import shutil
from fastapi.staticfiles import StaticFiles


HLS_DIR = "/hls"
os.makedirs(HLS_DIR, exist_ok=True)
hls_processes = {}  # task_id: subprocess.Popen

DATA_DIR = "/data"
RECORDINGS_DIR = "/recordings"
TASKS_FILE = os.path.join(DATA_DIR, "tasks.json")
LOG_DIR = os.path.join(DATA_DIR, "logs")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(RECORDINGS_DIR, exist_ok=True)

app = FastAPI()
scheduler = BackgroundScheduler()
scheduler.start()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/hls", StaticFiles(directory=HLS_DIR), name="hls")


lock = threading.Lock()

class Task(BaseModel):
    id: Optional[str] = None
    name: str
    url: str
    interval: int
    save_dir: str
    params: Optional[str] = ""
    hls_enable: Optional[bool] = False  # <--- 新增

def get_tasks():
    if not os.path.exists(TASKS_FILE):
        return []
    with open(TASKS_FILE, "r") as f:
        return json.load(f)

def save_tasks(tasks):
    with open(TASKS_FILE, "w") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)

def get_logfile(task_id):
    return os.path.join(LOG_DIR, f"{task_id}.log")

def write_log(task_id, event, msg=""):
    logfile = get_logfile(task_id)
    with open(logfile, "a") as f:
        f.write(json.dumps({
            "time": datetime.now().isoformat(),
            "event": event,
            "msg": msg
        }, ensure_ascii=False) + "\n")

def read_logs(task_id):
    logfile = get_logfile(task_id)
    if not os.path.exists(logfile):
        return []
    with open(logfile, "r") as f:
        return [json.loads(line) for line in f]

# ========== 重點1：全域進程表 ==========
active_recordings = {}

def record_stream(task):
    save_path = os.path.join(RECORDINGS_DIR, task.save_dir.strip("/"))
    os.makedirs(save_path, exist_ok=True)
    nowstr = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(save_path, f"{task.name}_{nowstr}.ts")

    base_cmd = [
        "streamlink",
        *(task.params.split() if task.params else []),
        task.url,
        "best",
        "-o", out_file
    ]
    write_log(task.id, "start", f"CMD: {' '.join(base_cmd)}")
    proc = None
    try:
        # ========== 註冊進程 ==========
        proc = subprocess.Popen(base_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        active_recordings[task.id] = proc
        stdout, stderr = proc.communicate()
        std_out_msg = stdout.decode("utf-8").strip() if stdout else ""
        std_err_msg = stderr.decode("utf-8").strip() if stderr else ""
        if proc.returncode == 0:
            write_log(task.id, "end", f"SUCCESS: {out_file}")
            # --- 自動轉成 MP4 ---
            try:
                mp4_file = out_file.rsplit('.', 1)[0] + ".mp4"
                ffmpeg_cmd = [
                    "ffmpeg", "-y", "-i", out_file, "-c", "copy", mp4_file
                ]
                proc2 = subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
                write_log(task.id, "mp4", f"MP4 converted: {mp4_file}")
                # 若你只要保留 mp4，可解註下一行自動刪除 ts
                # os.remove(out_file)
            except Exception as e:
                write_log(task.id, "error", f"MP4 conversion failed: {e}")
        else:
            # 無論錯誤訊息在哪裡，都抓進 log
            reason = std_err_msg or std_out_msg or "Unknown"
            main_line = reason.splitlines()[0] if reason else "Unknown"
            if "No playable streams found" in reason or "No streams found" in reason:
                write_log(task.id, "no_stream", f"No live stream: {main_line}")
            else:
                write_log(task.id, "error", f"ERROR: {main_line}")
    except Exception as e:
        write_log(task.id, "error", f"EXCEPTION: {str(e)}")
    finally:
        # ========== 錄影結束自動移除進程 ==========
        active_recordings.pop(task.id, None)

def add_job(task: Task):
    job_id = task.id
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass
    scheduler.add_job(
        record_stream,
        trigger=IntervalTrigger(minutes=task.interval),
        args=[task],
        id=job_id,
        replace_existing=True,
        next_run_time=datetime.now()
    )
    # 啟動 HLS
    if getattr(task, "hls_enable", False):
        start_hls_stream(task)
    else:
        stop_hls_stream(task.id)


def remove_job(job_id):
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass
    stop_hls_stream(job_id)
    # 清除 HLS 目錄
    task_hls_dir = os.path.join(HLS_DIR, job_id)
    if os.path.exists(task_hls_dir):
        shutil.rmtree(task_hls_dir)



def start_hls_stream(task: Task):
    # 停止舊的
    stop_hls_stream(task.id)
    task_hls_dir = os.path.join(HLS_DIR, task.id)
    if os.path.exists(task_hls_dir):
        shutil.rmtree(task_hls_dir)
    os.makedirs(task_hls_dir, exist_ok=True)

    streamlink_cmd = [
        "streamlink",
        *(task.params.split() if task.params else []),
        task.url,
        "best",
        "-O"
    ]
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", "pipe:0",
        "-c:v", "copy", "-c:a", "copy",
        "-f", "hls",
        "-hls_time", "6",
        "-hls_list_size", "10",
        "-hls_flags", "delete_segments+program_date_time",
        os.path.join(task_hls_dir, "stream.m3u8")
    ]
    # 開啟 streamlink→ffmpeg pipe
    streamlink_proc = subprocess.Popen(streamlink_cmd, stdout=subprocess.PIPE)
    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=streamlink_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    hls_processes[task.id] = (streamlink_proc, ffmpeg_proc)

def stop_hls_stream(task_id):
    procs = hls_processes.get(task_id)
    if procs:
        for proc in procs:
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
        hls_processes.pop(task_id, None)

@app.on_event("startup")
def startup_event():
    tasks = get_tasks()
    for t in tasks:
        add_job(Task(**t))

@app.get("/tasks", response_model=List[Task])
def list_tasks():
    return get_tasks()

@app.post("/tasks", response_model=Task)
def create_task(task: Task):
    with lock:
        tasks = get_tasks()
        if not task.id:
            task.id = uuid4().hex
        tasks.append(task.dict())
        save_tasks(tasks)
        add_job(task)
    return task

@app.put("/tasks/{task_id}", response_model=Task)
def update_task(task_id: str, update: Task):
    with lock:
        tasks = get_tasks()
        idx = next((i for i, t in enumerate(tasks) if t["id"] == task_id), None)
        if idx is None:
            raise HTTPException(404)
        update.id = task_id
        tasks[idx] = update.dict()
        save_tasks(tasks)
        add_job(update)
    return update

@app.delete("/tasks/{task_id}")
def delete_task(task_id: str):
    with lock:
        tasks = get_tasks()
        tasks = [t for t in tasks if t["id"] != task_id]
        save_tasks(tasks)
        remove_job(task_id)
    logfile = get_logfile(task_id)
    if os.path.exists(logfile):
        os.remove(logfile)
    return {"ok": True}

@app.get("/tasks/{task_id}/recordings")
def list_recordings(task_id: str):
    tasks = get_tasks()
    t = next((x for x in tasks if x["id"] == task_id), None)
    if not t:
        raise HTTPException(404)
    save_dir = os.path.join(RECORDINGS_DIR, t["save_dir"].strip("/"))
    files = []
    if os.path.exists(save_dir):
        for f in os.listdir(save_dir):
            p = os.path.join(save_dir, f)
            if os.path.isfile(p):
                files.append({
                    "file": f,
                    "size": os.path.getsize(p),
                    "mtime": datetime.fromtimestamp(os.path.getmtime(p)).isoformat()
                })
    files = sorted(files, key=lambda x: x["mtime"], reverse=True)
    return files

@app.get("/tasks/{task_id}/recordings/{filename}")
def get_recording(task_id: str, filename: str):
    tasks = get_tasks()
    t = next((x for x in tasks if x["id"] == task_id), None)
    if not t:
        raise HTTPException(404)
    save_dir = os.path.join(RECORDINGS_DIR, t["save_dir"].strip("/"))
    file_path = os.path.join(save_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(404)
    # 這裡直接用 FileResponse，支援影音串流、斷點續傳
    return FileResponse(file_path, media_type="video/mp2t", filename=filename)

@app.delete("/tasks/{task_id}/recordings/{filename}")
def delete_recording(task_id: str, filename: str):
    tasks = get_tasks()
    t = next((x for x in tasks if x["id"] == task_id), None)
    if not t:
        raise HTTPException(404)
    save_dir = os.path.join(RECORDINGS_DIR, t["save_dir"].strip("/"))
    file_path = os.path.join(save_dir, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    return {"ok": True}

@app.get("/tasks/{task_id}/logs")
def get_task_logs(task_id: str):
    return read_logs(task_id)

# ========== 新增: 停止錄影 API ==========
@app.post("/tasks/{task_id}/stop", status_code=status.HTTP_200_OK)
def stop_recording(task_id: str):
    proc = active_recordings.get(task_id)
    if proc and proc.poll() is None:
        proc.terminate()
        write_log(task_id, "manual_stop", "User requested stop")
        return {"ok": True, "msg": "Stopped"}
    return {"ok": False, "msg": "No active recording"}

# ========== 新增: Docker/SIGTERM 優雅結束全部錄影 ==========
def handle_shutdown(signum, frame):
    print("Graceful shutdown: Stopping all recording processes")
    for proc in list(active_recordings.values()):
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
    sys.exit(0)

@app.get("/tasks/active_recordings")
def get_active_recordings():
    # 回傳目前有在錄影的 task id 列表
    return list(active_recordings.keys())


# 點播轉檔：TS → MP4 串流（下載或觀看用）
@app.get("/tasks/{task_id}/recordings/{filename}/mp4")
def stream_ts_to_mp4(task_id: str, filename: str):
    tasks = get_tasks()
    t = next((x for x in tasks if x["id"] == task_id), None)
    if not t:
        raise HTTPException(404)
    save_dir = os.path.join(RECORDINGS_DIR, t["save_dir"].strip("/"))
    file_path = os.path.join(save_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(404)
    if not filename.lower().endswith(".ts"):
        raise HTTPException(400, "Only .ts can be remuxed")

    def remux():
        cmd = [
            "ffmpeg",
            "-i", file_path,
            "-c:v", "copy", "-c:a", "copy",
            "-f", "mp4",
            "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            "pipe:1"
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10**6)
        try:
            while True:
                data = proc.stdout.read(1024 * 64)
                if not data:
                    break
                yield data
        finally:
            proc.stdout.close()
            proc.terminate()
    return StreamingResponse(remux(), media_type="video/mp4")

# 錄影中即時觀看（TS 檔 growing file 也能邊錄邊播！）
@app.get("/tasks/{task_id}/recordings/{filename}/live_mp4")
def live_mp4_stream(task_id: str, filename: str):
    tasks = get_tasks()
    t = next((x for x in tasks if x["id"] == task_id), None)
    if not t:
        raise HTTPException(404)
    save_dir = os.path.join(RECORDINGS_DIR, t["save_dir"].strip("/"))
    file_path = os.path.join(save_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(404)
    if not filename.lower().endswith(".ts"):
        raise HTTPException(400, "Only .ts can be live streamed")

    def remux():
        cmd = [
            "ffmpeg",
            "-re",
            "-i", file_path,
            "-c:v", "copy", "-c:a", "copy",
            "-f", "mp4",
            "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            "pipe:1"
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10**6)
        try:
            while True:
                data = proc.stdout.read(1024 * 64)
                if not data:
                    break
                yield data
        finally:
            proc.stdout.close()
            proc.terminate()
    return StreamingResponse(remux(), media_type="video/mp4")
    
signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)
