# BOLD Systems 数据获取模块
# 使用 BOLD Public API v4, 无需注册账号

import io
import csv
import time
import logging
import re
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import (
    BOLD_TIMEOUT, RETRY_TIMES, RETRY_DELAY,
    SEQ_LENGTH_FILTER, MAX_AMBIGUOUS_RATIO
)

logger = logging.getLogger(__name__)
 
BOLD_API = "https://www.boldsystems.org/index.php/API_Public" # ??? 是这个吗? 为什么用的时候出错了

# BOLD marker 名称映射 (BOLD内部名称 → 标准名称) 
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

# BOLD marker 查询名称
BOLD_MARKER_QUERY = {
    "COI":  "COI-5P",
    "ITS":  "ITS",
    "ITS2": "ITS2",
    "rbcL": "RBCL",
    "matK": "MATK",
    "16S":  "16S",
    "18S":  "18S",
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

# 核心请求

def _fetch_bold_tsv(session: requests.Session,
                    taxon: str, marker_query: str) -> str:
    # 请求 BOLD combined API, 返回 TSV 文本。
    # combined 端点同时返回序列和标本元数据。
    params = {
        "taxon":  taxon,
        "marker": marker_query,
        "format": "tsv",
    }
    url = f"{BOLD_API}/combined"

    try:
        r = session.get(url, params=params, timeout=BOLD_TIMEOUT)
        r.raise_for_status()
        return r.text
    except requests.exceptions.Timeout:
        logger.warning(f"[BOLD] 请求超时: {taxon} / {marker_query}")
        return ""
    except requests.exceptions.HTTPError as e:
        logger.warning(f"[BOLD] HTTP 错误 {e.response.status_code}: {taxon}")
        return ""
    except requests.RequestException as e:
        logger.error(f"[BOLD] 请求异常: {e}")
        return ""


def _fetch_bold_sequence_fasta(session: requests.Session, taxon: str) -> str:
    # 备用：仅获取序列 FASTA (当 combined 失败时) 
    params = {"taxon": taxon, "format": "fasta"}
    url = f"{BOLD_API}/sequence"
    try:
        r = session.get(url, params=params, timeout=BOLD_TIMEOUT)
        r.raise_for_status()
        return r.text
    except requests.RequestException as e:
        logger.error(f"[BOLD] FASTA 备用请求失败: {e}")
        return ""
# 解析

def _parse_bold_tsv(tsv_text: str, target_species: str,
                    target_marker: str) -> list[dict]:
    """
    解析 BOLD TSV 响应。
    BOLD TSV 列众多 (约80列) , 仅提取关键字段。
    同时按 species 和 marker 过滤。
    """
    if not tsv_text or len(tsv_text.strip()) < 10:
        return []

    records = []
    reader = csv.DictReader(io.StringIO(tsv_text), delimiter="\t")

    # 兼容 BOLD 不同版本的列名变化
    FIELD_ALIASES = {
        "species":      ["species_name", "species", "identification"],
        "genus":        ["genus_name", "genus"],
        "family":       ["family_name", "family"],
        "order":        ["order_name", "order"],
        "sequence":     ["nucleotides", "sequence"],
        "marker":       ["markercode", "marker_code", "marker"],
        "accession":    ["processid", "process_id", "sampleid"],
        "country":      ["country", "collection_country"],
        "lat":          ["lat", "coord_lat"],
        "lon":          ["lon", "coord_lon"],
        "bold_bin":     ["bin_uri", "bin"],
    }

    def get_field(row, key):
        for alias in FIELD_ALIASES.get(key, [key]):
            if alias in row:
                return row[alias]
        return ""

    for row in reader:
        species = get_field(row, "species").strip()
        marker_raw = get_field(row, "marker").strip().upper()
        sequence = get_field(row, "sequence").strip().upper()

        # 物种过滤：允许模糊匹配 (eg. 查询属名时) 
        if target_species and not _species_match(species, target_species):
            continue

        # Marker 过滤
        std_marker = BOLD_MARKER_MAP.get(marker_raw, marker_raw)
        if target_marker and std_marker != target_marker:
            continue

        if not sequence:
            continue

        # 解析经纬度
        try:
            lat = float(get_field(row, "lat")) if get_field(row, "lat") else None
        except ValueError:
            lat = None
        try:
            lon = float(get_field(row, "lon")) if get_field(row, "lon") else None
        except ValueError:
            lon = None

        accession = get_field(row, "accession") or ""
        # BOLD processid 唯一, 加前缀区分来源
        if accession and not accession.startswith("BOLD:"):
            accession = f"BOLD:{accession}"

        genus = get_field(row, "genus") or (species.split()[0] if species else "")

        rec = {
            "source":      "BOLD",
            "accession":   accession,
            "species":     _normalize_species(species),
            "genus":       genus,
            "family":      get_field(row, "family"),
            "order_name":  get_field(row, "order"),
            "marker":      std_marker or target_marker,
            "sequence":    re.sub(r"[^ACGTRYSWKMBDHVN-]", "", sequence),
            "length":      len(sequence),
            "country":     get_field(row, "country"),
            "lat":         lat,
            "lon":         lon,
            "bold_bin":    get_field(row, "bold_bin"),
            "description": f"{species} {std_marker} [BOLD]",
        }

        if rec["accession"]:
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
    完整流程：请求 BOLD → 解析 TSV → 过滤
    支持物种名或属名查询。
    """
    session = _make_session()
    marker_query = BOLD_MARKER_QUERY.get(marker, marker)

    logger.info(f"[BOLD] 开始获取: {species} / {marker} (query marker: {marker_query})")

    tsv = _fetch_bold_tsv(session, species, marker_query)

    if not tsv:
        logger.warning(f"[BOLD] {species} / {marker}: 无响应, 尝试仅用物种名重试")
        time.sleep(RETRY_DELAY)
        tsv = _fetch_bold_tsv(session, species, "")  # 不限 marker 重试

    raw_records = _parse_bold_tsv(tsv, species, marker)

    filtered = quality_filter(raw_records, marker)
    logger.info(
        f"[BOLD] {species} / {marker}: "
        f"解析 {len(raw_records)} 条, 过滤后 {len(filtered)} 条"
    )
    return filtered
