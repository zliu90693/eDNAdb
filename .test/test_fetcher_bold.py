# %%

import io
import csv
import time
import logging
import re
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import sys
from pathlib import Path
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))
from config import (
    BOLD_TIMEOUT, RETRY_TIMES, RETRY_DELAY,
    SEQ_LENGTH_FILTER, MAX_AMBIGUOUS_RATIO
)

# %%

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# %%

from urllib.parse import quote

# %%

BOLD_API_BASE = "https://portal.boldsystems.org/api"
url = f"{BOLD_API_BASE}/query/preprocessor"
query = "tax:species:Apis cerana"
params = {"query": query}

logger.info(f"fetching URL: {url}?query={quote(query)}")

# %%

response = requests.get(url, params=params, timeout=30)
print(response.status_code) # 200

# %%

# 返回了什么格式?
print(response.headers.get('content-type', ''))
# application/json

# %%

if 'application/json' in response.headers.get('content-type', ''):
    result = response.json()
    print(result)

# ↑ 仅能证明API正常工作, 但不返回数据, 仅验证语法
# 调用 /query 生成 query_id

# %%

url = f"{BOLD_API_BASE}/query"
extent = "minimal"
params = {
        "query": query,
        "extent": extent,  # 关键参数！
    }
logger.info(f"请求生成token: {url}?query={quote(query)}&extent={extent}")

response = requests.get(url, params=params, timeout=30)
print(response.status_code)

# %%


