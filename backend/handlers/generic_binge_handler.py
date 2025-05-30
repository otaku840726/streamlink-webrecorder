import os
import re
import requests
import json
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime
from handlers.base_handler import StreamHandler

class GenericBingeHandler(StreamHandler):
    def parse_urls(self, start_url: str) -> list[str]:
        print(f"[DEBUG] parse_urls start with: {start_url}")
        to_visit = [start_url]
        visited = set()
        urls = set()

        while to_visit:
            page = to_visit.pop(0)
            print(f"[DEBUG] Visiting page: {page}")
            if page in visited:
                print(f"[DEBUG] Already visited: {page}")
                continue
            visited.add(page)

            try:
                resp = requests.get(page, timeout=10)
                resp.raise_for_status()
                html = resp.text
                print(f"[DEBUG] Fetched {len(html)} bytes from {page}")
            except Exception as e:
                print(f"[DEBUG][ERROR] 無法抓取 {page}: {e}")
                write_log(None, "error", f"無法抓取 {page}: {e}")
                continue

            soup = BeautifulSoup(html, 'html.parser')
            # 找 <a> / <source>
            for tag in soup.find_all(['a', 'source']):
                src = tag.get('href') or tag.get('src') or ''
                full = urllib.parse.urljoin(page, src)
                if '.m3u8' in src:
                    print(f"[DEBUG] Found m3u8 in tag: {full}")
                    urls.add(full)

            # 找內嵌 JS 文字
            for m in re.findall(r"['\"]([^'\"]*?\.m3u8(?:\?[^'\"]*)?)['\"]", html):
                full = urllib.parse.urljoin(page, m)
                print(f"[DEBUG] Found m3u8 in JS/text: {full}")
                urls.add(full)

            # 下一頁
            nxt = soup.find('a', string=re.compile(r'下一[页頁]'))
            if nxt and nxt.get('href'):
                nxt_url = urllib.parse.urljoin(page, nxt['href'])
                print(f"[DEBUG] Next page link: {nxt_url}")
                if nxt_url not in visited:
                    to_visit.append(nxt_url)

        final = list(urls)
        print(f"[DEBUG] parse_urls returning {len(final)} URLs: {final}")
        return final

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
