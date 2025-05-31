import os
import re
import requests
import json
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime
from handlers.base_handler import StreamHandler
from playwright.async_api import async_playwright, Page, BrowserContext, Download
import asyncio
import multiprocessing
from subprocess import PIPE
import time
import shutil
from pathlib import Path
from urllib.parse import urlparse


@register_handler(r"^https?://(?:www\.)?ani\.gamer\.com\.tw/.*")
class BahamutHandler(StreamHandler):
    def __init__(self):
        super().__init__()
        print("[DEBUG] BahamutHandler.__init__(): 初始化 Handler")
        self.playwright = None
        self.browser = None
        self.page = None

    async def init_browser(self):
        print("[DEBUG] init_browser() called.")
        if not self.playwright:
            print("[DEBUG] Playwright 尚未啟動，開始啟動 Playwright...")
            self.playwright = await async_playwright().start()
            print("[DEBUG] Playwright 已啟動。")

            print("[DEBUG] 正在使用 Firefox 建立 persistent context...")
            self.browser = await self.playwright.firefox.launch_persistent_context(
                user_data_dir="./playwright",
                headless=False,
                accept_downloads=True,
                viewport={"width": 1280, "height": 800},
            )
            print("[DEBUG] Firefox persistent context 建立完成。")

            # 可選擇改用系統 firefox
            # system_firefox = shutil.which("firefox")
            # if not system_firefox:
            #     raise RuntimeError("系統上找不到 firefox，可先安裝或指定正確路徑")
            # self.browser = await self.playwright.firefox.launch(
            #     headless=False,
            #     executable_path=system_firefox
            # )

            print("[DEBUG] 建立新分頁 (new_page)...")
            self.page = await self.browser.new_page()
            print("[DEBUG] 分頁建立完成。")
        else:
            print("[DEBUG] Playwright 已在運行，跳過啟動步驟。")

    async def close_browser(self):
        """
        關閉 browser 控制端，但不會關掉 browserless server（若有使用）
        """
        print("[DEBUG] close_browser() called.")
        if self.page:
            print("[DEBUG] 嘗試關閉 page...")
            try:
                await self.page.close()
                print("[DEBUG] page 關閉成功。")
            except Exception as e:
                print(f"[WARNING] page.close() 遇到例外: {e}")
            self.page = None
        else:
            print("[DEBUG] 沒有 page 需要關閉。")

        if self.browser:
            print("[DEBUG] 嘗試關閉 browser context...")
            try:
                await self.browser.close()
                print("[DEBUG] browser context 關閉成功。")
            except Exception as e:
                print(f"[WARNING] browser.close() 遇到例外: {e}")
            self.browser = None
        else:
            print("[DEBUG] 沒有 browser context 需要關閉。")

        if self.playwright:
            print("[DEBUG] 嘗試停止 Playwright...")
            try:
                await self.playwright.stop()
                print("[DEBUG] Playwright 停止成功。")
            except Exception as e:
                print(f"[WARNING] playwright.stop() 遇到例外: {e}")
            self.playwright = None
        else:
            print("[DEBUG] Playwright 已經是 None，無須停止。")



    def get_ext(self):
        return "ts"
        
    def build_cmd(self, url: str, task, out_file: str) -> list[str]:
        """不使用命令列模式"""
        print(f"[DEBUG] build_cmd() called with url={url}, task={task}, out_file={out_file}")
        return None

    def build_method(self, url: str, task, out_file: str):
        """
        這個版本示範：
        1. 用 Playwright 點擊「同意」(id="adult")，讓廣告開始播放
        2. 等待最多 40 秒，監聽所有 response，找出第 一 個 .m3u8 請求，
           並將那次 request 的 headers 全部讀出
        3. 關閉瀏覽器
        4. 將 headers 轉成 Streamlink 所需的 --http-header 格式
        5. 呼叫 Streamlink，下載並合併成 out_file (ts)
        """

        async def _grab_m3u8_and_headers():
            # 1. 啟動 Playwright
            await self.init_browser()
            page: Page = self.page

            # 2. 前往影片頁面
            await page.goto(url, wait_until="load")

            # 3. 點擊「同意」按鈕 (#adult) 讓廣告開始播放
            try:
                await page.click("#adult")
            except Exception as e:
                # 如果找不到按鈕或點擊失敗，直接拋出
                await self.close_browser()
                raise RuntimeError(f"找不到或無法點擊 #adult 同意按鈕: {e}") from e

            # 4. 監聽 response：只要有 .m3u8 就抓 URL + headers
            m3u8_url = None
            m3u8_headers = None

            def _on_response(response):
                nonlocal m3u8_url, m3u8_headers
                resp_url = response.url
                # 判斷條件：URL 結尾含 .m3u8 或 URL 中間包含 .m3u8?
                if m3u8_url is None and (resp_url.endswith(".m3u8") or ".m3u8?" in resp_url):
                    m3u8_url = resp_url
                    # 讀出這次 request 的 headers
                    try:
                        req_hdrs = response.request.headers
                        m3u8_headers = dict(req_hdrs)
                    except Exception:
                        m3u8_headers = {}
            
            page.on("response", _on_response)

            # 5. 等待最多 40 秒，或一旦抓到 m3u8_url 就立即跳出
            elapsed = 0
            interval = 0.5  # 每 0.5 秒檢查一次
            while elapsed < 40:
                if m3u8_url:
                    break
                await asyncio.sleep(interval)
                elapsed += interval

            # 6. 關閉 Playwright
            await self.close_browser()

            if not m3u8_url:
                raise RuntimeError("在 40 秒內未偵測到任何 .m3u8 請求，可能廣告尚未發出或按鈕點擊失敗。")
            if not m3u8_headers:
                raise RuntimeError("擷取到 .m3u8 URL，但無法讀取對應 request 的 headers。")

            return m3u8_url, m3u8_headers

        # —— 同步部分：呼叫上面的 async func 來抓 m3u8_url、headers —— 
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            m3u8_url, headers_dict = loop.run_until_complete(_grab_m3u8_and_headers())
        except Exception as e:
            loop.close()
            print(f"[ERROR] build_method(): _grab_m3u8_and_headers() 失敗: {e}")
            return
        finally:
            if not loop.is_closed():
                loop.close()

        # 7. 把 headers_dict 轉成 Streamlink 所需的 --http-header 參數列表
        #    例如: {"User-Agent": "...", "Referer": "..."} → ["--http-header", "User-Agent=...", "--http-header", "Referer=...", ...]
        header_args = []
        for key, val in headers_dict.items():
            # 排除掉 HTTP/2 pseudo-headers (":method", ":authority" 等)
            if key.startswith(":"):
                continue
            # Streamlink 對於某些標頭（如 Cookie）要求格式：「Cookie=name=value; name2=value2」
            header_args += ["--http-header", f"{key}={val}"]

        # 8. 確保輸出資料夾存在
        folder = os.path.dirname(out_file)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder, exist_ok=True)

        # 9. 組裝 Streamlink 命令：將 m3u8_url 丟給 Streamlink 並帶上所有 header_args
        #    quality="best" 表示選 HLS 清單裡標示的最高畫質，並 "-o out_file" 直接輸出成 .ts
        cmd = ["streamlink"] + header_args + [m3u8_url, "best", "-o", out_file]

        print("[DEBUG] 執行 Streamlink 下載 HLS 並合併成 TS，命令如下：")
        print("  " + " \\\n  ".join(cmd))

        # 10. 呼叫 Streamlink，並檢查回傳值
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print("[ERROR] Streamlink stderr：")
            print(proc.stderr)
            print("[ERROR] Streamlink 執行失敗，請檢查失敗原因。")
            return

        print(f"[OK] 下載完成，已輸出成 TS：{out_file}")


    def __del__(self):
        print("[DEBUG] GenericBingeHandler.__del__()：析構方法被呼叫。")
        if self.browser:
            print("[DEBUG] __del__(): 偵測到 browser 尚未關閉，嘗試關閉...")
            try:
                asyncio.run(self.close_browser())
                print("[DEBUG] __del__(): browser 關閉完成。")
            except Exception as e:
                print(f"[WARNING] __del__(): 關閉 browser 時發生例外: {e}")
        else:
            print("[DEBUG] __del__(): browser 已經是 None。")
