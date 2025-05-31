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
from handlers.base_handler import BrowserManager


@register_handler(r"^https?:\/\/(?:www\.)?ani\.gamer\.com\.tw.*")
class BahamutHandler(StreamHandler):
    def __init__(self):
        super().__init__()
        print("[DEBUG] BahamutHandler.__init__(): 初始化 Handler")
        self.page = None
        self.context = None

    async def init_browser(self):
        self.context = await BrowserManager.init()
        self.page = await self.context.new_page()
        print("[DEBUG] 已建立新 page")

    async def close_browser(self):
        if self.page:
            try:
                await self.page.close()
                print("[DEBUG] 已關閉 page")
            except Exception as e:
                print(f"[WARNING] page.close() 異常: {e}")
            finally:
                self.page = None

    def get_ext(self):
        return "ts"

    def get_filename(self, url: str, task) -> str:
        """
        1. 優先使用 Playwright 到页面执行 JS，等待并抓取 class="anime_name" 底下的 <h1> 文本。
           Selector: ".anime_name > h1"
        2. 如果拿不到，再退而求其次使用 <meta property="og:title"> 或 <title>。
        3. 如果两者都失败，使用 URL query 的 sn 值作为 fallback 名称。
        4. 对获取到的名称做文件名合法化，最后附上 ".mp4" 返回。
        """
        print(f"[DEBUG] get_filename() called with url = {url}")

        # 先从 URL 中解析出 sn 作为 fallback
        parsed_url = urlparse(url)
        qs = urllib.parse.parse_qs(parsed_url.query)
        sn_values = qs.get("sn", [])
        if sn_values:
            fallback_name = sn_values[0]
        else:
            fallback_name = "anime_video"
        print(f"[DEBUG] get_filename(): 解析到 sn (fallback) = {fallback_name}")

        # 异步函数：用 Playwright 抓取 .anime_name > h1 文本
        async def _fetch_dynamic_title():
            title_text = None
            print("[DEBUG] _fetch_dynamic_title(): 使用 Playwright 抓取 .anime_name > h1")

            playwright = None
            browser = None
            try:
                playwright = await async_playwright().start()
                browser = await playwright.firefox.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, wait_until="load")

                selector = ".anime_name > h1"
                print(f"[DEBUG] _fetch_dynamic_title(): 等待元素出现：{selector}")
                await page.wait_for_selector(selector, timeout=10000)
                title_text = await page.evaluate(
                    f"() => document.querySelector('{selector}').textContent.trim()"
                )
                print(f"[DEBUG] _fetch_dynamic_title(): 取得动态标题 = {title_text}")
            except Exception as e:
                print(f"[WARNING] _fetch_dynamic_title(): 无法通过 Playwright 抓取标题: {e}")
                title_text = None
            finally:
                if browser:
                    try:
                        await browser.close()
                        print("[DEBUG] _fetch_dynamic_title(): 已关闭浏览器")
                    except Exception as e:
                        print(f"[WARNING] _fetch_dynamic_title(): 关闭浏览器时异常: {e}")
                if playwright:
                    try:
                        await playwright.stop()
                        print("[DEBUG] _fetch_dynamic_title(): 已停止 Playwright")
                    except Exception as e:
                        print(f"[WARNING] _fetch_dynamic_title(): 停止 Playwright 时异常: {e}")
            return title_text

        # —— 在同步函数里调用上面的 async 来获取动态标题 —— 
        title = None
        print("[DEBUG] get_filename(): 尝试用 Playwright 获取 .anime_name > h1")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            title = loop.run_until_complete(_fetch_dynamic_title())
            print(f"[DEBUG] get_filename(): Playwright 返回 title = {title}")
        except Exception as e:
            print(f"[ERROR] get_filename(): _fetch_dynamic_title() 异常: {e}")
            title = None
        finally:
            if not loop.is_closed():
                loop.close()
            print("[DEBUG] get_filename(): Playwright 相关 event loop 已关闭。")

        # 2. 如果 playright 没拿到，再用 requests+BS 抓 <meta> 或 <title>
        if not title:
            print("[DEBUG] get_filename(): 开始用 requests+BS 抓取 <meta og:title> 或 <title>")
            try:
                resp = requests.get(url, timeout=15)
                resp.raise_for_status()
                html = resp.text
                print(f"[DEBUG] get_filename(): 获取 HTML 长度 {len(html)}")

                soup = BeautifulSoup(html, "html.parser")
                og = soup.find("meta", property="og:title")
                if og and og.get("content"):
                    title = og["content"].strip()
                    print(f"[DEBUG] get_filename(): 从 <meta og:title> 获取到标题: {title}")
                else:
                    title_tag = soup.find("title")
                    if title_tag and title_tag.text:
                        title = title_tag.text.strip()
                        print(f"[DEBUG] get_filename(): 从 <title> 获取到文字: {title}")
                    else:
                        print("[WARNING] get_filename(): 未找到 <meta og:title> 或 <title>")
                        title = None
            except Exception as e:
                print(f"[WARNING] get_filename(): 请求页面解析时异常: {e}")
                title = None

        # 3. 如果仍然没有，就使用 sn 作为标题
        if not title:
            title = fallback_name
            print(f"[DEBUG] get_filename(): 使用 fallback sn 作为标题: {title}")

        # 4. 做文件名合法化
        safe_title = re.sub(r'[\\\/\:\*\?\"<>\|]', "_", title)
        safe_title = re.sub(r"\s+", "_", safe_title.strip())
        filename = f"{safe_title}.mp4"
        print(f"[DEBUG] get_filename(): 最终生成 filename = {filename}")

        return filename


    def parse_urls(self, start_url: str) -> list[str]:
        """
        使用 Playwright 解析 Ani.Gamer 動畫頁面中「所有集數」的完整 URL 列表：
        1. 啟動 Playwright，導航到 start_url。
        2. 等待 <section class="season"> 底下的所有 <a> 元素載入完成。
        3. 讀取每個 <a> 的 href 屬性（通常形如 "?sn=XXXXX"），並將其轉成完整 URL。
        4. 關閉瀏覽器，回傳完整 URL 清單。
        """
        print(f"[DEBUG] parse_urls() called with start_url = {start_url}")

        async def _parse_urls_async():
            print("[DEBUG] _parse_urls_async(): 開始執行，啟動 Playwright...")
            await self.init_browser()
            page: Page = self.page

            try:
                print(f"[DEBUG] _parse_urls_async(): 導航到 {start_url}")
                await page.goto(start_url, wait_until="load")
                print("[DEBUG] _parse_urls_async(): 網頁載入完成。")
            except Exception as e:
                print(f"[ERROR] _parse_urls_async(): page.goto({start_url}) 失敗: {e}")
                await self.close_browser()
                return []

            # 等待 season 區塊中至少有一個 <a> 出現
            selector = "section.season a"
            try:
                print(f"[DEBUG] _parse_urls_async(): 等待 selector: '{selector}' 出現 (timeout=10s)")
                await page.wait_for_selector(selector, timeout=10000)
                print("[DEBUG] _parse_urls_async(): 已找到至少一個 <a> 元素。")
            except Exception as e:
                print(f"[WARNING] _parse_urls_async(): 等待 selector '{selector}' 超時或發生錯誤: {e}")
                # 即使等待失敗，也繼續嘗試抓取所有可能已經渲染的 <a>
            
            # 擷取所有 season 中的 <a> 元素
            try:
                anchors = await page.query_selector_all(selector)
                print(f"[DEBUG] _parse_urls_async(): 找到 {len(anchors)} 個 <a> 元素。")
            except Exception as e:
                print(f"[ERROR] _parse_urls_async(): query_selector_all 發生錯誤: {e}")
                await self.close_browser()
                return []

            urls = []
            for idx, a in enumerate(anchors):
                try:
                    href = await a.get_attribute("href")
                    if not href:
                        print(f"[WARNING] _parse_urls_async(): 第 {idx} 個 <a> 沒有 href 屬性，跳過。")
                        continue
                    href = href.strip()
                    full_url = urllib.parse.urljoin(start_url, href)
                    print(f"[DEBUG] _parse_urls_async(): 第 {idx} 個 href = '{href}', 對應 full_url = '{full_url}'")
                    urls.append(full_url)
                except Exception as e:
                    print(f"[WARNING] _parse_urls_async(): 讀取第 {idx} 個 <a> href 時出錯: {e}")
                    continue

            print(f"[DEBUG] _parse_urls_async(): 總共組出 {len(urls)} 個 URL。")
            # 關閉 Playwright
            print("[DEBUG] _parse_urls_async(): 開始關閉 Playwright 瀏覽器...")
            await self.close_browser()
            print("[DEBUG] _parse_urls_async(): Playwright 已關閉。")

            return urls

        # 同步部分：在新 event loop 裡呼叫 _parse_urls_async()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            urls = loop.run_until_complete(_parse_urls_async())
            print(f"[DEBUG] parse_urls(): _parse_urls_async() 回傳 {len(urls)} 個 URL。")
        except Exception as e:
            print(f"[ERROR] parse_urls(): 呼叫 _parse_urls_async() 發生例外: {e}")
            urls = []
        finally:
            if not loop.is_closed():
                loop.close()
            print("[DEBUG] parse_urls(): event loop 已關閉。")

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
        print("[DEBUG] Anime1Handler.__del__()：析構方法被呼叫。")
        if self.page:
            print("[DEBUG] __del__(): 偵測到 page 尚未關閉，嘗試關閉...")
            try:
                asyncio.run(self.close_browser())
                print("[DEBUG] __del__(): page 關閉完成。")
            except Exception as e:
                print(f"[WARNING] __del__(): 關閉 page 時發生例外: {e}")
        else:
            print("[DEBUG] __del__(): page 已經是 None。")
