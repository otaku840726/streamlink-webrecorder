import os
import re
import requests
import json
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime
from handlers.base_handler import StreamHandler
from playwright.async_api import async_playwright
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
        1. 在內部建立一個 asyncio event loop，執行 Playwright 協程。
        2. 協程內容：初始化浏览器、前往 url 點擊播放、攔截對 video_src 發出的 request，取得它的 headers。
        3. 關閉 Playwright 之後，用 requests.get(...) 搭配攔截到的 headers 同步下載影片。
        """

        async def _fetch_video_request():
            # 初始化（或重用）Playwright persistent context
            await self.init_browser()

            try:
                # 前往目標頁面並點擊播放
                await self.page.goto(url, wait_until="load")
                await self.page.click(".vjs-big-play-centered")

                # 等待 <video> element 有 src 屬性
                await self.page.wait_for_function(
                    "() => !!(document.querySelector('video') && document.querySelector('video').src)"
                )
                video_src = await self.page.evaluate("() => document.querySelector('video').src")

                # 攔截瀏覽器對 video_src 發出的那筆 request
                video_request = await self.page.wait_for_request(lambda req: req.url == video_src)
                req_headers = video_request.headers

                return video_src, req_headers
            finally:
                # 一定要關閉瀏覽器 context
                await self.close_browser()

        # 1. 建立一個新的 event loop，執行上面那段協程
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            video_src, req_headers = loop.run_until_complete(_fetch_video_request())
        finally:
            loop.close()

        # 2. 用 requests.get 同步下載，用攔截到的 headers 保持與瀏覽器完全一致
        r = requests.get(video_src, headers=req_headers, stream=True)
        content_length = int(r.headers.get("content-length", 0))

        if r.status_code == 200:
            file_name = os.path.basename(out_file)
            print(f"+ 開始下載：{file_name}（{content_length/1024/1024:.2f} MB）")

            with open(out_file, "wb") as f:
                for chunk in r.iter_content(chunk_size=10240):
                    if not chunk:
                        continue
                    f.write(chunk)
                    f.flush()

            print(f"  下載完畢：{out_file}")
        else:
            print(f"- 下載失敗：HTTP {r.status_code}")
    def __del__(self):
        if self.browser:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.close_browser())
            finally:
                loop.close()
