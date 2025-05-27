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
import psutil
from PIL import Image
import time


HLS_DIR = "/hls"
os.makedirs(HLS_DIR, exist_ok=True)
hls_processes = {}  # task_id: subprocess.Popen
conversion_tasks = {}  # {task_id_filename: {status, progress, start_time, quality}}  
active_recordings = {}

THUMBNAILS_DIR = "/thumbnails"
os.makedirs(THUMBNAILS_DIR, exist_ok=True)

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
app.mount("/thumbnails", StaticFiles(directory=THUMBNAILS_DIR), name="thumbnails")


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

def read_logs(task_id, limit=20):
    """
    從文件末尾讀取最新的 n 條日誌記錄
    
    參數:
    - task_id: 任務ID
    - limit: 返回的日誌條數上限，默認20條
    
    返回:
    - 倒序排列的最新日誌記錄列表
    """
    logfile = get_logfile(task_id)
    if not os.path.exists(logfile):
        return []
    
    # 使用逆向讀取文件的方式獲取最新日誌
    logs = []
    try:
        with open(logfile, 'rb') as f:
            # 先將文件指針移到末尾
            f.seek(0, 2)
            file_size = f.tell()
            
            # 從文件末尾開始讀取
            pointer = file_size
            line_count = 0
            
            # 逆向讀取直到達到限制或文件開頭
            while pointer > 0 and line_count < limit:
                # 向前移動指針，最多移動 8KB
                chunk_size = min(8192, pointer)
                pointer -= chunk_size
                f.seek(pointer)
                
                # 讀取當前塊的數據
                data = f.read(chunk_size + (file_size - pointer - chunk_size))
                
                # 按行分割並處理不完整行
                lines = data.split(b'\n')
                
                # 如果不是第一塊且指針不在文件開頭，丟棄第一行（可能不完整）
                if pointer > 0 and line_count > 0:
                    lines = lines[1:]
                
                # 處理每一行
                for line in reversed(lines):
                    if not line:  # 跳過空行
                        continue
                    try:
                        log = json.loads(line.decode('utf-8'))
                        logs.append(log)
                        line_count += 1
                        if line_count >= limit:
                            break
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        print(f"讀取日誌錯誤: {str(e)}")
    
    return logs

def write_compression_log(message):
    print(message)

