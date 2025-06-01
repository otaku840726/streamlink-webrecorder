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
    _inter_task_delay = 1.0  # 每個任務延遲秒數

    @classmethod
    async def init(cls, use_persistent=False):
        async with cls._lock:
            if cls._browser:
                print("[BrowserManager] Browser 已初始化，略過")
                return cls._browser
            try:
                print("[BrowserManager] 啟動 Playwright...")
                cls._playwright = await async_playwright().start()
                os.makedirs("auth_storage", exist_ok=True)

                if use_persistent:
                    print("[BrowserManager] 使用 persistent context 啟動瀏覽器")
                    cls._context = await cls._playwright.chromium.launch_persistent_context(
                        user_data_dir=cls._user_data_dir,
                        headless=cls._headless,
                    )
                    cls._browser = cls._context.browser
                else:
                    print("[BrowserManager] 使用 ephemeral context 啟動瀏覽器")
                    cls._browser = await cls._playwright.chromium.launch(headless=cls._headless)
                    if os.path.exists(cls._storage_path):
                        print(f"[BrowserManager] 載入已儲存的登入狀態: {cls._storage_path}")
                        cls._context = await cls._browser.new_context(storage_state=cls._storage_path)
                    else:
                        print("[BrowserManager] 尚未有登入狀態，建立新 context")
                        cls._context = await cls._browser.new_context()

                print("[BrowserManager] 初始化完成")
                return cls._browser
            except Exception as e:
                print(f"[BrowserManager][ERROR] 初始化瀏覽器時發生錯誤: {e}")
                raise

    @classmethod
    async def new_page(cls, target_url: str = None) -> Page:
        async with cls._lock:
            try:
                if not cls._context:
                    print("[BrowserManager] Context 尚未初始化，嘗試 init()")
                    await cls.init()

                print("[BrowserManager] 建立新頁面...")
                page = await cls._context.new_page()
                print("[BrowserManager] 頁面建立完成")

                if cls._inter_task_delay > 0:
                    print(f"[BrowserManager] 延遲 {cls._inter_task_delay} 秒以避免併發過快")
                    await asyncio.sleep(cls._inter_task_delay)

                if target_url:
                    print(f"[BrowserManager] 開啟目標網址: {target_url}")
                    await page.goto(target_url)

                return page
            except Exception as e:
                print(f"[BrowserManager][ERROR] 建立頁面時失敗: {e}")
                raise

    @classmethod
    async def save_storage(cls):
        async with cls._lock:
            try:
                if cls._context and not cls._context.is_closed():
                    print(f"[BrowserManager] 儲存登入狀態到 {cls._storage_path}...")
                    await cls._context.storage_state(path=cls._storage_path)
                    print("[BrowserManager] 登入狀態儲存完成")
                else:
                    print("[BrowserManager] Context 已關閉，略過儲存")
            except Exception as e:
                print(f"[BrowserManager][ERROR] 儲存登入狀態時發生錯誤: {e}")

    @classmethod
    async def close(cls):
        async with cls._lock:
            try:
                print("[BrowserManager] 關閉中...")
                if cls._context and not cls._context.is_closed():
                    await cls.save_storage()
                    await cls._context.close()
                    print("[BrowserManager] Context 已關閉")
                else:
                    print("[BrowserManager] Context 已關閉或不存在")

                if cls._browser:
                    await cls._browser.close()
                    print("[BrowserManager] Browser 已關閉")

                cls._browser = None
                cls._context = None
            except Exception as e:
                print(f"[BrowserManager][ERROR] 關閉瀏覽器時發生錯誤: {e}")

    @classmethod
    def set_inter_task_delay(cls, seconds: float):
        print(f"[BrowserManager] 設定任務間延遲為 {seconds} 秒")
        cls._inter_task_delay = seconds




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