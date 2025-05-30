import os
from datetime import datetime
from handlers.base_handler import StreamHandler

class StreamlinkHandler(StreamHandler):
    def parse_urls(self, start_url: str) -> list[str]:
        # Streamlink 模式不預先解析
        return []

    def build_cmd(self, url: str, task, out_file: str) -> list[str]:
        # 直接使用 streamlink
        return [
            'streamlink',
            *(task.params.split() if task.params else []),
            task.url,
            'best',
            '-o', out_file
        ]