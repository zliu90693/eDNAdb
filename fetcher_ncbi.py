# NCBI Entrez E-utilities 数据获取模块, 直接使用 requests, 不依赖 Biopython

import re
import time
import logging
import xml.etree.ElementTree as ET
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import (
    NCBI_API_KEY, NCBI_EMAIL, NCBI_BATCH_SIZE,
    MARKER_QUERY_MAP, SEQ_LENGTH_FILTER,
    MAX_AMBIGUOUS_RATIO, RETRY_TIMES, RETRY_DELAY
)

logger = logging.getLogger(__name__)

NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"


def _make_session() -> requests.Session:
    # 创建带重试机制的 Session
    session = requests.Session()
    retry = Retry(
        total=RETRY_TIMES,
        backoff_factor=RETRY_DELAY,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session


def _rate_limit():
    # 根据是否有 API Key 控制请求速率
    delay = 0.11 if NCBI_API_KEY else 0.34
    time.sleep(delay)


def _build_params(extra: dict) -> dict:
    # 构建基础请求参数
    params = {"email": NCBI_EMAIL}
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    params.update(extra)
    return params


# 搜索

def search_ncbi(session: requests.Session, species: str,
                marker: str, retmax: int = 500) -> list[str]:
    # 搜索 NCBI nucleotide 数据库, 返回 GI/UID 列表。自动处理超过 retmax 的结果 (usehistory) 。
    length_range = SEQ_LENGTH_FILTER.get(marker, (200, 2000))
    marker_query = MARKER_QUERY_MAP.get(marker, f"{marker}[Gene]")

    query = (
        f'"{species}"[Organism] AND '
        f'{marker_query} AND '
        f'{length_range[0]}:{length_range[1]}[SLEN]'
    )

    params = _build_params({
        "db": "nucleotide",
        "term": query,
        "retmax": min(retmax, 10000),
        "retmode": "json",
        "usehistory": "y",
    })

    try:
        r = session.get(NCBI_BASE + "esearch.fcgi", params=params, timeout=30)
        r.raise_for_status()
        _rate_limit()
    except requests.RequestException as e:
        logger.error(f"[NCBI] 搜索失败 {species}/{marker}: {e}")
        return []

    data = r.json().get("esearchresult", {})
    count = int(data.get("count", 0))
    id_list = data.get("idlist", [])

    logger.info(f"[NCBI] {species} / {marker}: 找到 {count} 条记录, 获取前 {len(id_list)} 条")
    return id_list

# 获取序列 (GenBank XML 格式, 便于解析元数据) 

def fetch_genbank_xml(session: requests.Session, id_list: list[str]) -> list[dict]:
    # 批量获取 GenBank 记录 (XML 格式) , 解析为标准化字典列表。
    all_records = []
    total = len(id_list)

    for i in range(0, total, NCBI_BATCH_SIZE):
        batch = id_list[i:i + NCBI_BATCH_SIZE]
        params = _build_params({
            "db": "nucleotide",
            "id": ",".join(batch),
            "rettype": "gb",
            "retmode": "xml",
        })

        try:
            r = session.get(NCBI_BASE + "efetch.fcgi", params=params, timeout=60)
            r.raise_for_status()
            _rate_limit()
        except requests.RequestException as e:
            logger.warning(f"[NCBI] 批次 {i//NCBI_BATCH_SIZE+1} 获取失败: {e}")
            time.sleep(RETRY_DELAY)
            continue

        records = _parse_genbank_xml(r.text)
        all_records.extend(records)
        logger.debug(f"[NCBI] 批次 {i//NCBI_BATCH_SIZE+1}: 解析 {len(records)} 条")

    return all_records


def _parse_genbank_xml(xml_text: str) -> list[dict]:
    # 解析 GenBank XML, 提取所需字段
    records = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.error(f"[NCBI] XML 解析错误: {e}")
        return []

    for seq in root.findall(".//GBSeq"):
        rec = {
            "source": "NCBI",
            "accession": "",
            "species": "",
            "genus": "",
            "family": "",
            "order_name": "",
            "marker": "",
            "sequence": "",
            "length": 0,
            "country": "",
            "lat": None,
            "lon": None,
            "bold_bin": "",
            "description": "",
        }

        # 基本字段
        acc = seq.findtext("GBSeq_primary-accession", "")
        rec["accession"] = acc
        rec["description"] = seq.findtext("GBSeq_definition", "")
        rec["length"] = int(seq.findtext("GBSeq_length", 0) or 0)

        # 序列
        seq_text = seq.findtext("GBSeq_sequence", "")
        rec["sequence"] = seq_text.upper() if seq_text else ""

        # 物种名
        organism = seq.findtext("GBSeq_organism", "")
        rec["species"] = _normalize_species(organism)
        parts = rec["species"].split()
        rec["genus"] = parts[0] if parts else ""

        # Feature 表中提取更多信息
        for feature in seq.findall(".//GBFeature"):
            feat_key = feature.findtext("GBFeature_key", "")

            if feat_key == "source":
                for qual in feature.findall(".//GBQualifier"):
                    name = qual.findtext("GBQualifier_name", "")
                    value = qual.findtext("GBQualifier_value", "")
                    if name == "country":
                        rec["country"] = value.split(":")[0]
                    elif name == "lat_lon":
                        lat, lon = _parse_lat_lon(value)
                        rec["lat"] = lat
                        rec["lon"] = lon
                    elif name == "organism" and not rec["species"]:
                        rec["species"] = _normalize_species(value)

            elif feat_key in ("CDS", "rRNA", "misc_RNA", "gene"):
                for qual in feature.findall(".//GBQualifier"):
                    name = qual.findtext("GBQualifier_name", "")
                    value = qual.findtext("GBQualifier_value", "")
                    if name == "gene" and not rec["marker"]:
                        rec["marker"] = _normalize_marker(value)
                    elif name == "product" and not rec["marker"]:
                        rec["marker"] = _normalize_marker(value)

        # 若 feature 中未获取 marker, 从描述推断
        if not rec["marker"]:
            rec["marker"] = _infer_marker_from_description(rec["description"])

        if rec["accession"] and rec["sequence"]:
            records.append(rec)

    return records


# 辅助函数

def _normalize_species(name: str) -> str:
    # 取二名法前两个词, 去除亚种和多余注释
    name = re.sub(r"\s+(subsp\.|var\.|f\.|ssp\.).*", "", name).strip()
    parts = name.split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1]}"
    return name