# 添加在全局变量部分（约在第 40 行附近）
# 用于跟踪转码任务的状态
def get_duration(ts_file):
    # 方法 1：用 ffprobe 讀取 video stream duration
    cmd1 = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        ts_file
    ]
    result = subprocess.run(cmd1, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        duration = float(result.stdout.strip())
        if duration > 0:
            return duration
    except:
        pass

    # 方法 2：ffmpeg 輸出資訊中擷取 "Duration: 00:00:12.34"
    cmd2 = [
        "ffmpeg", "-i", ts_file
    ]
    result2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    match = re.search(r'Duration: (\d+):(\d+):(\d+).(\d+)', result2.stdout)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        millis = int(match.group(4))
        return hours * 3600 + minutes * 60 + seconds + millis / 100.0

    return None  # 若完全失敗

def get_first_pts(ts_file):
    import subprocess, json
    try:
        cmd = [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_entries", "frame=pts_time", "-select_streams", "v:0",
            "-read_intervals", "%+#1", ts_file
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        info = json.loads(result.stdout)
        if "frames" in info and info["frames"]:
            # 第一幀的 pts_time
            return float(info["frames"][0]["pts_time"])
    except Exception as e:
        print(f"[get_first_pts] error: {e}")
    return 0.0


# 添加在 ts_to_mp4 函数中，修改函数签名和内容
def ts_to_mp4(ts_file, quality="high", task_id=None):
    import re
    import subprocess
    filename = os.path.basename(ts_file)
    task_key = f"{task_id}_{filename}"
    base, _ = os.path.splitext(ts_file)
    mp4_file = base + ".mp4"

    print(f"[ts_to_mp4] called with ts_file={ts_file} quality={quality} task_id={task_id}")
    print(f"[ts_to_mp4] task_key={task_key}, mp4_file={mp4_file}")

    # 初始化状态
    start = time.time()
    conversion_tasks[task_key] = {
        "status": "processing",
        "progress": 0,
        "start_time": start,
        "quality": quality
    }

    # 先拿总时长，必须成功，否则无法计算中间进度
    total_duration = get_duration(ts_file)
    print(f"[ts_to_mp4] get_duration({ts_file}) = {total_duration}")
    if not total_duration or total_duration < 1.0:
        print(f"[ts_to_mp4] 無法獲取 {ts_file} 的時長，放棄轉碼")
        conversion_tasks[task_key].update({
            "status": "failed",
            "end_time": time.time(),
            "progress": 0
        })
        return None

    # 选 CRF
    crf_map = {"extreme": 36, "high": 32, "medium": 28, "low": 24}
    crf = crf_map.get(quality, 32)
    print(f"[ts_to_mp4] crf={crf}")

    # 关键：持续输出进度信息，并关闭默认 stats 输出
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-progress", "pipe:1",
        "-nostats",
        "-i", ts_file,
        "-c:v", "libx265", "-crf", str(crf), "-preset", "medium",
        "-c:a", "copy",
        mp4_file
    ]
    print(f"[ts_to_mp4] running command: {' '.join(cmd)}")

    # 取得影片最早的 PTS
    pts_base = get_first_pts(ts_file)
    print(f"[ts_to_mp4] pts_base={pts_base}")

    def read_output(proc):
        print(f"[ts_to_mp4] read_output() thread started")
        start_time = None  # 進度起點
        while True:
            line = proc.stdout.readline()
            if not line:
                print("[ts_to_mp4] ffmpeg stdout closed, break.")
                break
            print(f"[ffmpeg] {line.strip()}")
            # (1) 抓 start_time
            if start_time is None and "start:" in line:
                try:
                    # 解析出 start: 153676.630000
                    start_time = float(line.split("start:")[1].split(",")[0].strip())
                    print(f"[ts_to_mp4] detected start_time: {start_time}")
                except Exception as e:
                    print(f"[ts_to_mp4] failed to parse start_time: {e}")

            # (2) 算進度時要有 start_time
            if line.startswith("out_time_ms="):
                try:
                    out_ms = int(line.split("=", 1)[1].strip())
                    out_sec = out_ms / 1000
                    # 判斷是否要取餘數
                    if out_sec > total_duration * 3:
                        current_sec = out_sec % total_duration
                    else:
                        current_sec = out_sec

                    # 最大進度追蹤
                    prev_max = conversion_tasks[task_key].get("max_current_sec", 0)
                    if current_sec > prev_max:
                        conversion_tasks[task_key]["max_current_sec"] = current_sec
                    else:
                        current_sec = prev_max

                    pct = min(100, (current_sec / total_duration) * 100)
                    conversion_tasks[task_key]["progress"] = pct
                    print(f"[ts_to_mp4] 轉碼進度: {pct:.2f}% (out_time_ms={out_ms}, out_sec={out_sec}, current_sec={current_sec}, total_duration={total_duration})")
                except Exception as e:
                    print(f"[ts_to_mp4] 解析進度出錯: {str(e)} line={line}")


    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    output_thread = threading.Thread(target=read_output, args=(proc,), daemon=True)
    output_thread.start()

    proc.wait()
    output_thread.join(timeout=1)
    print(f"[ts_to_mp4] ffmpeg proc.returncode={proc.returncode}")

    # 转码完成／失败后收尾
    if proc.returncode == 0 and os.path.exists(mp4_file):
        original_size = os.path.getsize(ts_file) / (1024*1024)
        new_size = os.path.getsize(mp4_file) / (1024*1024)
        print(f"[ts_to_mp4] completed: {original_size:.2f}MB → {new_size:.2f}MB")
        conversion_tasks[task_key].update({
            "status": "completed",
            "progress": 100,
            "end_time": time.time(),
            "original_size": original_size,
            "new_size": new_size
        })
        try:
            os.remove(ts_file)
        except Exception as e:
            print(f"[ts_to_mp4] 刪除 TS 檔時發生錯誤: {e}")
        return mp4_file
    else:
        print(f"[ts_to_mp4] failed. mp4_file exists: {os.path.exists(mp4_file)}")
        conversion_tasks[task_key].update({
            "status": "failed",
            "end_time": time.time()
        })
        return None



# 添加新的 API 端点，用于手动触发转码（约在第 600 行后）
@app.post("/tasks/{task_id}/recordings/{filename}/convert")
def convert_recording(task_id: str, filename: str, quality: str = "high"):
    tasks = get_tasks()
    t = next((x for x in tasks if x["id"] == task_id), None)
    if not t:
        raise HTTPException(404)
    save_dir = os.path.join(RECORDINGS_DIR, t["save_dir"].strip("/"))
    file_path = os.path.join(save_dir, filename)       # ← 确保定义在这儿
    if not os.path.exists(file_path):
        raise HTTPException(404)
    if not filename.lower().endswith(".ts"):
        raise HTTPException(400, "Only .ts files can be converted")

    task_key = f"{task_id}_{filename}"
    if task_key in conversion_tasks and conversion_tasks[task_key]["status"] == "processing":
        return {"status": "already_processing", "task_key": task_key}

    # 直接把 ts_to_mp4 当作 target，file_path 就是上面定义的那个变量
    thread = threading.Thread(
        target=ts_to_mp4,
        args=(file_path, quality, task_id),
        daemon=True
    )
    thread.start()

    return {"status": "started", "task_key": task_key}


# 添加 API 端点，用于获取转码进度
@app.get("/conversion_status")
def get_conversion_status(task_key: str = None):
    if task_key:
        return {task_key: conversion_tasks.get(task_key, {"status": "not_found"})}
    return conversion_tasks

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
            # --- 自動轉成 MP4 --- (統一使用 ts_to_mp4 函數)
            mp4_file = ts_to_mp4(out_file)
            if mp4_file:
                write_log(task.id, "mp4", f"MP4 converted: {mp4_file}")
            else:
                write_log(task.id, "error", f"MP4 conversion failed for {out_file}")
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
        # 確保在 finally 區塊也呼叫 ts_to_mp4，以處理可能的例外情況
        if os.path.exists(out_file):
            mp4_file = ts_to_mp4(out_file)
            if mp4_file:
                # 這裡可以選擇是否要記錄，因為前面成功時已經記錄過了
                # write_log(task.id, "mp4_finally", f"MP4 converted (finally): {mp4_file}")
                pass # 或者不記錄
            else:
                # 如果轉換失敗，可以記錄一下
                write_log(task.id, "error_finally", f"MP4 conversion failed (finally) for {out_file}")

def add_job(task: Task):
    stop_hls_stream(task.id)  # 保險先停
    try:
        scheduler.remove_job(task.id)
    except Exception:
        pass
    scheduler.add_job(
        record_stream,
        trigger=IntervalTrigger(minutes=task.interval),
        args=[task],
        id=task.id,
        replace_existing=True,
        next_run_time=datetime.now()
    )
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
        "-hls_time", "2",                # 改回 2 秒，1 秒太短了
        "-hls_list_size", "6",           # 適當減少列表大小
        "-hls_flags", "delete_segments+program_date_time+append_list",  # 添加 append_list
        "-hls_segment_type", "mpegts",   # 明確指定分段類型
        "-hls_init_time", "2",           # 初始分段時間
        "-hls_allow_cache", "1",         # 允許緩存
        os.path.join(task_hls_dir, "stream.m3u8")
    ]
    write_log(task.id, "hls_start", f"CMD: {' '.join(streamlink_cmd)} | {' '.join(ffmpeg_cmd)}")
    streamlink_proc = subprocess.Popen(streamlink_cmd, stdout=subprocess.PIPE)
    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=streamlink_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    hls_processes[task.id] = (streamlink_proc, ffmpeg_proc)

    def monitor_ffmpeg():
        stdout, stderr = ffmpeg_proc.communicate()
        std_out_msg = stdout.decode("utf-8", errors="ignore") if stdout else ""
        std_err_msg = stderr.decode("utf-8", errors="ignore") if stderr else ""
        if ffmpeg_proc.returncode == 0:
            write_log(task.id, "hls_end", "ffmpeg exited normally")
        else:
            write_log(task.id, "hls_error", f"ffmpeg exited: {std_err_msg or std_out_msg}")
    threading.Thread(target=monitor_ffmpeg, daemon=True).start()

