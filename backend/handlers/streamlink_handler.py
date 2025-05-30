import os
from datetime import datetime
from handlers.base_handler import StreamHandler

class StreamlinkHandler(StreamHandler):
    def parse_urls(self, start_url: str) -> list[str]:
        # Streamlink 模式不預先解析
        return []

    def get_new_url(self, urls: str, records: set[str]):
        return urls[0] if urls else None

    def get_final_url(self, episode_url: str):
        return episode_url

    def build_cmd(self, url: str, task, out_file: str) -> list[str]:
        # 直接使用 streamlink
        return [
            'streamlink',
            *(task.params.split() if task.params else []),
            task.url,
            'best',
            '-o', out_file
        ]