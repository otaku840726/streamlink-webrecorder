import os
import re
import requests
import json
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime
from handlers.base_handler import StreamHandler
from playwright.async_api import async_playwright, Page, BrowserContext
import asyncio
import multiprocessing
from subprocess import PIPE
import time
import shutil

class GenericBingeHandler(StreamHandler):
    def __init__(self):
        super().__init__()
        self.playwright = None
        self.browser = None
        self.page = None

    async def init_browser(self):
        if not self.playwright:
            self.playwright = await async_playwright().start()
            
            # self.browser = await self.playwright.chromium.launch_persistent_context(
            #         user_data_dir="/root/.config/chromium",
            #         headless=False,
            #         accept_downloads=True
            #     )

            system_firefox = shutil.which("firefox")
            if not system_firefox:
                raise RuntimeError("系統上找不到 firefox，可先安裝或指定正確路徑")
            self.browser = await self.playwright.firefox.launch(
                headless=False,
                executable_path=system_firefox
            )
            
            self.page = await self.browser.new_page()

    async def close_browser(self):
        if self.browser:
            await self.browser.close()
            await self.playwright.stop()
            self.browser = None
            self.playwright = None
            self.page = None

    async def get_episode_urls_async(self, category_url: str) -> list[str]:
        episodes = {}
        next_page = category_url
        
        await self.init_browser()
        try:
            while next_page:
                await self.page.goto(next_page, wait_until="load")
                data = await self.page.eval_on_selector_all(
                    ".entry-title a",
                    """els => els.map(e => ({
                        href: e.href,
                        title: e.textContent.trim()
                    }))"""
                )
                
                for item in data:
                    m = re.search(r'\[(\d+)\]', item["title"])
                    if m:
                        num = int(m[1])
                        if num not in episodes:
                            episodes[num] = item["href"]

                nxt = await self.page.query_selector('a:has-text("上一頁")')
                if nxt:
                    href = await nxt.get_attribute("href")
                    if href:
                        next_page = href
                        continue
                break
        finally:
            await self.close_browser()

        sorted_nums = sorted(episodes.keys())
        return [episodes[n] for n in sorted_nums]

    def parse_urls(self, start_url: str) -> list[str]:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.get_episode_urls_async(start_url))
        finally:
            loop.close()

    def get_new_url(self, urls: str, records: set[str]):
        new_urls = [u for u in urls if u not in records]
        return new_urls[0] if new_urls else None
        
    async def get_video_src_async(self, episode_url: str) -> str:
        await self.init_browser()
        try:
            await self.page.goto(episode_url, wait_until="load")
            await self.page.click(".vjs-big-play-centered")
            await self.page.wait_for_function(
                "() => !!(document.querySelector('video') && document.querySelector('video').src)"
            )
            return await self.page.evaluate("() => document.querySelector('video').src")
        finally:
            await self.close_browser()

    def get_final_url(self, episode_url: str):
        return episode_url
        # loop = asyncio.new_event_loop()
        # asyncio.set_event_loop(loop)
        # try:
        #     return loop.run_until_complete(self.get_video_src_async(episode_url))
        # finally:
        #     loop.close()

    def build_cmd(self, url: str, task, out_file: str) -> list[str]:
        """不使用命令列模式"""
        return None

    def build_method(self, url: str, task, out_file: str):
        """
        同步 (blocking) 版，直接在同一個分頁利用 <a download> 下載 .mp4：
        1. 攔截第一筆 .mp4 回應（包括 206 Partial），取得真正串流 URL。
        2. 在同一個 self.page 中動態產生 <a download> 並點擊，等待 download 事件，儲存到 out_file。
        """

        async def _fetch_and_dl_in_same_page():
            # 1. 初始化 Playwright browser context
            await self.init_browser()
            page = self.page

            # 2. 先註冊等待「URL 以 .mp4 結尾且 status 為 200 或 206」的 response
            mp4_response_task = page.wait_for_event(
                "response",
                lambda resp: resp.url.lower().endswith(".mp4") and resp.status in (200, 206)
            )

            # 3. 前往播放頁並觸發播放
            await page.goto(url, wait_until="load")
            await page.click(".vjs-big-play-centered")

            # 4. 等待那筆 .mp4 回應到來，取得最終串流 URL
            mp4_resp = await mp4_response_task
            actual_mp4_url = mp4_resp.url

            # 5. 註冊同一個分頁的 download 事件
            download_task = page.wait_for_event("download")

            # 6. 在同一個分頁裡動態插入 <a download>，並自動點擊
            #    這段 JavaScript 會把 <a> 加到 DOM 中並觸發 click()
            js = f'''
                (() => {{
                  const a = document.createElement("a");
                  a.href = "{actual_mp4_url}";
                  a.download = "";            // 只要有 download 屬性，瀏覽器就會視為下載
                  a.style.display = "none";   // 不顯示在畫面上
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a); // 下載觸發後可以移除
                }})();
            '''
            await page.evaluate(js)

            # 7. 等待瀏覽器真正觸發 download 事件
            download: Download = await download_task

            # 8. 下載完成後把檔案存在 out_file
            Path(os.path.dirname(out_file)).mkdir(parents=True, exist_ok=True)
            await download.save_as(out_file)

            # 9. 關閉瀏覽器 context，釋放資源
            await self.close_browser()

            # 10. 回傳來源 URL 以及檔案大小（bytes）
            file_size = os.path.getsize(out_file)
            return actual_mp4_url, file_size

        # —— 把上述 async 包在同步流程裡運行 —— 
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            actual_url, size_bytes = loop.run_until_complete(_fetch_and_dl_in_same_page())
        finally:
            loop.close()

        # 同步輸出結果
        filename = os.path.basename(out_file)
        print(f"+ 已下載並儲存：{filename}（{size_bytes/1024/1024:.2f} MB）")
        print(f"  來源 URL：{actual_url}")

    def __del__(self):
        if self.browser:
            try:
                asyncio.run(self.close_browser())
            except Exception:
                pass