def stop_hls_stream(task_id):
    procs = hls_processes.get(task_id)
    if procs:
        for proc in procs:
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        hls_processes.pop(task_id, None)

    # 強制殺光所有殘留 ffmpeg/streamlink（保險起見）
    # 找所有 ffmpeg/streamlink，有參數指到該目錄就砍掉
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if ('ffmpeg' in p.info['name'] or 'streamlink' in p.info['name']) and \
                any(task_id in str(x) for x in p.info['cmdline']):
                print(f"Kill leftover process: {p.info['pid']} {p.info['cmdline']}")
                p.kill()
        except Exception:
            pass

def generate_thumbnail(video_path, interval: int = 60, size: int = 128):
    """
    从视频中每隔 interval 秒抽帧生成缩略图，
    输出到目录 THUMBNAILS_DIR/{basename}/ 下，
    文件名格式为 <basename>_001.jpg、<basename>_002.jpg…
    """
    import subprocess
    basename = os.path.basename(video_path)
    name, _ = os.path.splitext(basename)
    out_dir = os.path.join(THUMBNAILS_DIR, name)
    os.makedirs(out_dir, exist_ok=True)
    # 构建 ffmpeg 命令：fps=1/interval 每秒取 1/interval 帧
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"fps=1/{interval},scale={size}:-1:flags=lanczos",
        "-qscale:v", "2",
        os.path.join(out_dir, f"{name}_%03d.jpg")
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"缩略图生成成功: {out_dir}")
        return out_dir
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode('utf-8', errors='ignore')
        print(f"缩略图生成失败: {err}")
        return None


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
        # 轉檔流程
        tasks = get_tasks()
        t = next((x for x in tasks if x["id"] == task_id), None)
        if not t:
            return {"ok": False, "msg": "Task not found"}
        save_dir = os.path.join(RECORDINGS_DIR, t["save_dir"].strip("/"))
        ts_files = [f for f in os.listdir(save_dir) if f.endswith(".ts")]
        if ts_files:
            latest_ts = max(ts_files, key=lambda f: os.path.getmtime(os.path.join(save_dir, f)))
            ts_file_path = os.path.join(save_dir, latest_ts)
            ts_to_mp4(ts_file_path)
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


