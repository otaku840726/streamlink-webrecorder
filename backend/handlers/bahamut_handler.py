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

    def get_filename(self, url: str, task) -> str:
        """
        仅用 requests 抓标题，不启用 Playwright。逻辑：
        1. 先从 URL query 解析 sn 作为 fallback 名称。
        2. 用 requests GET 页面 HTML，用 BeautifulSoup 解析：
           a. 优先尝试抓取 class="anime_name" 下的 <h1>（Selector: ".anime_name > h1"）。
           b. 如果找不到，再尝试抓 <meta property="og:title"> 的 content。
           c. 如果还没找到，就抓 <title> 标签文本。
        3. 如果以上都无法获取到标题，就用 sn 作为名称。
        4. 对获取到的名称做文件名安全化（将 \ / : * ? " < > | 等字符替换成 "_"，并以 "_" 替换连续空白）。
        5. 最后在名称末尾加上 ".mp4" 并返回。
        """
        print(f"[DEBUG] get_filename() called with url = {url}")

        # 1. 从 URL 中解析 sn 作为 fallback
        parsed_url = urlparse(url)
        qs = urllib.parse.parse_qs(parsed_url.query)
        sn_values = qs.get("sn", [])
        if sn_values:
            fallback_name = sn_values[0]
        else:
            fallback_name = "anime_video"
        print(f"[DEBUG] get_filename(): 解析到 sn (fallback) = {fallback_name}")

        title = None

        # 2. 用 requests 获取页面 HTML
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            html = resp.text
            print(f"[DEBUG] get_filename(): 成功取得 HTML (长度 {len(html)} 字符)")
        except Exception as e:
            print(f"[WARNING] get_filename(): 无法获取页面 HTML: {e}")
            # 直接使用 fallback
            safe_fallback = re.sub(r'[\\\/\:\*\?\"<>\|]', "_", fallback_name)
            filename = f"{safe_fallback}.mp4"
            print(f"[DEBUG] get_filename(): 返回 fallback filename = {filename}")
            return filename

        soup = BeautifulSoup(html, "html.parser")

        # 2.a 优先抓取 <div class="anime_name"><h1>…</h1></div>
        h1 = soup.select_one(".anime_name > h1")
        if h1 and h1.text:
            title = h1.text.strip()
            print(f"[DEBUG] get_filename(): 从 .anime_name > h1 获取到标题: {title}")
        else:
            # 2.b 再尝试 <meta property="og:title">
            og = soup.find("meta", property="og:title")
            if og and og.get("content"):
                title = og["content"].strip()
                print(f"[DEBUG] get_filename(): 从 <meta property='og:title'> 获取到标题: {title}")
            else:
                # 2.c 再尝试 <title>
                title_tag = soup.find("title")
                if title_tag and title_tag.text:
                    title = title_tag.text.strip()
                    print(f"[DEBUG] get_filename(): 从 <title> 获取到文本: {title}")
                else:
                    print("[WARNING] get_filename(): 未找到 .anime_name > h1、<meta og:title> 或 <title>，将使用 sn 作为标题。")
                    title = None

        # 3. 如果仍然没有标题，使用 sn
        if not title:
            title = fallback_name
            print(f"[DEBUG] get_filename(): 使用 fallback sn 作为标题: {title}")

        # 4. 文件名安全化：将 \ / : * ? \" < > | 全部替换成 "_"，再将连续空白替换为 "_"
        safe_title = re.sub(r'[\\\/\:\*\?\"<>\|]', "_", title)
        safe_title = re.sub(r"\s+", "_", safe_title.strip())

        # 5. 最终返回
        filename = f"{safe_title}.mp4"
        print(f"[DEBUG] get_filename(): 最终生成 filename = {filename}")
        return filename


    def parse_urls(self, start_url: str) -> list[str]:
        """
        解析 Ani.Gamer 動畫頁面中，「所有集數」的 URL。
        1. 發送 HTTP GET 取得 start_url 的 HTML。
        2. 用 BeautifulSoup 解析 <section class="season"> 中所有 <a> 標籤。
        3. 將 href（通常形如 "?sn=XXXXX"）轉成完整 URL，並依序回傳列表。
        """
        print(f"[DEBUG] parse_urls() called with start_url = {start_url}")

        try:
            resp = requests.get(start_url, timeout=15)
            resp.raise_for_status()
            html = resp.text
            print(f"[DEBUG] parse_urls(): 成功取得 HTML (長度 {len(html)} 字符)")
        except Exception as e:
            print(f"[ERROR] parse_urls(): 無法取得頁面 HTML: {e}")
            return []

        soup = BeautifulSoup(html, "html.parser")

        # 找到 <section class="season">
        season_section = soup.find("section", class_="season")
        if not season_section:
            print("[WARNING] parse_urls(): 未找到 <section class='season'>，回傳空列表。")
            return []

        # 在 season_section 底下抓所有 <a>，並建構完整 URL
        anchors = season_section.find_all("a", href=True)
        if not anchors:
            print("[WARNING] parse_urls(): <section class='season'> 中未找到任何 <a>，回傳空列表。")
            return []

        urls = []
        for a in anchors:
            href = a.get("href").strip()
            # 若 href 以 '?' 開頭 (如 "?sn=40262")，用 urljoin 加上 base
            full_url = urllib.parse.urljoin(start_url, href)
            print(f"[DEBUG] parse_urls(): 抓到 href = {href}，對應 full_url = {full_url}")
            urls.append(full_url)

        print(f"[DEBUG] parse_urls(): 最終回傳 {len(urls)} 個 URL → {urls}")
        return urls


    def get_new_url(self, urls: str, records: set[str]):
        print(f"[DEBUG] get_new_url() called.")
        print(f"        傳入的 urls: {urls}")
        print(f"        傳入的 records: {records}")
        new_urls = [u for u in urls if u not in records]
        print(f"[DEBUG] 比對後的 new_urls: {new_urls}")
        new_url = new_urls[0] if new_urls else None
        print(f"[DEBUG] 回傳的新 URL: {new_url}")
        return new_url

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