import os
import re
import requests
import json
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime
from handlers.base_handler import StreamHandler, register_handler
from playwright.async_api import async_playwright, Page, BrowserContext, Download
import asyncio
import multiprocessing
from subprocess import PIPE
import time
import shutil
from pathlib import Path
from urllib.parse import urlparse


@register_handler(r"^https?:\/\/(?:www\.)?ani\.gamer\.com\.tw.*")
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

    def parse_urls(self, start_url: str) -> list[str]:
        # Streamlink 模式不預先解析
        return []

    def get_new_url(self, urls: str, records: set[str]):
        return urls[0] if urls else None

    def get_final_url(self, episode_url: str):
        return episode_url

    def build_cmd(self, url: str, task, out_file: str) -> list[str]:
        """
        这版示范：
        1. 先从传入的 URL (e.g. https://ani.gamer.com.tw/animeVideo.php?sn=43389) 中
           解析出查询参数 sn 的值 (如“43389”)。
        2. 用 Playwright 点击「同意」(id="adult")，让广告开始播放。
        3. 等待最多 40 秒，监听所有响应，只捕获同时满足：
           - URL 中包含 “.m3u8”
           - URL 中包含解析到的 sn 值 (e.g. “43389”)
           并将那次请求的 headers 读出。
        4. 关闭浏览器。
        5. 将 headers 转成 Streamlink 要求的 `--http-header Key=Value` 格式。
        6. 调用 Streamlink，下载并合并为 `out_file` (.ts)。
        """

        async def _grab_m3u8_and_headers():
            print("[DEBUG] _grab_m3u8_and_headers(): 开始执行。")

            # --- 1. 从传入 URL 解析出 sn 值 ---
            print(f"[DEBUG] _grab_m3u8_and_headers(): 传入的影片页面 URL = {url}")
            parsed_page = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed_page.query)
            sn_values = qs.get("sn", [])
            if not sn_values:
                await self.close_browser()
                raise RuntimeError("[ERROR] _grab_m3u8_and_headers(): 无法从 URL 中解析出 sn 参数，请确认 URL 格式。")
            sn = sn_values[0]
            print(f"[DEBUG] _grab_m3u8_and_headers(): 解析到 sn = {sn}")

            # --- 2. 启动 Playwright 并打开页面 ---
            print("[DEBUG] _grab_m3u8_and_headers(): 调用 init_browser() 启动 Playwright ...")
            await self.init_browser()
            page: Page = self.page
            print("[DEBUG] _grab_m3u8_and_headers(): Playwright 启动完成。")

            print(f"[DEBUG] _grab_m3u8_and_headers(): 导航到影片页面：{url}")
            await page.goto(url, wait_until="load")
            print("[DEBUG] _grab_m3u8_and_headers(): 页面加载完成。")

            # --- 3. 点击「同意」按钮 (#adult) 让广告开始播放 ---
            try:
                print("[DEBUG] _grab_m3u8_and_headers(): 尝试点击同意按钮 (#adult) ...")
                await page.click("#adult")
                print("[DEBUG] _grab_m3u8_and_headers(): 同意按钮已点击。")
            except Exception as e:
                print(f"[ERROR] _grab_m3u8_and_headers(): 点击 #adult 同意按钮失败: {e}")
                await self.close_browser()
                raise RuntimeError(f"找不到或无法点击 #adult 同意按钮: {e}") from e

            # --- 4. 监听页面所有 response，只捕获同时含 .m3u8 且包含 sn 的 URL ---
            m3u8_url = None
            m3u8_headers = None

            def _on_response(response):
                nonlocal m3u8_url, m3u8_headers
                resp_url = response.url
                # 每个 response 都打印出来，便于调试
                print(f"[DEBUG] _on_response(): 收到 response URL = {resp_url}")

                # 判断条件：URL 中包含 ".m3u8" 且包含 sn
                if m3u8_url is None and (".m3u8" in resp_url) and (sn in resp_url):
                    m3u8_url = resp_url
                    print(f"[DEBUG] _on_response(): 匹配到目标 .m3u8 (包含 sn={sn})，m3u8_url = {m3u8_url}")
                    # 读取此次 request 的 headers
                    try:
                        req_hdrs = response.request.headers
                        m3u8_headers = dict(req_hdrs)
                        print(f"[DEBUG] _on_response(): 读取到 headers_dict = {m3u8_headers}")
                    except Exception as e:
                        print(f"[WARNING] _on_response(): 读取 request.headers 失败: {e}")
                        m3u8_headers = {}

            page.on("response", _on_response)
            print("[DEBUG] _grab_m3u8_and_headers(): 已设置 response 监听器。")

            # --- 5. 等待最多 40 秒，或一旦捕获到 m3u8_url 就立即跳出 ---
            print("[DEBUG] _grab_m3u8_and_headers(): 开始等待最多 40 秒来捕获 .m3u8 请求 ...")
            elapsed = 0.0
            interval = 0.5  # 每 0.5 秒检查一次
            while elapsed < 40.0:
                if m3u8_url:
                    print(f"[DEBUG] _grab_m3u8_and_headers(): 成功在 {elapsed:.1f} 秒内捕获到目标 .m3u8")
                    break
                await asyncio.sleep(interval)
                elapsed += interval
            else:
                print(f"[WARNING] _grab_m3u8_and_headers(): 已等待 40 秒，仍未捕获到包含 sn={sn} 的 .m3u8")

            # --- 6. 关闭 Playwright 浏览器 ---
            print("[DEBUG] _grab_m3u8_and_headers(): 开始关闭 Playwright 浏览器 ...")
            await self.close_browser()
            print("[DEBUG] _grab_m3u8_and_headers(): Playwright 已关闭。")

            # --- 7. 检查结果 ---
            if not m3u8_url:
                raise RuntimeError("在 40 秒内未检测到任何包含 sn 参数的 .m3u8 请求，可能广告未发出或按钮点击失败。")
            if not m3u8_headers:
                raise RuntimeError("捕获到 .m3u8 URL，但无法读取对应 request 的 headers。")

            print(f"[DEBUG] _grab_m3u8_and_headers(): 返回 m3u8_url = {m3u8_url}")
            print(f"[DEBUG] _grab_m3u8_and_headers(): 返回 headers_dict = {m3u8_headers}")
            return m3u8_url, m3u8_headers

        # ——— 同步部分：调用上面的 async func 捕获 m3u8_url 和 headers ———
        print("[DEBUG] build_method(): 启动新的 event loop 来执行 _grab_m3u8_and_headers() ...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            m3u8_url, headers_dict = loop.run_until_complete(_grab_m3u8_and_headers())
            print("[DEBUG] build_method(): _grab_m3u8_and_headers() 返回成功。")
        except Exception as e:
            print(f"[ERROR] build_method(): _grab_m3u8_and_headers() 抛出异常: {e}")
            loop.close()
            print("[DEBUG] build_method(): event loop 已关闭。")
            return
        finally:
            if not loop.is_closed():
                loop.close()
            print("[DEBUG] build_method(): event loop 已关闭。")

        # --- 8. 将 headers_dict 转成 Streamlink 所需的 --http-header 参数列表 ---
        print("[DEBUG] build_method(): 开始将 headers_dict 转成 header_args ...")
        header_args = []
        for key, val in headers_dict.items():
            print(f"[DEBUG] build_method(): 处理 header — Key: {key}, Value: {val}")
            # 排除掉 HTTP/2 伪标头（":method", ":authority" 等）
            if key.startswith(":"):
                print(f"[DEBUG] build_method(): 跳过 pseudo-header: {key}")
                continue
            kv = f"{key}={val}"
            header_args += ["--http-header", kv]
            print(f"[DEBUG] build_method(): 加入 header_args => '--http-header {kv}'")
        print(f"[DEBUG] build_method(): 最终 header_args 列表 = {header_args}")

        # --- 10. 组装 Streamlink 命令 ---
        cmd = ["streamlink"] + header_args + [m3u8_url, "best", "-o", out_file]
        print(f"[DEBUG] build_method(): 组装的 Streamlink 命令 = {cmd}")
        return cmd



    def build_method(self, url: str, task, out_file: str):
        return None


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