# —— 新增：获取录像缩略图 —— 
@app.get("/tasks/{task_id}/recordings/{filename}/thumbnails")
def list_thumbnails(task_id: str, filename: str):
    """
    列出指定录像文件的所有缩略图 URL，如果不存在则生成。
    返回格式：
      ["/thumbnails/<basename>/<basename>_001.jpg", ...]
    """
    name, _ = os.path.splitext(filename)
    # 缩略图目录
    thumb_dir = os.path.join(THUMBNAILS_DIR, name)
    # 若目录不存在则尝试生成
    if not os.path.isdir(thumb_dir):
        tasks = get_tasks()
        t = next((x for x in tasks if x["id"] == task_id), None)
        if t:
            save_dir = os.path.join(RECORDINGS_DIR, t["save_dir"].strip("/"))
            source_file = os.path.join(save_dir, filename)
            if os.path.exists(source_file):
                generate_thumbnail(source_file)
    if not os.path.isdir(thumb_dir):
        raise HTTPException(status_code=404, detail="Thumbnails not found")
    # 列出 JPG 文件，并按文件名排序
    files = sorted(f for f in os.listdir(thumb_dir) if f.lower().endswith('.jpg'))
    # 返回静态挂载路径
    return [f"/thumbnails/{name}/{f}" for f in files]

signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)