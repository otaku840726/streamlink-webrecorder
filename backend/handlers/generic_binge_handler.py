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

class GenericBingeHandler(StreamHandler):
    def __init__(self):
        super().__init__()
        self.playwright = None
        self.browser = None
        self.page = None

    async def init_browser(self):
        if not self.playwright:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
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
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.get_video_src_async(episode_url))
        finally:
            loop.close()

    def __del__(self):
        if self.browser:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.close_browser())
            finally:
                loop.close()

    def build_cmd(self, url: str, task, out_file: str) -> list[str]:
        print(f"[DEBUG] build_cmd called with url={url}, out_file={out_file}")
        # 這裡用 streamlink 或 ffmpeg 取決於你註冊的 handler
        # 下面示範 Streamlink 模式
        cmd = [
            'streamlink',
            *(task.params.split() if task.params else []),
            url,           # 注意要用這裡傳入的 url
            'best',
            '-o', out_file
        ]
        print(f"[DEBUG] Generated command: {' '.join(cmd)}")
        return cmd
