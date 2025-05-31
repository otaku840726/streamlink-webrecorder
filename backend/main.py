import os
import json
import threading
from fastapi import FastAPI, HTTPException, UploadFile, File, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from typing import List, Optional, Literal
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
from handlers.base_handler import get_handler


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
    hls_enable: Optional[bool] = False
    default_conversion_quality: Optional[str] = "high"
    tool: Literal["streamlink", "custom"] = "streamlink"

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

def get_total_frames(ts_file):
    """
    用 ffprobe 获取视频总帧数，用于进度计算
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-count_frames",
        "-select_streams", "v:0",
        "-show_entries", "stream=nb_read_frames",
        "-of", "default=noprint_wrappers=1:nokey=1",
        ts_file
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return int(result.stdout.strip())
    except:
        return None


# 添加在 ts_to_mp4 函数中，修改函数签名和内容
def ts_to_mp4(ts_file, quality="high", task_id=None, task_key_override=None):
    import re  # 確保 re 模塊已導入
    filename = os.path.basename(ts_file)
    # 如果提供了 task_key_override，則使用它，否則基於 task_id 和 filename 生成
    task_key = task_key_override if task_key_override else f"{task_id}_{filename}"
    base, _ = os.path.splitext(ts_file)
    mp4_file = base + ".mp4"

    # 初始化状态
    start = time.time()
    conversion_tasks[task_key] = {
        "status": "processing",
        "progress": 0,
        "start_time": start,
        "quality": quality
    }

    # 选 CRF
    crf_map = {"extreme": 36, "high": 32, "medium": 28, "low": 24}
    crf = crf_map.get(quality, 32)

    # 关键：使用 -stats 参数让 ffmpeg 输出详细的进度信息
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-stats",  # 使用 -stats 而不是 -progress
        "-i", ts_file,
        "-c:v", "libx265", "-crf", str(crf), "-preset", "medium",
        "-c:a", "copy",
        mp4_file
    ]
    
    # 使用線程來讀取進程輸出，確保實時更新進度
    def read_output(proc):
        # 用於跟踪進度的變量
        total_duration_seconds = None
        start_time_seconds = 0  # 默認為0，如果解析到start則更新
        actual_total_duration_seconds = None

        # 從 stderr 讀取，因為 ffmpeg 的進度信息輸出到 stderr
        for line in iter(proc.stderr.readline, ''):
            if not line:  # 如果讀取到空行，說明流結束了
                break
            
            line_strip = line.strip()
            # 打印每一行輸出，方便調試
            print(f"FFMPEG: {line_strip}")

            # 解析 Duration 和 start
            duration_match = re.search(r'Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)', line_strip)
            if duration_match:
                hours = int(duration_match.group(1))
                minutes = int(duration_match.group(2))
                seconds = float(duration_match.group(3))
                total_duration_seconds = hours * 3600 + minutes * 60 + seconds
                print(f"解析到 Duration: {total_duration_seconds}s")

            start_match = re.search(r'start:\s*(\d+\.?\d*)', line_strip)
            if start_match:
                start_time_seconds = float(start_match.group(1))
                print(f"解析到 start: {start_time_seconds}s")
            
            if total_duration_seconds is not None:
                actual_total_duration_seconds = total_duration_seconds - start_time_seconds
                if actual_total_duration_seconds <= 0: # 防止 start 比 duration 大或相等的情況
                    print(f"警告: 計算出的實際總時長 <= 0 ({actual_total_duration_seconds}s), 將使用原始Duration進行計算。")
                    actual_total_duration_seconds = total_duration_seconds
                print(f"計算出的實際總時長: {actual_total_duration_seconds}s (Duration: {total_duration_seconds}s, Start: {start_time_seconds}s)")

            # 解析當前 time
            time_match = re.search(r'time=(\d{2}):(\d{2}):(\d{2}\.\d+)', line_strip)
            if time_match and actual_total_duration_seconds and actual_total_duration_seconds > 0:
                hours = int(time_match.group(1))
                minutes = int(time_match.group(2))
                seconds = float(time_match.group(3))
                current_time_seconds = hours * 3600 + minutes * 60 + seconds
                
                # 進度是相對於 start 時間之後的當前時間
                # progress_time_seconds = current_time_seconds - start_time_seconds
                progress_time_seconds = current_time_seconds
                
                progress = (progress_time_seconds / actual_total_duration_seconds) * 100
                progress = min(100, max(0, progress)) # 限制在 0-100
                conversion_tasks[task_key]["progress"] = progress
                print(f"轉碼進度 (基於時間): {progress:.2f}% (當前時間: {current_time_seconds}s / 實際總長: {actual_total_duration_seconds}s)")
    
    # 使用 stderr=subprocess.PIPE 來捕獲 ffmpeg 的進度輸出
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True)
    
    # 啟動讀取線程
    output_thread = threading.Thread(target=read_output, args=(proc,), daemon=True)
    output_thread.start()
    
    # 等待進程完成
    proc.wait()
    output_thread.join(timeout=1)  # 給讀取線程最多1秒鐘完成

    # 转码完成／失败后收尾
    if proc.returncode == 0 and os.path.exists(mp4_file):
        original_size = os.path.getsize(ts_file) / (1024*1024)
        new_size = os.path.getsize(mp4_file) / (1024*1024)
        conversion_tasks[task_key].update({
            "status": "completed",
            "progress": 100,
            "end_time": time.time(),
            "original_size": original_size,
            "new_size": new_size
        })
        print(f"轉碼完成: {ts_file} -> {mp4_file}")
        print(f"文件大小: {original_size:.2f}MB -> {new_size:.2f}MB")
        try: os.remove(ts_file)
        except: pass
        return mp4_file
    else:
        conversion_tasks[task_key].update({
            "status": "failed",
            "end_time": time.time()
        })
        print(f"轉碼失敗: {ts_file}")
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


# 定期生成縮圖的函數
def generate_thumbnails_periodically(video_path, task_id_for_log, stop_flag):
    last_size = 0
    thumbnail_interval_seconds = 60  # 每30秒嘗試生成一次縮圖
    min_size_change_for_thumbnail = 1024 * 1024  # 文件大小變化超過1MB才生成
    thumbnail_count = 0
    max_thumbnails_during_recording = 15  # 錄製過程中最多生成10張

    while not stop_flag.is_set():
        time.sleep(thumbnail_interval_seconds)
        
        if thumbnail_count >= max_thumbnails_during_recording:
            write_log(task_id_for_log, "thumbnail_limit", "已達到錄製中縮圖生成上限")
            break
            
        try:
            if not os.path.exists(video_path):
                continue
                
            current_size = os.path.getsize(video_path)
            if current_size <= 0 or (current_size - last_size <= min_size_change_for_thumbnail):
                continue
                
            write_log(task_id_for_log, "thumbnail_attempt", 
                     f"嘗試為 {video_path} 生成縮圖 (大小: {current_size})")
            
            # 使用 ffmpeg 從當前 TS 文件生成一張縮圖
            # 這裡我們只取影片開頭附近的一幀作為臨時縮圖
            # 更複雜的邏輯可以選擇不同的時間點
            base_name = os.path.splitext(os.path.basename(video_path))[0]
            temp_thumbnail_dir = os.path.join(THUMBNAILS_DIR, base_name)
            os.makedirs(temp_thumbnail_dir, exist_ok=True)
            
            # 生成一個唯一的縮圖文件名，避免覆蓋
            thumbnail_filename = f"{base_name}_live_{thumbnail_count + 1:03d}.jpg"
            thumbnail_path = os.path.join(temp_thumbnail_dir, thumbnail_filename)
            
            # 從影片的第 N 秒取一幀 (例如，每30秒取一次，就取第 30*thumbnail_count 秒)
            # 這裡簡化為取影片開頭的幾幀，避免讀取整個文件
            # 注意：對正在寫入的TS文件操作可能不穩定
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-ss", "00:00:01",  # 嘗試從影片的第1秒取幀
                "-frames:v", "1",
                "-vf", "scale=128:-1:flags=lanczos",
                "-qscale:v", "2",
                thumbnail_path
            ]
            
            subprocess.run(ffmpeg_cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            if os.path.exists(thumbnail_path):
                write_log(task_id_for_log, "thumbnail_live_generated", 
                         f"錄製中縮圖生成: {thumbnail_path}")
                thumbnail_count += 1
                last_size = current_size
                
        except Exception as e:
            write_log(task_id_for_log, "thumbnail_live_error", 
                     f"錄製中生成縮圖錯誤: {str(e)}")


def record_stream(task):
    # 準備存放路徑
    save_path = os.path.join(RECORDINGS_DIR, task.save_dir.strip("/"))
    os.makedirs(save_path, exist_ok=True)

    handler = get_handler(task)
    # 解析 URL 清單（追劇模式或特定站點）
    urls = handler.parse_urls(task.url)
    # 若無列表，則以單一 URL 處理
    if not urls:
        urls = [task.url]

    # 讀取已錄列表
    meta_file = os.path.join(save_path, "recorded.json")
    recorded = set()
    if os.path.exists(meta_file):
        recorded = set(json.load(open(meta_file, 'r', encoding='utf-8')))

    # 產生統一 out_file
    u = handler.get_new_url(urls, recorded)
    nowstr = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(save_path, f"{task.name}_{nowstr}.ts")

    # 使用統一的介面啟動錄影
    proc = handler.start_recording(handler.get_final_url(u), task, out_file)

    write_log(task.id, "start", f"CMD: {' '.join(base_cmd)}")
    proc = None
    conversion_triggered = False # 新增標誌，用於跟踪是否已觸發轉碼
    thumbnail_thread = None # 用於在錄製過程中生成縮圖的線程
    stop_flag = threading.Event()

    try:
        # ========== 註冊進程 ==========
        proc = subprocess.Popen(base_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        active_recordings[task.id] = proc

        # 啟動定期生成縮圖的線程
        thumbnail_thread = threading.Thread(target=generate_thumbnails_periodically, args=(out_file, task.id, stop_flag), daemon=True)
        thumbnail_thread.start()

        stdout, stderr = proc.communicate()
        std_out_msg = stdout.decode("utf-8").strip() if stdout else ""
        std_err_msg = stderr.decode("utf-8").strip() if stderr else ""
        if proc.returncode == 0:
            write_log(task.id, "end", f"SUCCESS: {out_file}")
            # --- 自動轉成 MP4 --- (統一使用 ts_to_mp4 函數)
            if os.path.exists(out_file):
                # 標記已錄
                recorded.add(u)
                with open(meta_file, 'w', encoding='utf-8') as mf:
                    json.dump(list(recorded), mf, ensure_ascii=False, indent=2)

                # 錄製完成後，生成最終的完整縮圖集
                generate_thumbnail(out_file) # 使用原始的 generate_thumbnail 生成完整縮圖
                # 使用任務中定義的預設品質，如果沒有則使用 'high'
                quality_to_use = task.default_conversion_quality if task.default_conversion_quality else "high"
                convert_recording(task.id, out_file, quality=quality_to_use)
                conversion_triggered = True # 標記已觸發轉碼
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
        stop_flag.set()
        if thumbnail_thread and thumbnail_thread.is_alive():
            # 確保縮圖線程結束 (雖然是 daemon，但明確 join 更安全)
            # proc.poll() is None 條件在上面循環中已處理，這裡可以簡化
            pass 

        # 確保在 finally 區塊也呼叫 ts_to_mp4，以處理可能的例外情況
        # 只有在 try 區塊中沒有觸發轉碼，並且文件存在時才觸發
        if not conversion_triggered and os.path.exists(out_file):
            generate_thumbnail(out_file) # 確保即使錄製失敗也有縮圖
            # 使用任務中定義的預設品質，如果沒有則使用 'high'
            quality_to_use = task.default_conversion_quality if task.default_conversion_quality else "high"
            convert_recording(task.id, out_file, quality=quality_to_use)

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
            quality_to_use = t['default_conversion_quality'] if t['default_conversion_quality'] else "high"
            convert_recording(task_id, ts_file_path, quality=quality_to_use)
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