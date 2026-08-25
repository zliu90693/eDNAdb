# BOLD Systems 数据获取模块
# 使用 BOLD Portal Public API v4, 无需注册账号
#
# 请求流程 (三步):
#   1. 构造 triplet 查询词:  tax:species:<种名>  或  tax:genus:<属名>
#   2. GET /api/query?query=<triplet>&extent=full  → 得到 query_id
#   3. GET /api/documents/{query_id}/download?format=json  → 返回 JSON Lines (NDJSON)
# 注意: v4 API 查询不支持 marker 过滤, 需在解析阶段按 marker_code 客户端过滤。

import time
import logging
import re
import json

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import (
    BOLD_TIMEOUT, BOLD_DOWNLOAD_TIMEOUT, RETRY_TIMES, RETRY_DELAY,
    SEQ_LENGTH_FILTER, MAX_AMBIGUOUS_RATIO
)

logger = logging.getLogger(__name__)

BOLD_API = "https://portal.boldsystems.org/api"

# BOLD marker 名称映射 (BOLD 内部名称 → 标准名称)
BOLD_MARKER_MAP = {
    "COI-5P": "COI",
    "COI-3P": "COI",
    "COI":    "COI",
    "ITS":    "ITS",
    "ITS2":   "ITS2",
    "RBCL":   "rbcL",
    "MATK":   "matK",
    "16S":    "16S",
    "18S":    "18S",
}


def _make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=RETRY_TIMES,
        backoff_factor=RETRY_DELAY,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    # 模拟浏览器, 避免被屏蔽
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (compatible; BarcodeDBFetcher/1.0; "
            "Academic research use)"
        )
    })
    return session


# 查询词构造

def _build_query(species: str) -> str:
    # 单词视为属名, 双词视为种名
    if len(species.split()) == 1:
        return f"tax:genus:{species}"
    return f"tax:species:{species}"


# 核心请求

def _create_query_id(session: requests.Session, query: str) -> str:
    # 请求 /api/query, 返回 query_id (空串表示失败)。
    params = {"query": query, "extent": "full"}
    url = f"{BOLD_API}/query"

    try:
        r = session.get(url, params=params, timeout=BOLD_TIMEOUT)
        r.raise_for_status()
        query_id = (r.json() or {}).get("query_id", "")
        if not query_id:
            logger.warning(f"[BOLD] 查询未返回 query_id: {query}")
        return query_id
    except requests.exceptions.HTTPError as e:
        logger.warning(
            f"[BOLD] 查询 HTTP 错误 {e.response.status_code}: {query} "
            f"(响应: {e.response.text[:200]})"
        )
        return ""
    except requests.RequestException as e:
        logger.error(f"[BOLD] 查询异常: {e}")
        return ""


def _download_ndjson(session: requests.Session, query_id: str) -> str:
    # 下载文档, format=json 返回 JSON Lines (每行一条记录)。
    params = {"format": "json"}
    url = f"{BOLD_API}/documents/{query_id}/download"
    try:
        r = session.get(url, params=params, timeout=BOLD_DOWNLOAD_TIMEOUT)
        r.raise_for_status()
        return r.text
    except requests.RequestException as e:
        logger.error(f"[BOLD] 下载失败: {e}")
        return ""


# 解析

