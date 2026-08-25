# # %%

# import io
# import csv
# import time
# import logging
# import re
# from typing import Optional

# import requests
# from requests.adapters import HTTPAdapter
# from urllib3.util.retry import Retry

# import sys
# from pathlib import Path
# parent_dir = Path(__file__).parent.parent
# sys.path.insert(0, str(parent_dir))
# from config import (
#     BOLD_TIMEOUT, RETRY_TIMES, RETRY_DELAY,
#     SEQ_LENGTH_FILTER, MAX_AMBIGUOUS_RATIO
# )

# # %%

# logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
# logger = logging.getLogger(__name__)

# # %%

# from urllib.parse import quote

# # %%

# BOLD_API_BASE = "https://portal.boldsystems.org/api"
# url = f"{BOLD_API_BASE}/query/preprocessor"
# query = "tax:species:Apis cerana"
# params = {"query": query}

# logger.info(f"fetching URL: {url}?query={quote(query)}")

# # %%

# response = requests.get(url, params=params, timeout=30)
# print(response.status_code) # 200

# # %%

# # 返回了什么格式?
# print(response.headers.get('content-type', ''))
# # application/json

# # %%

# if 'application/json' in response.headers.get('content-type', ''):
#     result = response.json()
#     print(result)

# # ↑ 仅能证明API正常工作, 但不返回数据, 仅验证语法
# # 调用 /query 生成 query_id

# # %%

# url = f"{BOLD_API_BASE}/query"
# extent = "minimal"
# params = {
#         "query": query,
#         "extent": extent,  # 关键参数！
#     }
# logger.info(f"请求生成token: {url}?query={quote(query)}&extent={extent}")

# response = requests.get(url, params=params, timeout=30)
# print(response.status_code)

# %%
import requests
import json
from pathlib import Path
# %%
BASE = "https://portal.boldsystems.org/api"
species = "Bos taurus"
query = f"tax:species:{species}"
# %%
# -----------------------------
# 1. 可选：先让 preprocessor 验证查询
# -----------------------------
# r = requests.get(
#     f"{BASE}/query/preprocessor",
#     params={"query": query},
#     timeout=60
# )

# r.raise_for_status()

# print("Validated query:")
# print(r.json())
# %%
# -----------------------------
# 2. 创建 query_id
# -----------------------------
r = requests.get(
    f"{BASE}/query",
    params={
        "query": query,
        "extent": "full"
    },
    timeout=60
)
# %%
r.raise_for_status()
query_info = r.json()
print(json.dumps(query_info, indent=2)[:2000])
# %%
# 提取query_id
def find_query_id(obj):
    if isinstance(obj, dict):
        if "query_id" in obj:
            return obj["query_id"]

        for value in obj.values():
            result = find_query_id(value)
            if result is not None:
                return result

    elif isinstance(obj, list):
        for value in obj:
            result = find_query_id(value)
            if result is not None:
                return result

    return None
# %%
query_id = find_query_id(query_info)
# %%
# 开始下载
download_url = (
    f"{BASE}/documents/{query_id}/download"
)
# %%
r = requests.get(
    download_url,
    params={"format": "json"},
    timeout=300
)
# %%
r.raise_for_status()
# %%
# data = r.json()
data = [json.loads(line) for line in r.text.strip().splitlines() if line.strip()]
# %%
data
# %%
marker_code = "COI-5P"
# %%
def walk_dicts(obj):
    if isinstance(obj, dict):
        yield obj

        for value in obj.values():
            yield from walk_dicts(value)

    elif isinstance(obj, list):
        for value in obj:
            yield from walk_dicts(value)
# %%
markers = set()
for record in walk_dicts(data):
    marker = record.get("marker_code")

    if marker:
        markers.add(marker)
markers
# %%
print(json.dumps(data, indent=2)[:10000])
# %%
coi_records = []

for record in walk_dicts(data):
    marker = record.get("marker_code")
    sequence = record.get("sequence")
    if marker == "COI-5P" and sequence:
        coi_records.append({
            "processid": record.get("processid", "unknown"),
            "species": record.get("species", species),
            "sequence": sequence
        })

print("COI sequences:", len(coi_records))

# %%
