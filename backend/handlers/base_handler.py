import re
from abc import ABC, abstractmethod

_registry = []

def register_handler(pattern):
    def deco(cls):
        _registry.append((re.compile(pattern), cls()))
        return cls
    return deco

class StreamHandler(ABC):
    @abstractmethod
    def parse_urls(self, start_url: str) -> list[str]:
        """解析起始 URL，返回 m3u8 連結列表"""
        pass

    @abstractmethod
    def get_new_url(self, urls: str, records: set[str]):
        pass

    @abstractmethod
    def get_final_url(self, episode_url: str):
        """
        根據選中的 episode_url 做進一步處理，取得最終要給 build_cmd 的 url
        預設直接回傳 episode_url，子類可覆寫此方法
        """
        pass     

    @abstractmethod
    def build_cmd(self, url: str, task, out_file: str) -> list[str]:
        """根據單一 m3u8 URL、任務資訊與輸出檔案路徑，返回執行命令"""
        pass


def get_handler(task) -> StreamHandler:
    # 先匹配專屬 handler
    for pattern, handler in _registry:
        if pattern.search(task.url):
            return handler
    # 依 tool 選擇預設 handler
    if task.tool == 'custom':
        from handlers.generic_binge_handler import GenericBingeHandler
        return GenericBingeHandler()
        
    from handlers.streamlink_handler import StreamlinkHandler
    return StreamlinkHandler()