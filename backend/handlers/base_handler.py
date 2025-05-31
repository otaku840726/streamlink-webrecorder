import re
from abc import ABC, abstractmethod
import multiprocessing
from subprocess import PIPE
import subprocess
from playwright.async_api import async_playwright, BrowserContext
import asyncio
        
_registry = []

def register_handler(pattern):
    def deco(cls):
        _registry.append((re.compile(pattern), cls()))
        return cls
    return deco


class BrowserManager:
    _playwright = None
    _context: BrowserContext = None
    _lock = asyncio.Lock()
    _init_task = None

    @classmethod
    async def init(cls, user_data_dir="./playwright", headless=False):
        print("[BrowserManager] init() called")
        async with cls._lock:
            if cls._context:
                return cls._context
            if cls._init_task:
                return await cls._init_task

            async def _do_init():
                cls._playwright = await async_playwright().start()
                cls._context = await cls._playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=headless,
                    accept_downloads=True,
                    viewport={"width": 1280, "height": 800},
                )
                print("[BrowserManager] Persistent context 啟動完成。")
                return cls._context

            cls._init_task = asyncio.create_task(_do_init())
            return await cls._init_task

    @classmethod
    async def close(cls):
        if cls._context:
            await cls._context.close()
            cls._context = None
        if cls._playwright:
            await cls._playwright.stop()
            cls._playwright = None

class StreamHandler(ABC):
    @abstractmethod
    def parse_urls(self, start_url: str) -> list[str]:
        """解析起始 URL，返回 m3u8 連結列表"""
        pass

    @abstractmethod
    def get_new_url(self, urls: str, records: set[str]):
        pass

    @abstractmethod
    def get_final_url(self, episode_url: str):
        """
        根據選中的 episode_url 做進一步處理，取得最終要給 build_cmd 的 url
        預設直接回傳 episode_url，子類可覆寫此方法
        """
        pass

    @abstractmethod
    def get_ext(self):
        pass

    @abstractmethod
    def get_filename(self, url: str, task) -> str:
        pass

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

from handlers.streamlink_handler import StreamlinkHandler
from handlers.bahamut_handler import BahamutHandler
from handlers.anime1_handler import Anime1Handler

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