def _parse_bold_ndjson(text: str, target_species: str,
                       target_marker: str) -> list[dict]:
    """
    解析 BOLD download 返回的 JSON Lines。
    每条记录字段众多, 仅提取关键字段。
    同时按 species 和 marker 过滤。
    """
    if not text or len(text.strip()) < 10:
        return []

    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            logger.warning(f"[BOLD] 跳过无法解析的行: {line[:100]}")
            continue

        species = (row.get("species") or row.get("identification") or "").strip()

        # 物种过滤：允许模糊匹配 (eg. 查询属名时)
        if target_species and not _species_match(species, target_species):
            continue

        # Marker 过滤 (v4 API 不支持服务端 marker 过滤)
        marker_raw = (row.get("marker_code") or "").strip().upper()
        std_marker = BOLD_MARKER_MAP.get(marker_raw, marker_raw)
        if target_marker and std_marker != target_marker:
            continue

        sequence = (row.get("nuc") or "").strip().upper()
        if not sequence:
            continue

        # 解析经纬度 (coord 格式为 [lat, lon])
        coord = row.get("coord")
        if isinstance(coord, list) and len(coord) == 2:
            try:
                lat, lon = float(coord[0]), float(coord[1])
            except (TypeError, ValueError):
                lat, lon = None, None
        else:
            lat, lon = None, None

        accession = (row.get("processid") or "").strip()
        # BOLD processid 唯一, 加前缀区分来源
        if accession and not accession.startswith("BOLD:"):
            accession = f"BOLD:{accession}"
        if not accession:
            continue

        genus = (row.get("genus") or "").strip() or (species.split()[0] if species else "")

        rec = {
            "source":      "BOLD",
            "accession":   accession,
            "species":     _normalize_species(species),
            "genus":       genus,
            "family":      (row.get("family") or "").strip(),
            "order_name":  (row.get("order") or "").strip(),
            "marker":      std_marker or target_marker,
            "sequence":    re.sub(r"[^ACGTRYSWKMBDHVN-]", "", sequence),
            "length":      len(sequence),
            "country":     (row.get("country/ocean") or "").strip() or None,
            "lat":         lat,
            "lon":         lon,
            "bold_bin":    (row.get("bin_uri") or "").strip(),
            "description": f"{species} {std_marker} [BOLD]",
        }
        records.append(rec)

    return records


def _species_match(found: str, target: str) -> bool:
    # 物种名匹配, 支持属名查询时匹配所有该属物种
    found = found.lower().strip()
    target = target.lower().strip()
    target_parts = target.split()

    if len(target_parts) == 1:
        # 仅属名：匹配以该属名开头的物种
        return found.startswith(target_parts[0])
    else:
        # 种名：精确匹配前两个词
        found_parts = found.split()
        if len(found_parts) >= 2:
            return found_parts[0] == target_parts[0] and found_parts[1] == target_parts[1]
        return False


def _normalize_species(name: str) -> str:
    name = re.sub(r"\s+(subsp\.|var\.|f\.|ssp\.).*", "", name).strip()
    parts = name.split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1]}"
    return name


# 质量过滤

def quality_filter(records: list[dict], marker: str) -> list[dict]:
    length_range = SEQ_LENGTH_FILTER.get(marker, (100, 5000))
    passed = []
    for rec in records:
        seq = rec.get("sequence", "").replace("-", "")  # 去除比对间隙
        if not seq:
            continue
        length = len(seq)
        if not (length_range[0] <= length <= length_range[1]):
            continue
        n_ratio = seq.count("N") / length if length > 0 else 1
        if n_ratio > MAX_AMBIGUOUS_RATIO:
            continue
        rec["sequence"] = seq  # 存储去除间隙的序列
        rec["length"] = length
        passed.append(rec)
    return passed


# 主入口

def fetch_from_bold(species: str, marker: str) -> list[dict]:
    """
    完整流程：构造查询 → 生成 query_id → 下载 NDJSON → 解析 → 过滤
    支持物种名或属名查询。
    """
    session = _make_session()
    query = _build_query(species)

    logger.info(f"[BOLD] 开始获取: {species} / {marker} (query: {query})")

    query_id = _create_query_id(session, query)
    if not query_id:
        logger.warning(f"[BOLD] {species} / {marker}: 无法生成查询, 跳过")
        return []

    ndjson = _download_ndjson(session, query_id)

    if not ndjson:
        logger.warning(f"[BOLD] {species} / {marker}: 无响应, 稍后重试一次")
        time.sleep(RETRY_DELAY)
        ndjson = _download_ndjson(session, query_id)

    raw_records = _parse_bold_ndjson(ndjson, species, marker)

    filtered = quality_filter(raw_records, marker)
    logger.info(
        f"[BOLD] {species} / {marker}: "
        f"解析 {len(raw_records)} 条, 过滤后 {len(filtered)} 条"
    )
    return filtered
