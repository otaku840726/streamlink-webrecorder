import re
from abc import ABC, abstractmethod
import multiprocessing
from subprocess import PIPE
import subprocess
import os, json, asyncio
from urllib.parse import urlparse
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from pathlib import Path
from typing import Optional

_registry = []

def register_handler(pattern):
    def deco(cls):
        _registry.append((re.compile(pattern), cls()))
        return cls
    return deco



import os
import asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

class BrowserManager:
    _browser: Browser = None
    _context: BrowserContext = None
    _storage_path = "auth_storage/state.json"
    _user_data_dir = "auth_storage/user_data"
    _headless = False
    _lock = asyncio.Lock()
    _inter_task_delay = 10.0  # 每個任務之間的延遲秒數

    @classmethod
    async def init(cls, use_persistent=False):
        async with cls._lock:
            if cls._browser:
                return cls._browser

            playwright = await async_playwright().start()
            os.makedirs("auth_storage", exist_ok=True)

            if use_persistent:
                cls._context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=cls._user_data_dir,
                    headless=cls._headless,
                )
                cls._browser = cls._context.browser
            else:
                cls._browser = await playwright.chromium.launch(headless=cls._headless)
                cls._context = await cls._browser.new_context(
                    storage_state=cls._storage_path if os.path.exists(cls._storage_path) else None
                )
            return cls._browser

    @classmethod
    async def new_page(cls, target_url: str = None) -> Page:
        async with cls._lock:
            if not cls._context:
                await cls.init()
            page = await cls._context.new_page()

            # 加入操作後延遲
            await asyncio.sleep(cls._inter_task_delay)

        if target_url:
            await page.goto(target_url)
        return page

    @classmethod
    async def save_storage(cls):
        async with cls._lock:
            if cls._context and not cls._context.is_closed():
                await cls._context.storage_state(path=cls._storage_path)

    @classmethod
    async def close(cls):
        async with cls._lock:
            if cls._context and not cls._context.is_closed():
                await cls.save_storage()
                await cls._context.close()
            if cls._browser:
                await cls._browser.close()
            cls._browser = None
            cls._context = None



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