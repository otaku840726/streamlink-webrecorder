import os
import re
import requests
import json
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime
from handlers.base_handler import StreamHandler
import asyncio
import multiprocessing
from subprocess import PIPE
import time
import shutil
from pathlib import Path
from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Download

class GenericBingeHandler(StreamHandler):
    def __init__(self):
        super().__init__()
        self.playwright = None
        self.browser = None
        self.page = None

    async def init_browser(self):
        """
        不在本地啟動瀏覽器，而是連到 Browserless 提供的 WebSocket 端點。
        這裡假設環境變數 BROWSERLESS_WS_ENDPOINT 已經設好，格式類似：
          - wss://chrome.browserless.io?token=YOUR_TOKEN
          - ws://localhost:3000/playwright       (視你架的映像而定)

        因為 browserless.io 預設會以 CDP （Chrome DevTools Protocol）對外服務，所以要使用
        playwright.chromium.connect_over_cdp() 而非 playwright.chromium.launch()。
        """
        if not self.playwright:
            self.playwright = await async_playwright().start()

            # 取得 env 裡的 WebSocket endpoint
            ws_endpoint = os.getenv("BROWSERLESS_WS_ENDPOINT") if os.getenv("BROWSERLESS_WS_ENDPOINT") else '127.0.0.1:3000'
            if not ws_endpoint:
                raise RuntimeError("環境變數 BROWSERLESS_WS_ENDPOINT 尚未設定")

            # 連到遠端 CDP，取得 Browser 實例
            self.browser = await self.playwright.chromium.connect_over_cdp(
                ws_endpoint
            )
            # 在同一個 瀏覽器上下文 裡新開一個分頁／頁籤
            # 如果需要「persistent context」（保留 cookie/session），browserless 也會支援
            context: BrowserContext = await self.browser.new_context(
                accept_downloads=True  # 確保啟動下載功能
            )
            self.page = await context.new_page()

    async def close_browser(self):
        """
        關閉遠端連線。只關閉 Playwright 控制端口，不會關掉
        browserless server 本身（那由服務端自己維護）。
        """
        if self.page:
            # 先關閉頁面
            try:
                await self.page.close()
            except:
                pass
            self.page = None

        if self.browser:
            try:
                await self.browser.close()
            except:
                pass
            self.browser = None

        if self.playwright:
            try:
                await self.playwright.stop()
            except:
                pass
            self.playwright = None

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
        同步 (blocking) 版，利用遠端的 Browserless 下載影片。
        流程概述：
          1. 連到遠端 browserless (init_browser)
          2. 在 page 直接取出 <video> 或 data-src 裡的 URL，不用 click 播放 (避免播放失敗)
          3. 生成 <a download>，觸發瀏覽器下載 (在遠端 context 裡)
          4. 等待 download 事件，呼叫 download.save_as(out_file)
          5. 關閉 playwrigth 控制 client (不關 browserless server)
        """

        async def _fetch_video_and_download():
            # 1. 初始化遠端瀏覽器環境
            await self.init_browser()
            page = self.page

            # 2. 直接導航到影片頁面
            await page.goto(url, wait_until="load")

            # 3. 嘗試從 DOM 直接抓影片 URL，例如 <video src="..." data-src="..."> 或 JS 全域變數
            actual_mp4_url = await page.evaluate(
                """() => {
                    let vid = document.querySelector("video");
                    if (vid) {
                        // (A) <video src="...">
                        if (vid.src) {
                            return vid.src;
                        }
                        // (B) <video data-src="...">
                        const ds = vid.getAttribute("data-src");
                        if (ds) {
                            return ds;
                        }
                    }
                    // (C) 如果有全域 JS 變數，例如 window.videoUrl
                    if (window.videoUrl) {
                        return window.videoUrl;
                    }
                    // 你可以依實際頁面結構自行擴充
                    return "";
                }()"""
            )

            if not actual_mp4_url:
                raise RuntimeError("無法從頁面 DOM 取得影片 URL，請確認 <video> 結構或自定義 JS 變數")

            # 4. 補全協議相對 URL (若以 // 開頭)，或者相對路徑
            if actual_mp4_url.startswith("//"):
                actual_mp4_url = "https:" + actual_mp4_url
            elif actual_mp4_url.startswith("/"):
                # 用 JS 取得當前頁面 origin，再接上相對路徑
                origin = await page.evaluate("() => window.location.origin")
                actual_mp4_url = origin + actual_mp4_url

            # 5. 因為有可能伺服器對影片回傳 206 Partial Content，但瀏覽器內建 download 會自動串聯
            #    在同一個 page 裡註冊等待 download 事件
            download_task = page.wait_for_event("download")

            # 6. 動態注入一段 <a download> 的 JS，立即觸發點擊
            js = f"""
                (() => {{
                  const a = document.createElement("a");
                  a.href = "{actual_mp4_url}";
                  a.download = "";
                  a.style.display = "none";
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a);
                }})();
            """
            await page.evaluate(js)

            # 7. 等候瀏覽器觸發 download 事件
            download: Download = await download_task

            # 8. 把檔案另存到 out_file
            Path(os.path.dirname(out_file)).mkdir(parents=True, exist_ok=True)
            await download.save_as(out_file)

            # 9. 關閉 Playwright 端的資料結構（不會關 browserless server）
            await self.close_browser()

            # 10. 回傳影片 URL + 本地檔案大小
            file_size = os.path.getsize(out_file)
            return actual_mp4_url, file_size

        # —— 同步部分開始 —— 
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            actual_url, size_bytes = loop.run_until_complete(_fetch_video_and_download())
        finally:
            loop.close()

        # 同步列印結果
        filename = os.path.basename(out_file)
        print(f"+ 已下載並儲存：{filename}（{size_bytes/1024/1024:.2f} MB）")
        print(f"  來源 URL：{actual_url}")

    def __del__(self):
        if self.browser:
            try:
                asyncio.run(self.close_browser())
            except Exception:
                pass
