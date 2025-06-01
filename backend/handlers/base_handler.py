import re
from abc import ABC, abstractmethod
import multiprocessing
from subprocess import PIPE
import subprocess
import os, json, asyncio
from urllib.parse import urlparse
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
        
_registry = []

def register_handler(pattern):
    def deco(cls):
        _registry.append((re.compile(pattern), cls()))
        return cls
    return deco


import asyncio
import os
import json
from urllib.parse import urlparse
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

STORAGE_PATH = "/playwright"

class BrowserManager:
    _semaphore = asyncio.Semaphore(1)
    _playwright = None
    _browser: Browser = None
    _contexts: dict[str, BrowserContext] = {}
    _lock = asyncio.Lock()
    _persistent_mode = False

    @classmethod
    async def init(cls, persistent: bool = False, headless: bool = True):
        cls._persistent_mode = persistent

        async with cls._lock:
            if cls._playwright is None:
                cls._playwright = await async_playwright().start()

            if persistent:
                # 使用 persistent_context -> 不需要 browser 物件
                return

            if cls._browser is None:
                cls._browser = await cls._playwright.chromium.launch(
                    headless=headless,
                    args=["--no-sandbox", "--disable-dev-shm-usage"]
                )

    @classmethod
    async def get_context(cls, context_id: str, headless: bool = True) -> BrowserContext:
        print(f"[BrowserManager] get_context({context_id})")
        if context_id in cls._contexts:
            print(f"[BrowserManager] context 已存在：{context_id}")
            return cls._contexts[context_id]

        print(f"[BrowserManager] context 不存在：{context_id}")
        base_dir = f"{STORAGE_PATH}/{context_id}"
        os.makedirs(base_dir, exist_ok=True)
        print(f"[BrowserManager] base_dir: {base_dir}")

        if cls._persistent_mode:
            print(f"[BrowserManager] persistent 模式，使用 launch_persistent_context")
            context = await cls._playwright.chromium.launch_persistent_context(
                user_data_dir=base_dir,
                headless=headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            print(f"[BrowserManager] launch_persistent_context 成功")
        else:
            print(f"[BrowserManager] 非 persistent 模式，使用 new_context")
            storage_path = os.path.join(base_dir, "state.json")
            print(f"[BrowserManager] storage_path: {storage_path}")
            context = await cls._browser.new_context(
                storage_state=storage_path
            )
            print(f"[BrowserManager] new_context 成功")

        cls._contexts[context_id] = context
        print(f"[BrowserManager] context 已儲存：{context_id}")
        return context

    @classmethod
    async def new_page(cls, context_id: str, target_url: str, headless: bool = False):
        print(f"[BrowserManager] 開啟 {target_url} for {context_id} (persistent={cls._persistent_mode})")
        async with cls._semaphore:
            print(f"[BrowserManager] semaphore acquired for {context_id}")
            context = await cls.get_context(context_id, headless=headless)
            print(f"[BrowserManager] context acquired for {context_id}")
            page = await context.new_page()
            print(f"[BrowserManager] page acquired for {context_id}")
            try:
                print(f"[BrowserManager] 前往 {target_url}")
                await page.goto(target_url, timeout=15000)
                print(f"[BrowserManager] 前往 {target_url} 成功")
                return page
            except Exception as e:
                print(f"[BrowserManager] page.goto() 失敗: {e}")
                await page.close()
                raise

    @classmethod
    async def save_session(cls, context_id: str):
        if cls._persistent_mode:
            print(f"[BrowserManager] persistent 模式不需手動 save_session")
            return

        context = cls._contexts.get(context_id)
        if not context:
            print(f"[BrowserManager] 無對應 context: {context_id}")
            return

        storage_path = f"{STORAGE_PATH}/{context_id}/state.json"
        await context.storage_state(path=storage_path)
        print(f"[BrowserManager] 儲存狀態至 {storage_path}")

    @classmethod
    async def close(cls):
        if not cls._persistent_mode:
            for context_id, context in cls._contexts.items():
                try:
                    storage_path = f"{STORAGE_PATH}/{context_id}/state.json"
                    await context.storage_state(path=storage_path)
                    print(f"[BrowserManager] 自動儲存 {context_id} 狀態至 {storage_path}")
                except Exception as e:
                    print(f"[BrowserManager] 儲存 {context_id} 狀態失敗: {e}")

        for context in cls._contexts.values():
            await context.close()
        cls._contexts.clear()

        if cls._browser:
            await cls._browser.close()
            cls._browser = None

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