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

class GenericBingeHandler(StreamHandler):
    def __init__(self):
        super().__init__()
        self.playwright = None
        self.browser = None
        self.page = None

    async def init_browser(self):
        if not self.playwright:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch_persistent_context(
                    user_data_dir="/root/.config/chromium",
                    headless=True,
                    accept_downloads=True
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
        同步（blocking）版：
        1. 在內部建立一個 asyncio event loop，執行 Playwright 協程 _fetch_video_and_headers()。
        2. 協程內容：初始化瀏覽器、前往 url 點擊播放、等待 <video> .src 被注入，
           然後使用 wait_for_event("request") 攔截對 video_src 的 request，取得 headers。
        3. 關閉 Playwright 之後，用 requests.get(...) 搭配攔截到的 headers 同步下載影片。
        """

        async def _fetch_video_and_headers():
            # 1. 初始化（或重用）靜態 Context
            await self.init_browser()

            try:
                # 2. 前往影片頁面並點擊播放
                await self.page.goto(url, wait_until="load")
                await self.page.click(".vjs-big-play-centered")

                # 3. 等待 <video> element 有 src 屬性
                await self.page.wait_for_function(
                    "() => !!(document.querySelector('video') && document.querySelector('video').src)"
                )
                video_src = await self.page.evaluate("() => document.querySelector('video').src")

                # 4. 攔截瀏覽器對 video_src 發出的那筆 request（使用 wait_for_event）
                media_req = await self.page.wait_for_event(
                    "request",
                    lambda req: req.url == video_src
                )
                req_headers = media_req.headers

                return video_src, req_headers
            finally:
                # 無論如何都要先關閉 Playwright context
                await self.close_browser()

        # —— 同步部分開始 —— 
        # 建立一個新的 event loop，執行上面那段協程
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            video_src, req_headers = loop.run_until_complete(_fetch_video_and_headers())
        finally:
            loop.close()

        # 之後再執行一次關閉，保險起見（_fetch_video_and_headers 已關閉一次）
        try:
            asyncio.run(self.close_browser())
        except Exception:
            pass

        # 5. 用 requests.get 同步下載，用攔截到的 headers 保持與瀏覽器完全一致
        response = requests.get(video_src, headers=req_headers, stream=True)
        content_length = int(response.headers.get("content-length", 0))

        if response.status_code == 200:
            file_name = os.path.basename(out_file)
            print(f"+ 開始下載：{file_name}（{content_length/1024/1024:.2f} MB）")

            with open(out_file, "wb") as f:
                for chunk in response.iter_content(chunk_size=10240):
                    if not chunk:
                        continue
                    f.write(chunk)
                    f.flush()

            print(f"  下載完畢：{out_file}")
        else:
            print(f"- 下載失敗：HTTP {response.status_code}")
            
    def __del__(self):
        if self.browser:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.close_browser())
            finally:
                loop.close()
