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

def ts_to_mp4(ts_file, quality="high", use_segmentation=True, task_id=None):
    """
    將 TS 檔轉換為高壓縮率的 MP4 檔，支援 Intel QSV 硬體加速
    
    參數:
    - ts_file: TS 文件路徑
    - quality: 壓縮品質 ("extreme", "high", "medium", "low")
    - use_segmentation: 是否使用分段處理（適用於大文件）
    - task_id: 任務 ID，用於記錄日誌
    
    返回:
    - 成功時返回 MP4 文件路徑，失敗時返回 None
    """
    import os
    import subprocess
    import shutil
    import tempfile
    import time
    from datetime import datetime
    
    if not os.path.exists(ts_file):
        print(f"錯誤: 找不到 TS 文件 {ts_file}")
        return None
    
    # 獲取文件大小 (MB)
    file_size_mb = os.path.getsize(ts_file) / (1024 * 1024)
    print(f"開始處理 {ts_file}，大小: {file_size_mb:.2f} MB")
    
    # 如果任務 ID 為空，從文件路徑中提取
    if task_id is None:
        try:
            # 假設目錄結構是 /recordings/任務目錄/文件名
            task_id = os.path.basename(os.path.dirname(ts_file))
        except:
            task_id = "unknown"
    
    # 嘗試檢測是否支援 Intel QSV
    try:
        qsv_check = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        has_qsv = "h264_qsv" in qsv_check.stdout
        has_hevc_qsv = "hevc_qsv" in qsv_check.stdout
    except Exception:
        has_qsv = False
        has_hevc_qsv = False
    
    # 壓縮預設值 - 從極端壓縮到低壓縮
    compression_presets = {
        "extreme": {
            "video_codec": "hevc_qsv" if has_hevc_qsv else "libx265",
            "crf": "32" if not has_hevc_qsv else None,  # QSV 不使用 CRF
            "bitrate": "1000k" if has_hevc_qsv else None,  # QSV 使用碼率控制
            "preset": "veryslow" if not has_hevc_qsv else None,  # QSV 不使用此預設
            "qsv_params": ["global_quality=28", "preset=veryslow"] if has_hevc_qsv else [],
            "audio_codec": "aac",
            "audio_bitrate": "48k",
            "resolution": None,
            "extra": [] if has_hevc_qsv else ["-x265-params", "bframes=8:psy-rd=1:aq-mode=3:aq-strength=1.0:deblock=1,1:sao=1:rect=1:amp=1:limit-refs=1"]
        },
        "high": {
            "video_codec": "hevc_qsv" if has_hevc_qsv else "libx265",
            "crf": "28" if not has_hevc_qsv else None,
            "bitrate": "2000k" if has_hevc_qsv else None,
            "preset": "veryslow" if not has_hevc_qsv else None,
            "qsv_params": ["global_quality=23", "preset=slow"] if has_hevc_qsv else [],
            "audio_codec": "aac",
            "audio_bitrate": "64k",
            "resolution": None,
            "extra": [] if has_hevc_qsv else ["-x265-params", "bframes=8:psy-rd=1:aq-mode=3:aq-strength=0.8:deblock=1,1"]
        },
        "medium": {
            "video_codec": "h264_qsv" if has_qsv else "libx265",
            "crf": "25" if not has_qsv else None,
            "bitrate": "3000k" if has_qsv else None,
            "preset": "slow" if not has_qsv else None,
            "qsv_params": ["global_quality=18", "preset=medium"] if has_qsv else [],
            "audio_codec": "aac",
            "audio_bitrate": "96k",
            "resolution": None,
            "extra": [] if has_qsv else ["-x265-params", "bframes=5:psy-rd=1"]
        },
        "low": {
            "video_codec": "h264_qsv" if has_qsv else "libx264",
            "crf": "23" if not has_qsv else None,
            "bitrate": "4000k" if has_qsv else None,
            "preset": "medium" if not has_qsv else None,
            "qsv_params": ["global_quality=15", "preset=fast"] if has_qsv else [],
            "audio_codec": "aac",
            "audio_bitrate": "128k",
            "resolution": None,
            "extra": []
        }
    }
    
    # 選擇壓縮設置
    compression = compression_presets.get(quality, compression_presets["extreme"])
    
    # 輸出文件路徑
    mp4_file = ts_file.rsplit('.', 1)[0] + ".mp4"
    start_time = time.time()
    
    # 日誌記錄
    def write_compression_log(message):
        if task_id:
            write_log(task_id, "mp4_compression", message)
        print(message)
    
    # 記錄使用的編碼器
    hw_accel_msg = "使用 Intel QSV 硬體加速" if (has_qsv and "qsv" in compression["video_codec"]) else "使用軟體編碼"
    write_compression_log(f"開始轉換 {os.path.basename(ts_file)} 為 MP4，壓縮級別: {quality}，{hw_accel_msg}")
    
    # 檢查文件大小，決定是否使用分段處理
    large_file = file_size_mb > 500  # 大於 500MB 的文件考慮使用分段處理
    
    if large_file and use_segmentation:
        write_compression_log(f"檔案較大 ({file_size_mb:.2f}MB)，使用分段處理")
        
        # 分段處理大文件
        temp_dir = tempfile.mkdtemp()
        try:
            # 1. 分割成小段 (每段 2 分鐘)
            segment_time = 120
            segments_cmd = [
                "ffmpeg", "-i", ts_file,
                "-f", "segment",
                "-segment_time", str(segment_time),
                "-reset_timestamps", "1",
                "-c", "copy",
                os.path.join(temp_dir, "segment_%03d.ts")
            ]
            
            write_compression_log("將大文件分段...")
            subprocess.run(segments_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # 2. 轉換每個分段
            segments = sorted([f for f in os.listdir(temp_dir) if f.startswith("segment_") and f.endswith(".ts")])
            write_compression_log(f"共分為 {len(segments)} 個分段，逐一處理...")
            
            mp4_segments = []
            for i, segment in enumerate(segments):
                segment_path = os.path.join(temp_dir, segment)
                mp4_segment = segment_path.replace(".ts", ".mp4")
                
                # 構建分段轉換命令
                segment_cmd = ["ffmpeg", "-y", "-i", segment_path]
                
                # 添加解析度縮放（如果有）
                if compression["resolution"]:
                    segment_cmd.extend(["-vf", compression["resolution"]])
                
                # 添加 QSV 專用參數
                if "qsv" in compression["video_codec"] and compression["qsv_params"]:
                    segment_cmd.extend(["-load_plugin", "hevc_hw", "-init_hw_device", "qsv=hw", "-filter_hw_device", "hw"])
                    qsv_params = ":".join(compression["qsv_params"])
                    segment_cmd.extend(["-c:v", compression["video_codec"], "-qsv_params", qsv_params])
                    if compression["bitrate"]:
                        segment_cmd.extend(["-b:v", compression["bitrate"]])
                else:
                    # 添加視頻編碼設置
                    segment_cmd.extend(["-c:v", compression["video_codec"]])
                    if compression["crf"]:
                        segment_cmd.extend(["-crf", compression["crf"]])
                    if compression["preset"]:
                        segment_cmd.extend(["-preset", compression["preset"]])
                
                # 添加音頻編碼設置
                segment_cmd.extend([
                    "-c:a", compression["audio_codec"],
                    "-b:a", compression["audio_bitrate"],
                    "-movflags", "+faststart",
                    "-pix_fmt", "yuv420p"
                ])
                
                # 添加額外參數
                if compression["extra"]:
                    segment_cmd.extend(compression["extra"])
                
                # 添加輸出文件
                segment_cmd.append(mp4_segment)
                
                # 執行轉換
                write_compression_log(f"處理分段 {i+1}/{len(segments)}...")
                try:
                    subprocess.run(segment_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    mp4_segments.append(mp4_segment)
                except subprocess.CalledProcessError as e:
                    stderr = e.stderr.decode("utf-8", errors="ignore") if e.stderr else ""
                    write_compression_log(f"分段 {i+1} 處理失敗: {stderr[:200]}")
                    continue
            
            # 3. 合併 MP4 分段
            if not mp4_segments:
                write_compression_log("所有分段處理失敗")
                return None
            
            write_compression_log("合併所有處理完的分段...")
            concat_file = os.path.join(temp_dir, "concat.txt")
            
            with open(concat_file, "w") as f:
                for mp4_segment in mp4_segments:
                    f.write(f"file '{mp4_segment}'\n")
            
            concat_cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                mp4_file
            ]
            subprocess.run(concat_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        except Exception as e:
            write_compression_log(f"分段處理過程中出錯: {str(e)}")
            return None
        finally:
            # 清理臨時目錄
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
    
    else:
        # 直接處理單個文件
        try:
            # 構建 ffmpeg 命令
            ffmpeg_cmd = ["ffmpeg", "-y", "-i", ts_file]
            
            # 如果使用 QSV，添加 QSV 專用參數
            if "qsv" in compression["video_codec"]:
                ffmpeg_cmd.extend(["-init_hw_device", "qsv=hw", "-filter_hw_device", "hw"])
                
                # 添加解析度縮放（如果有）
                if compression["resolution"]:
                    ffmpeg_cmd.extend(["-vf", f"format=nv12,hwupload=extra_hw_frames=64,scale_qsv={compression['resolution']},hwdownload,format=nv12"])
                else:
                    ffmpeg_cmd.extend(["-vf", "format=nv12,hwupload=extra_hw_frames=64,hwdownload,format=nv12"])
                
                # 添加 QSV 專用視頻編碼設置
                ffmpeg_cmd.extend(["-c:v", compression["video_codec"]])
                if compression["qsv_params"]:
                    qsv_params = ":".join(compression["qsv_params"])
                    ffmpeg_cmd.extend(["-qsv_params", qsv_params])
                if compression["bitrate"]:
                    ffmpeg_cmd.extend(["-b:v", compression["bitrate"]])
            else:
                # 使用標準軟體編碼
                if compression["resolution"]:
                    ffmpeg_cmd.extend(["-vf", compression["resolution"]])
                
                ffmpeg_cmd.extend([
                    "-c:v", compression["video_codec"],
                    "-crf", compression["crf"],
                    "-preset", compression["preset"]
                ])
            
            # 添加音頻編碼設置
            ffmpeg_cmd.extend([
                "-c:a", compression["audio_codec"],
                "-b:a", compression["audio_bitrate"],
                "-movflags", "+faststart",
                "-pix_fmt", "yuv420p"
            ])
            
            # 添加額外參數
            if compression["extra"]:
                ffmpeg_cmd.extend(compression["extra"])
            
            # 添加輸出文件
            ffmpeg_cmd.append(mp4_file)
            
            # 執行轉換
            write_compression_log(f"執行單文件轉換，命令: {' '.join(ffmpeg_cmd)}")
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode("utf-8", errors="ignore") if e.stderr else ""
            write_compression_log(f"轉換失敗: {stderr[:500]}")
            return None
        except Exception as e:
            write_compression_log(f"未知錯誤: {str(e)}")
            return None
    
    # 檢查轉換結果
    if os.path.exists(mp4_file):
        original_size = os.path.getsize(ts_file)
        compressed_size = os.path.getsize(mp4_file)
        compression_ratio = (1 - compressed_size / original_size) * 100
        elapsed_time = time.time() - start_time
        
        result_msg = (
            f"轉換成功: {os.path.basename(mp4_file)}\n"
            f"原始大小: {original_size/1024/1024:.2f}MB\n"
            f"壓縮大小: {compressed_size/1024/1024:.2f}MB\n"
            f"壓縮比: {compression_ratio:.2f}%\n"
            f"節省空間: {(original_size-compressed_size)/1024/1024:.2f}MB\n"
            f"處理時間: {elapsed_time:.1f}秒\n"
            f"{hw_accel_msg}"
        )
        write_compression_log(result_msg)
        
        # 轉換成功後刪除原始 TS 文件
        try:
            os.remove(ts_file)
            write_compression_log(f"原始 TS 文件已刪除")
        except Exception as e:
            write_compression_log(f"無法刪除原始 TS 文件: {str(e)}")
        
        return mp4_file
    else:
        write_compression_log(f"轉換失敗: 找不到輸出文件")
        return None
        
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

signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)