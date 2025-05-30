import os
import re
import requests
import json
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime
from handlers.base_handler import StreamHandler
from playwright.sync_api import sync_playwright, Page

class GenericBingeHandler(StreamHandler):
    def __init__(self):
        super().__init__()
        self.playwright = None
        self.browser = None
        self.page = None

    def init_browser(self):
        if not self.playwright:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(headless=True)
            self.page = self.browser.new_page()

    def close_browser(self):
        if self.browser:
            self.browser.close()
            self.playwright.stop()
            self.browser = None
            self.playwright = None
            self.page = None

    def parse_urls(self, start_url: str) -> list[str]:
        """使用 Playwright 取得所有集數連結"""
        episodes = {}
        next_page = start_url
        
        self.init_browser()
        while next_page:
            self.page.goto(next_page, wait_until="load")
            data = self.page.eval_on_selector_all(
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

            nxt = self.page.query_selector('a:has-text("上一頁")')
            if nxt:
                href = nxt.get_attribute("href")
                if href:
                    next_page = href
                    continue
            break

        sorted_nums = sorted(episodes.keys())
        return [episodes[n] for n in sorted_nums]

    def get_new_url(self, urls: str, records: set[str]):
        new_urls = [u for u in urls if u not in records]
        return new_urls[0] if new_urls else None

    def get_final_url(self, episode_url: str):
        """從影片頁面取得實際播放源"""
        self.init_browser()
        self.page.goto(episode_url, wait_until="load")
        self.page.click(".vjs-big-play-centered")
        self.page.wait_for_function(
            "() => !!(document.querySelector('video') && document.querySelector('video').src)"
        )
        return self.page.evaluate("() => document.querySelector('video').src")

    def __del__(self):
        self.close_browser()

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
