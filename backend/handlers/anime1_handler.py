print("[DEBUG] anime1_handler.py 已 import")
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



@register_handler(r"^https?:\/\/(?:www\.)?anime1\.me.*")
class Anime1Handler(StreamHandler):
    def __init__(self):
        super().__init__()
        print("[DEBUG] Anime1Handler.__init__(): 初始化 Handler")
        self.page = None

    async def init_browser(self):
        if not self.page:
            self.page = await BrowserManager.new_page()
            print("[DEBUG] 已開啟新 page")

    async def close_browser(self):
        if self.page:
            await self.page.close()
            self.page = None
            print("[DEBUG] 已關閉 page")

    async def get_episode_urls_async(self, category_url: str) -> list[str]:
        print(f"[DEBUG] get_episode_urls_async() called with category_url = {category_url}")
        episodes = {}
        next_page = category_url
        
        # 初始化瀏覽器
        await self.init_browser()
        try:
            while next_page:
                print(f"[DEBUG] 造訪下一頁: {next_page}")
                await self.page.goto(next_page, wait_until="load")
                print("[DEBUG] 頁面載入完成，開始擷取 .entry-title a 列表...")
                data = await self.page.eval_on_selector_all(
                    ".entry-title a",
                    """els => els.map(e => ({
                        href: e.href,
                        title: e.textContent.trim()
                    }))"""
                )
                print(f"[DEBUG] 擷取到 {len(data)} 個 <a> 標籤。")

                for item in data:
                    title = item.get("title", "")
                    href = item.get("href", "")
                    print(f"[DEBUG] 解析項目: title='{title}', href='{href}'")
                    m = re.search(r'\[(\d+)\]', title)
                    if m:
                        num = int(m[1])
                        if num not in episodes:
                            episodes[num] = href
                            print(f"[DEBUG] 新增第 {num} 集: {href}")
                        else:
                            print(f"[DEBUG] 第 {num} 集已存在，跳過。")
                    else:
                        print(f"[DEBUG] 標題 '{title}' 未找到集次，跳過。")

                # 嘗試找「上一頁」連結
                print("[DEBUG] 嘗試尋找『上一頁』按鈕...")
                nxt = await self.page.query_selector('a:has-text("上一頁")')
                if nxt:
                    href = await nxt.get_attribute("href")
                    print(f"[DEBUG] 找到上一頁連結: {href}")
                    if href:
                        next_page = href
                        continue
                    else:
                        print("[DEBUG] '上一頁' 按鈕存在但 href 為 None，結束迴圈。")
                        break
                else:
                    print("[DEBUG] 未找到 '上一頁' 按鈕，結束迴圈。")
                    break
        except Exception as e:
            print(f"[ERROR] 取得集數清單時發生例外: {e}")
            raise
        finally:
            print("[DEBUG] get_episode_urls_async() finally 區塊, 準備關閉瀏覽器...")
            await self.close_browser()

        sorted_nums = sorted(episodes.keys())
        print(f"[DEBUG] 共找到 {len(sorted_nums)} 集，集數排序: {sorted_nums}")
        result_urls = [episodes[n] for n in sorted_nums]
        print(f"[DEBUG] 回傳 URL 列表: {result_urls}")
        return result_urls

    def get_ext(self):
        return "mp4"
        
    def get_filename(self, url: str, task) -> str:
        """
        1. 根据传入的 anime1.me 页面 URL，发送 HTTP GET 获取 HTML。
        2. 用 BeautifulSoup 解析，优先抓取 <h2 class="entry-title">，再退而求其次抓 <title>。
        3. 如果都找不到，就用 URL path 的最后一段做备用名称。
        4. 将抓到的名称做文件名合法化，最后加上 .mp4。
        """
        print(f"[DEBUG] get_filename() called with url = {url}")

        try:
            # 1. 发送 HTTP GET 请求获取 HTML
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            html = resp.text
            print(f"[DEBUG] get_filename(): 成功获取页面 HTML (长度 {len(html)} 字符)")
        except Exception as e:
            print(f"[WARNING] get_filename(): 无法获取 URL {url} 的 HTML: {e}")
            # 如果请求失败，就以 URL path 生成备用文件名
            parsed = urlparse(url)
            fallback = parsed.path.strip("/").replace("/", "_") or "anime1_video"
            safe_fallback = re.sub(r'[\\\/\:\*\?\"<>\|]', "_", fallback)
            filename = f"{safe_fallback}.mp4"
            print(f"[DEBUG] get_filename(): 返回 fallback filename = {filename}")
            return filename

        # 2. 用 BeautifulSoup 解析
        soup = BeautifulSoup(html, "html.parser")

        # 3. 优先尝试抓 <h2 class="entry-title">
        title = None
        h2 = soup.find("h2", class_="entry-title")
        if h2 and h2.text:
            title = h2.text.strip()
            print(f"[DEBUG] get_filename(): 从 <h2 class='entry-title'> 获取到标题: {title}")
        else:
            # 4. 再退而求其次，尝试抓 <title> 标签
            title_tag = soup.find("title")
            if title_tag and title_tag.text:
                title = title_tag.text.strip()
                print(f"[DEBUG] get_filename(): 从 <title> 获取到文字: {title}")
            else:
                print("[WARNING] get_filename(): 未找到 <h2> 也未找到 <title>，将使用 URL path 作为名称。")

        # 5. 如果上述都没成功，就以 URL path 的最后一段做为标题
        if not title:
            parsed = urlparse(url)
            # 例如 '/25302' → '25302'
            last_segment = parsed.path.strip("/").replace("/", "_") or "anime1_video"
            title = last_segment
            print(f"[DEBUG] get_filename(): fallback 使用 URL 最后一段作为标题: {title}")

        # 6. 进行文件名合法化
        #    Windows/macOS/Linux 常见不能用的字符: \ / : * ? " < > |
        safe_title = re.sub(r'[\\\/\:\*\?\"<>\|]', "_", title)
        # 将多余的空格折成 underscore
        safe_title = re.sub(r"\s+", "_", safe_title.strip())

        filename = f"{safe_title}.mp4"
        print(f"[DEBUG] get_filename(): 最终生成 filename = {filename}")
        return filename

    def parse_urls(self, start_url: str) -> list[str]:
        print(f"[DEBUG] parse_urls() called with start_url = {start_url}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            urls = loop.run_until_complete(self.get_episode_urls_async(start_url))
            print(f"[DEBUG] parse_urls() 完成，取得 URL 數量: {len(urls)}")
            return urls
        finally:
            print("[DEBUG] parse_urls() 正在關閉 event loop。")
            loop.close()

    def get_new_url(self, urls: list[str], records: set[str]):
        print(f"[DEBUG] get_new_url() called.")
        print(f"        傳入的 urls: {urls}")
        print(f"        傳入的 records: {records}")
        new_urls = [u for u in urls if u not in records]
        print(f"[DEBUG] 比對後的 new_urls: {new_urls}")
        new_url = new_urls[0] if new_urls else None
        print(f"[DEBUG] 回傳的新 URL: {new_url}")
        return new_url
        
    async def get_video_src_async(self, episode_url: str) -> str:
        print(f"[DEBUG] get_video_src_async() called with episode_url = {episode_url}")
        await self.init_browser()
        try:
            print(f"[DEBUG] 將前往影片頁面: {episode_url}")
            await self.page.goto(episode_url, wait_until="load")
            print("[DEBUG] 頁面載入完成，準備點擊播放按鈕...")
            await self.page.click(".vjs-big-play-centered")
            print("[DEBUG] 已點擊播放按鈕，開始等待影片 <video> 元素的 src 屬性出現...")
            await self.page.wait_for_function(
                "() => !!(document.querySelector('video') && document.querySelector('video').src)"
            )
            video_src = await self.page.evaluate("() => document.querySelector('video').src")
            print(f"[DEBUG] 取得到影片 src: {video_src}")
            return video_src
        except Exception as e:
            print(f"[ERROR] 取得影片 src 時發生例外: {e}")
            raise
        finally:
            print("[DEBUG] get_video_src_async() finally 區塊, 準備關閉瀏覽器...")
            await self.close_browser()

    def get_final_url(self, episode_url: str):
        print(f"[DEBUG] get_final_url() called with episode_url = {episode_url}")
        # 若要改回異步取得，可改成呼叫 get_video_src_async
        return episode_url

    def build_cmd(self, url: str, task, out_file: str) -> list[str]:
        """不使用命令列模式"""
        print(f"[DEBUG] build_cmd() called with url={url}, task={task}, out_file={out_file}")
        return None

    def build_method(self, url: str, task, out_file: str):
        """
        這個版本示範直接點按播放器上的「下載按鈕」，然後用 Playwright 自帶的 download 事件
        把影片存到 out_file。所有關鍵點都加上 print，方便觀察執行情況。
        """

        print(f"[DEBUG] build_method() called with url={url}, task={task}, out_file={out_file}")

        async def _get_video_info_and_cookies():
            print("[DEBUG] _download_via_player_button() 開始執行。")

            # 1. 啟動瀏覽器
            print("[DEBUG] 呼叫 init_browser() ...")
            await self.init_browser()
            page: Page = self.page
            print("[DEBUG] init_browser() 完成。")

            # 2. 導航到影片頁面
            print(f"[DEBUG] page.goto({url})")
            await page.goto(url, wait_until="load")
            print("[DEBUG] 頁面載入完成。")

            # 3. 點擊播放按鈕，讓 <video> 元素產生並載入 src
            try:
                print("[DEBUG] 嘗試點擊播放按鈕 (.vjs-big-play-centered) ...")
                await page.click(".vjs-big-play-centered")
                print("[DEBUG] 播放按鈕已點擊。")
            except Exception as e:
                print(f"[ERROR] 點擊播放按鈕失敗: {e}")
                await self.close_browser()
                raise RuntimeError("無法點擊播放按鈕，無法載入 <video> 元素") from e

            # 3. 等待 <video> 出現並且有 src 屬性
            try:
                print("[DEBUG] 等待 <video> 並且它有 src 屬性 (timeout=10秒)...")
                await page.wait_for_selector("video[src]", timeout=10000)
                print("[DEBUG] <video> 已經出現且具有 src 屬性。")
            except Exception as e:
                print(f"[ERROR] 等待 video[src] 失敗: {e}")
                await self.close_browser()
                raise RuntimeError("等待 video[src] 逾時或失敗") from e

            # 4. 確認 video.src 可以被讀到
            try:
                actual_mp4_url = await page.evaluate(
                    """() => {
                        const vid = document.querySelector("video");
                        return vid && vid.src ? vid.src : "";
                    }"""
                )
                print(f"[DEBUG] 從 DOM 取得 video.src = '{actual_mp4_url}'")
            except Exception as e:
                print(f"[ERROR] page.evaluate() 讀 video.src 失敗: {e}")
                await self.close_browser()
                raise

            if not actual_mp4_url:
                print("[ERROR] video.src 讀到的是空字串，代表影片尚未就緒。")
                await self.close_browser()
                raise RuntimeError("實際影片 URL 為空")

           # 6. 補全協議相對 URL（如果有需要）
            if actual_mp4_url.startswith("//"):
                print("[DEBUG] actual_mp4_url 以 '//' 開頭，補全為 https 協議。")
                actual_mp4_url = "https:" + actual_mp4_url
            elif actual_mp4_url.startswith("/"):
                print("[DEBUG] actual_mp4_url 以 '/' 開頭，使用 window.location.origin 補全相對路徑。")
                try:
                    origin = await page.evaluate("() => window.location.origin")
                    actual_mp4_url = origin + actual_mp4_url
                    print(f"[DEBUG] 補全後的 URL = {actual_mp4_url}")
                except Exception as e:
                    print(f"[ERROR] 取得 window.location.origin 時失敗: {e}")
                    await self.close_browser()
                    raise

            # 2. 導航到影片頁面
            print(f"[DEBUG] page.goto({actual_mp4_url})")
            await page.goto(actual_mp4_url, wait_until="load")
            print("[DEBUG] 頁面載入完成。")

            # 5. 從 BrowserContext 抓出該 video_url 對應的所有 cookie
            parsed = urlparse(actual_mp4_url)
            video_domain = f"{parsed.scheme}://{parsed.netloc}"
            try:
                # domain 必須與 video_url 相同（或更高層級）
                cookies = await self.page.context.cookies(actual_mp4_url)
                # cookies 會是 list of dict{"name", "value", "domain", …}
                cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
                print(f"[DEBUG] 取得 {len(cookies)} 個 cookies: {cookie_header}")
            except Exception as e:
                print(f"[WARNING] 無法取得 cookies: {e}")
                cookie_header = ""

            # 6. 讀取 User-Agent 及 Referer
            try:
                user_agent = await page.evaluate("() => navigator.userAgent")
                referer = page.url  # 頁面 URL 通常就是 referer
                print(f"[DEBUG] user_agent = '{user_agent}'")
                print(f"[DEBUG] referer = '{referer}'")
            except Exception as e:
                print(f"[WARNING] 無法取得 User-Agent 或 Referer: {e}")
                user_agent = ""
                referer = ""

            # # 7. 關閉 Playwright
            # print("[DEBUG] 關閉 Playwright context…")
            # await browser.close()
            # await playwright.stop()
            # print("[DEBUG] Playwright 已關閉。")

            return actual_mp4_url, user_agent, referer, cookie_header

        # —— 同步部分：呼叫上面的 async func 得到 video_url + headers —— 
        print("[DEBUG] build_method(): 啟動 event loop 取得 video_url + headers …")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            video_url, ua, ref, cookie_str = loop.run_until_complete(_get_video_info_and_cookies())
            print(f"[DEBUG] 拿到 video_url = '{video_url}'")
        except Exception as e:
            print(f"[ERROR] build_method(): _get_video_info_and_cookies() 拋出異常: {e}")
            loop.close()
            print("[DEBUG] build_method(): event loop 已關閉。")
            return
        finally:
            if not loop.is_closed():
                loop.close()
            print("[DEBUG] build_method(): event loop 已關閉。")

        # 8. 用 requests 一次性下載 MP4，帶上完整 Cookie/UA/Referer
        print(f"[DEBUG] Python: 開始用 requests 下載 MP4 → '{out_file}'")
        headers = {}
        if ua:
            headers["User-Agent"] = ua
        if ref:
            headers["Referer"] = ref
        if cookie_str:
            headers["Cookie"] = cookie_str
        # 你也可酌情加上 Accept、Accept-Language、Accept-Encoding 等
        headers.setdefault("Accept", "video/mp4,*/*")
        headers.setdefault("Accept-Language", "zh-TW,zh;q=0.9")

        print(f"[DEBUG] 將發送以下 Header 給 requests: {headers}")

        try:
            resp = requests.get(video_url, headers=headers, timeout=60, stream=True)
        except Exception as e:
            print(f"[ERROR] requests.get() 發生例外: {e}")
            return

        status = resp.status_code
        print(f"[DEBUG] requests.get() 返回狀態碼: {status}")
        if status != 200:
            print(f"[ERROR] 目標伺服器回 {status}，下載失敗！")
            return

        # 9. 逐塊寫入讓你能看到進度
        try:
            Path(os.path.dirname(out_file)).mkdir(parents=True, exist_ok=True)
            total_written = 0
            with open(out_file, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):  # 每次 1MB
                    if chunk:
                        f.write(chunk)
                        total_written += len(chunk)
                        print(f"[DEBUG] 已下載 {total_written} bytes …")
            final_size = os.path.getsize(out_file)
            print(f"[DEBUG] 寫檔完成，本地檔案大小: {final_size} bytes")
        except Exception as e:
            print(f"[ERROR] 寫入本地檔案時發生例外: {e}")
            return

        # 10. 印出最終結果
        filename = os.path.basename(out_file)
        print(f"+ 已下載並儲存：{filename}（{final_size/1024/1024:.2f} MB）")
        print(f"  來源 URL：{video_url}")

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
