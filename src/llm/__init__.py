"""大模型 API 层（OpenAI 兼容，公网/私有化可配置）。"""

from llm.config import LlmConfig, load_llm_config
from llm.review import enrich_report_with_llm

__all__ = [
    "LlmConfig",
    "load_llm_config",
    "enrich_report_with_llm",
]
