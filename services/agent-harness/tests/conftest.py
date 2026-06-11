import os
import sys
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

# 测试进程默认固定为 mock runtime，避免读取仓库 .env 后误连真实模型服务。
os.environ["APP_ENV"] = "test"
os.environ["MOCK_MODEL_ENABLED"] = "true"
os.environ.setdefault("MIMO_API_KEY", "test-key")
os.environ.setdefault("KNOWLEDGE_STORE_BACKEND", "memory")
os.environ.setdefault("DOCUMENT_INGESTION_ENABLED", "false")
os.environ.setdefault("TRACE_PERSISTENCE_ENABLED", "false")