def _normalize_marker(text: str) -> str:
    # 将基因名标准化
    text = text.lower()
    if any(k in text for k in ["cox1", "coi", "cytochrome c oxidase subunit 1",
                                "cytochrome oxidase subunit i"]):
        return "COI"
    if "its2" in text:
        return "ITS2"
    if "internal transcribed spacer" in text or "its" in text:
        return "ITS"
    if "rbcl" in text or "ribulose" in text:
        return "rbcL"
    if "matk" in text or "maturase" in text:
        return "matK"
    if "16s" in text:
        return "16S"
    if "18s" in text:
        return "18S"
    return text.upper()[:20]


def _infer_marker_from_description(desc: str) -> str:
    # 从序列描述推断标记基因
    return _normalize_marker(desc.lower())


def _parse_lat_lon(text: str) -> tuple[Optional[float], Optional[float]]:
    # 解析 NCBI lat_lon 格式, 例如 '25.5 N 120.3 E' 或 '25.5 S 120.3 W'
    pattern = r"([\d.]+)\s*([NS])\s+([\d.]+)\s*([EW])"
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        lat = float(m.group(1)) * (1 if m.group(2).upper() == "N" else -1)
        lon = float(m.group(3)) * (1 if m.group(4).upper() == "E" else -1)
        return lat, lon
    return None, None



# 质量过滤

def quality_filter(records: list[dict], marker: str) -> list[dict]:
    # 过滤不合格序列
    length_range = SEQ_LENGTH_FILTER.get(marker, (100, 5000))
    passed = []
    for rec in records:
        seq = rec.get("sequence", "")
        if not seq:
            continue
        length = len(seq)
        if not (length_range[0] <= length <= length_range[1]):
            continue
        n_ratio = seq.count("N") / length if length > 0 else 1
        if n_ratio > MAX_AMBIGUOUS_RATIO:
            continue
        rec["length"] = length
        passed.append(rec)
    return passed


# 主入口

def fetch_from_ncbi(species: str, marker: str,
                    retmax: int = 500) -> list[dict]:
    """
    完整流程：搜索 → 获取 → 解析 → 过滤
    返回标准化记录列表
    """
    session = _make_session()
    logger.info(f"[NCBI] 开始获取: {species} / {marker}")

    id_list = search_ncbi(session, species, marker, retmax)
    if not id_list:
        logger.info(f"[NCBI] {species} / {marker}: 无结果")
        return []

    raw_records = fetch_genbank_xml(session, id_list)
    # 补全 marker (以查询 marker 为准, 若解析到则保留解析值) 
    for rec in raw_records:
        if not rec.get("marker"):
            rec["marker"] = marker

    filtered = quality_filter(raw_records, marker)
    logger.info(
        f"[NCBI] {species} / {marker}: "
        f"获取 {len(raw_records)} 条, 过滤后 {len(filtered)} 条"
    )
    return filtered
