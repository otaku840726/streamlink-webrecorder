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


class BrowserManager:
    _playwright = None
    _browser: Browser = None
    _lock = asyncio.Lock()

    @classmethod
    async def init(cls, headless=True):
        async with cls._lock:
            if cls._playwright is None:
                cls._playwright = await async_playwright().start()
            if cls._browser is None:
                cls._browser = await cls._playwright.firefox.launch(headless=headless)
            return cls._browser

    @classmethod
    async def new_page(cls, target_url: str):
        print(f"[BrowserManager] 準備開啟 {target_url}...")
        browser = await cls.init(headless=False)
        print(f"[BrowserManager] init 完成")
        context = await browser.new_context()
        print(f"[BrowserManager] new_context 完成")
        await cls._restore_cookies(context, target_url)
        print(f"[BrowserManager] restore_cookies 完成")
        page = await context.new_page()
        print(f"[BrowserManager] new_page 完成")


        try:
            await page.goto(target_url, timeout=30000)  # 明確指定 timeout 30 秒
            print("[BrowserManager] page.goto 完成")
        except Exception as e:
            print(f"[BrowserManager] page.goto({target_url}) 發生例外：{type(e).__name__}: {e}")

        try:
            await cls._restore_local_storage(page, target_url)
            print("[BrowserManager] localStorage 還原完成")
        except Exception as e:
            print(f"[BrowserManager] 還原 localStorage 發生例外：{type(e).__name__}: {e}")

        return page, context

    @classmethod
    async def save_session(cls, context: BrowserContext, page: Page, target_url: str):
        parsed = urlparse(target_url)
        domain = parsed.netloc.replace(":", "_")
        base_dir = f"./playwright/{domain}"
        os.makedirs(base_dir, exist_ok=True)

        # Save cookies
        cookies = await context.cookies()
        with open(f"{base_dir}/cookies.json", "w", encoding="utf-8") as f:
            json.dump(cookies, f)

        # Save localStorage
        local_data = await page.evaluate("() => Object.fromEntries(Object.entries(localStorage))")
        with open(f"{base_dir}/localstorage.json", "w", encoding="utf-8") as f:
            json.dump(local_data, f)

    @classmethod
    async def _restore_cookies(cls, context: BrowserContext, target_url: str):
        parsed = urlparse(target_url)
        path = f"./playwright/{parsed.netloc}/cookies.json"
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            await context.add_cookies(cookies)

    @classmethod
    async def _restore_local_storage(cls, page: Page, target_url: str):
        parsed = urlparse(target_url)
        path = f"./playwright/{parsed.netloc}/localstorage.json"
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                local_data = json.load(f)
            for key, value in local_data.items():
                await page.evaluate("(k, v) => localStorage.setItem(k, v)", key, value)

    @classmethod
    async def close(cls):
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