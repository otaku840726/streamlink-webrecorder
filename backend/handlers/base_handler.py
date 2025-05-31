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



class BrowserManager:
    _playwright = None
    _browser: Optional[Browser] = None
    _context: Optional[BrowserContext] = None
    _semaphore = asyncio.Semaphore(1)  # 控制同時最多 3 個任務打開 Page
    _user_data_dir = "/tmp/playwright-user-data-dir"
    _cookie_path = Path(_user_data_dir) / "cookies.json"

    @classmethod
    async def init(cls, headless: bool = False) -> Browser:
        if cls._browser:
            return cls._browser

        cls._playwright = await async_playwright().start()
        cls._browser = await cls._playwright.chromium.launch_persistent_context(
            cls._user_data_dir,
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        cls._context = cls._browser
        print("[BrowserManager] Persistent context 啟動完成。")
        return cls._browser

    @classmethod
    async def new_page(cls, target_url: str) -> Page:
        print(f"[BrowserManager] 準備開啟 {target_url}...")
        async with cls._semaphore:  # 控制併發
            print(f"[BrowserManager] cls._semaphore 獲取成功，準備開啟新的 page")
            await cls.init()
            print(f"[BrowserManager] init 完成")
            page = await cls._context.new_page()
            print(f"[BrowserManager] new_page 完成，開始導向 {target_url}")
            try:
                await cls._restore_cookies(cls._context, target_url)
                await page.goto(target_url, timeout=15000, wait_until="domcontentloaded")
                print(f"[BrowserManager] page.goto 完成: {target_url}")
            except Exception as e:
                print(f"[BrowserManager] page.goto 發生錯誤: {e}")
                await page.close()
                raise
            return page

    @classmethod
    async def _restore_cookies(cls, context: BrowserContext, target_url: str):
        if cls._cookie_path.exists():
            try:
                with open(cls._cookie_path, "r") as f:
                    cookies = json.load(f)
                    await context.add_cookies(cookies)
                    print("[BrowserManager] Cookies 還原完成")
            except Exception as e:
                print(f"[BrowserManager] 還原 cookies 失敗: {e}")

    @classmethod
    async def _save_cookies(cls):
        if cls._context:
            try:
                cookies = await cls._context.cookies()
                with open(cls._cookie_path, "w") as f:
                    json.dump(cookies, f)
                    print("[BrowserManager] Cookies 已儲存")
            except Exception as e:
                print(f"[BrowserManager] 儲存 cookies 失敗: {e}")

    @classmethod
    async def close(cls):
        await cls._save_cookies()
        if cls._browser:
            await cls._browser.close()
            cls._browser = None
        if cls._playwright:
            await cls._playwright.stop()
            cls._playwright = None
        print("[BrowserManager] 瀏覽器已關閉")

    def __del__(self):
        print("[BrowserManager] __del__() 被觸發，請手動確保呼叫 close()")


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