import dashscope

from config import Settings, settings


def configure_dashscope(cfg: Settings = settings) -> None:
    dashscope.api_key = cfg.dashscope_api_key
    dashscope.base_http_api_url = cfg.dashscope_base_url
