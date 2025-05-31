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
        這個版本示範直接點按播放器上的「下載按鈕」，然後用 Playwright 自帶的 download 事件
        把影片存到 out_file。所有關鍵點都加上 print，方便觀察執行情況。
        """

        print(f"[DEBUG] build_method() called with url={url}, task={task}, out_file={out_file}")

        async def _download_via_player_button():
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

            # 5. 嘗試找到「下載按鈕」的可能 selector
            #    這邊舉例用中文「下載」或英文「Download」做查詢，你可以根據實際 HTML 再微調
            download_selectors = [
                'a:has-text("下載")',        # 連結文字為「下載」
                'a:has-text("Download")',    # 連結文字為 "Download"
                'button:has-text("下載")',
                'button:has-text("Download")',
                'a[download]',               # 直接找 <a download>
                'video[controlslist] ~ a',   # 假設下載按鈕緊接在 video 之後
            ]

            button = None
            for sel in download_selectors:
                try:
                    print(f"[DEBUG] 嘗試尋找下載按鈕 selector: '{sel}'")
                    button = await page.query_selector(sel)
                    if button:
                        print(f"[DEBUG] 找到下載按鈕 ({sel})！")
                        break
                    else:
                        print(f"[DEBUG] 尚未找到: {sel}")
                except Exception as e:
                    print(f"[DEBUG] query_selector(\"{sel}\") 出現例外: {e}")

            if not button:
                print("[ERROR] 未能找到任何下載按鈕，請檢查播放器的 HTML 結構。")
                await self.close_browser()
                raise RuntimeError("找不到下載按鈕")

            # 6. 在點擊「下載按鈕」之前，註冊 download 事件
            print("[DEBUG] 註冊 page.expect_download() …")
            # 這邊使用 expect_download，能夠確保 Playwright 等到 download 開始
            try:
                async with page.expect_download() as download_info:
                    print("[DEBUG] 正在點擊下載按鈕…")
                    await button.click()
                download: Download = await download_info.value
                print("[DEBUG] 已經攔截到 Download 事件！")
            except Exception as e:
                print(f"[ERROR] 點擊下載按鈕後未收到 Download 事件: {e}")
                await self.close_browser()
                raise RuntimeError("未能攔截到下載事件 (expect_download)") from e

            # 7. Download 物件拿到之後，確認取得的下載路徑與預設檔名
            try:
                # 如果你要看伺服器給的預設檔名，可以用 download.suggested_filename()
                suggested_name = download.suggested_filename
                print(f"[DEBUG] suggested filename = {suggested_name}")

                # 如果你要知道 Playwright 把檔案先下載到哪（暫存路徑）
                temp_path = download.path()
                print(f"[DEBUG] 暫存檔案路徑 = {temp_path}")

                # 把暫存檔案另存成你指定的 out_file
                print(f"[DEBUG] 將下載檔另存到: {out_file}")
                Path(os.path.dirname(out_file)).mkdir(parents=True, exist_ok=True)
                await download.save_as(out_file)
                print(f"[DEBUG] 檔案已儲存到: {out_file}")

                # 確認檔案大小
                final_size = os.path.getsize(out_file)
                print(f"[DEBUG] 下載完成，檔案大小: {final_size} bytes")
            except Exception as e:
                print(f"[ERROR] Download.save_as() 或檔案搬移過程失敗: {e}")
                await self.close_browser()
                raise

            # 8. 所有流程結束，關閉瀏覽器
            print("[DEBUG] 所有下載流程完成，準備關閉瀏覽器。")
            await self.close_browser()
            print("[DEBUG] 瀏覽器關閉完成。")

            # 9. 回傳實際影片 URL 與檔案大小
            return actual_mp4_url, final_size

        # —— 同步部分：啟動 event loop 去執行上述 async 函式 —— 
        print("[DEBUG] build_method(): 建立並啟動 event loop 下載影片。")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            actual_url, size_bytes = loop.run_until_complete(_download_via_player_button())
            print(f"[DEBUG] 下載任務完成，actual_url = {actual_url}，size_bytes = {size_bytes}")
        except Exception as e:
            print(f"[ERROR] build_method(): _download_via_player_button() 拋出例外: {e}")
        finally:
            print("[DEBUG] build_method(): event loop 關閉。")
            loop.close()

        # 最後在同步層印出最終結果
        if 'size_bytes' in locals() and size_bytes and size_bytes > 0:
            filename = os.path.basename(out_file)
            print(f"+ 已下載並儲存：{filename}（{size_bytes/1024/1024:.2f} MB）")
            print(f"  來源 URL：{actual_url}")
        else:
            print("[DEBUG] 未下載任何檔案，請檢查上述錯誤日誌。")

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
