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
        to_visit = [start_url]
        visited = set()
        urls = set()
        while to_visit:
            page = to_visit.pop(0)
            if page in visited:
                continue
            visited.add(page)
            try:
                html = requests.get(page, timeout=10).text
            except Exception as e:
                write_log(None, "error", f"無法抓取 {page}: {e}")
                continue
            soup = BeautifulSoup(html, 'html.parser')
            for tag in soup.find_all(['a', 'source']):
                src = tag.get('href') or tag.get('src') or ''
                if '.m3u8' in src:
                    urls.add(urllib.parse.urljoin(page, src))
            for m in re.findall(r"['\"]([^'\"]*?\.m3u8(?:\?[^'\"]*)?)['\"]", html):
                urls.add(urllib.parse.urljoin(page, m))
            nxt = soup.find('a', string=re.compile(r'下一[页頁]'))
            if nxt and nxt.get('href'):
                nxt_url = urllib.parse.urljoin(page, nxt['href'])
                if nxt_url not in visited:
                    to_visit.append(nxt_url)
        return list(urls)

    def build_cmd(self, url: str, task, out_file: str) -> list[str]:
        # ffmpeg 複製 m3u8 流
        return ['ffmpeg', '-hide_banner', '-y', '-i', url, '-c', 'copy', out_file]