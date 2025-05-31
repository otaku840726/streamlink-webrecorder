import re
from abc import ABC, abstractmethod
import multiprocessing
from subprocess import PIPE
import subprocess
        
from handlers.streamlink_handler import StreamlinkHandler
from handlers.bahamut_handler import BahamutHandler
from handlers.anime1_handler import Anime1Handler

_registry = []

def register_handler(pattern):
    def deco(cls):
        _registry.append((re.compile(pattern), cls()))
        return cls
    return deco

class StreamHandler(ABC):
    @abstractmethod
    def parse_urls(self, start_url: str) -> list[str]:
        """解析起始 URL，返回 m3u8 連結列表"""
        return start_url

    @abstractmethod
    def get_new_url(self, urls: str, records: set[str]):
        return urls[0]

    @abstractmethod
    def get_final_url(self, episode_url: str):
        """
        根據選中的 episode_url 做進一步處理，取得最終要給 build_cmd 的 url
        預設直接回傳 episode_url，子類可覆寫此方法
        """
        return episode_url

    @abstractmethod
    def get_ext(self):
        return "ts"

    @abstractmethod
    def build_cmd(self, url: str, task, out_file: str) -> list[str]:
        """舊的命令列介面，為了向後相容而保留"""
        pass

    @abstractmethod
    def build_method(self, url: str, task, out_file: str):
        """建構錄影方法，回傳一個可被 multiprocessing.Process 執行的函數"""
        pass

    def start_recording(self, url: str, task, out_file: str):
        """統一的錄影啟動介面，優先使用 build_cmd"""
        cmd = self.build_cmd(url, task, out_file)
        if cmd:
            return subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        
        # 如果沒有 cmd 才使用 build_method
        terminated = multiprocessing.Event()
        proc = multiprocessing.Process(
            target=self.build_method(url, task, out_file),
            args=(terminated,),
            daemon=True
        )
        proc.stdout = PIPE
        proc.stderr = PIPE
        proc.terminate = lambda: terminated.set()
        proc.start()
        return proc

def get_handler(task) -> StreamHandler:
    # 依 tool 選擇預設 handler
    if task.tool == 'custom':
        # 先匹配專屬 handler
        for pattern, handler in _registry:
            print(f"[DEBUG] 匹配專屬 handler：{pattern} for {task.url}")
            if pattern.search(task.url):
                print(f"[DEBUG] 匹配到專屬 handler：{handler} for {task.url}")
                return handler
    print(f"[DEBUG] 使用預設 handler：StreamlinkHandler for {task.url}")
    return StreamlinkHandler()