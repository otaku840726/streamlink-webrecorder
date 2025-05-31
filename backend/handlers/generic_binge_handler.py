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

class GenericBingeHandler(StreamHandler):
    def __init__(self):
        super().__init__()
        print("[DEBUG] GenericBingeHandler.__init__(): 初始化 Handler")
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
        同步 (blocking) 版，利用遠端的 Browserless 下載影片。
        流程概述：
          1. 連到遠端 browserless (init_browser)
          2. 在 page 直接取出 <video> 或 data-src 裡的 URL，不用 click 播放 (避免播放失敗)
          3. 生成 <a download>，觸發瀏覽器下載 (在遠端 context 裡)
          4. 等待 download 事件，呼叫 download.save_as(out_file)
          5. 關閉 Playwright 控制 client (不關 browserless server)
        """
        print(f"[DEBUG] build_method() called with url={url}, task={task}, out_file={out_file}")

        async def _fetch_video_and_download():
            print("[DEBUG] _fetch_video_and_download() 開始執行。")
            # 1. 初始化遠端瀏覽器環境
            print("[DEBUG] 呼叫 init_browser() ...")
            await self.init_browser()
            page = self.page
            print("[DEBUG] init_browser() 完成，開始導航至影片頁面...")

            # 2. 直接導航到影片頁面
            print(f"[DEBUG] page.goto({url})")
            await page.goto(url, wait_until="load")
            print("[DEBUG] 頁面載入完成。")

            # 3. 嘗試從 DOM 直接抓影片 URL
            print("[DEBUG] 嘗試從 DOM 提取 actual_mp4_url...")
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
            print(f"[DEBUG] 從 DOM 取得 actual_mp4_url = '{actual_mp4_url}'")

            if not actual_mp4_url:
                error_msg = "無法從頁面 DOM 取得影片 URL，請確認 <video> 結構或自定義 JS 變數"
                print(f"[ERROR] {error_msg}")
                raise RuntimeError(error_msg)

            # 4. 補全協議相對 URL (若以 // 開頭)，或者相對路徑
            if actual_mp4_url.startswith("//"):
                print("[DEBUG] actual_mp4_url 以 '//' 開頭，補全為 https 協議。")
                actual_mp4_url = "https:" + actual_mp4_url
            elif actual_mp4_url.startswith("/"):
                print("[DEBUG] actual_mp4_url 以 '/' 開頭，使用 window.location.origin 補全相對路徑。")
                origin = await page.evaluate("() => window.location.origin")
                actual_mp4_url = origin + actual_mp4_url
            print(f"[DEBUG] 最終的 actual_mp4_url = {actual_mp4_url}")

            # 5. 註冊等待 download 事件
            print("[DEBUG] 註冊 download 事件監聽 (page.wait_for_event('download'))")
            download_task = page.wait_for_event("download")

            # 6. 動態注入一段 <a download> 的 JS，立即觸發點擊
            print("[DEBUG] 注入 <a download> 觸發下載...")
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
            print("[DEBUG] 已執行下載觸發 JS。")

            # 7. 等候瀏覽器觸發 download 事件
            print("[DEBUG] 等待 download 事件完成...")
            download: Download = await download_task
            print("[DEBUG] 已收到 Download 事件。")

            # 8. 把檔案另存到 out_file
            print(f"[DEBUG] 準備儲存下載檔案到: {out_file}")
            Path(os.path.dirname(out_file)).mkdir(parents=True, exist_ok=True)
            await download.save_as(out_file)
            print(f"[DEBUG] 下載檔案已儲存至: {out_file}")

            # 9. 關閉 Playwright 端的資料結構（不會關 browserless server）
            print("[DEBUG] _fetch_video_and_download(): 準備關閉瀏覽器。")
            await self.close_browser()
            print("[DEBUG] _fetch_video_and_download(): 瀏覽器關閉完成。")

            # 10. 回傳影片 URL + 本地檔案大小
            file_size = os.path.getsize(out_file)
            print(f"[DEBUG] 本地檔案大小: {file_size} bytes")
            return actual_mp4_url, file_size

        # —— 同步部分開始 —— 
        print("[DEBUG] build_method(): 建立並啟動新的 event loop 進行下載。")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            actual_url, size_bytes = loop.run_until_complete(_fetch_video_and_download())
            print("[DEBUG] 下載任務完成，取得 actual_url 及 size_bytes。")
        finally:
            print("[DEBUG] build_method(): 正在關閉 event loop。")
            loop.close()

        # 同步列印結果
        filename = os.path.basename(out_file)
        print(f"+ 已下載並儲存：{filename}（{size_bytes/1024/1024:.2f} MB）")
        print(f"  來源 URL：{actual_url}")

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
