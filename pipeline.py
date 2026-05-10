# 主调度pipeline, 协调 NCBI/BOLD 获取、数据库写入、日志记录

import sys
import logging
import time
from pathlib import Path
from typing import Literal

from config import TARGET_MARKERS, LOG_FILE, FASTA_OUTPUT_DIR
from database import init_db, insert_records, log_fetch, get_stats, export_fasta
from fetcher_ncbi import fetch_from_ncbi
from fetcher_bold import fetch_from_bold

# 日志配置
def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


# 物种列表读取
def load_species_list(filepath: str) -> list[str]:
    # 读取物种列表文件。格式：每行一个物种名，# 开头为注释，支持空行。
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"物种列表文件不存在: {filepath}")

    species = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                species.append(line)

    if not species:
        raise ValueError("物种列表为空，请检查文件内容。")

    logging.getLogger(__name__).info(f"读取物种列表: {len(species)} 个分类群")
    return species


# 单物种获取

def fetch_one_species(
    species: str,
    marker: str,
    source: Literal["both", "ncbi", "bold"] = "both",
    ncbi_retmax: int = 500,
) -> int:
    # 获取单个物种的单个标记数据，写入数据库。返回实际插入的记录数。
    logger = logging.getLogger(__name__)
    total_inserted = 0

    sources = []
    if source in ("both", "ncbi"):
        sources.append("ncbi")
    if source in ("both", "bold"):
        sources.append("bold")

    for src in sources:
        try:
            if src == "ncbi":
                records = fetch_from_ncbi(species, marker, retmax=ncbi_retmax)
            else:
                records = fetch_from_bold(species, marker)

            if not records:
                log_fetch(species, src.upper(), marker, "empty", 0)
                continue

            inserted, skipped = insert_records(records)
            total_inserted += inserted
            log_fetch(species, src.upper(), marker, "success", inserted,
                      f"skipped={skipped}")
            logger.info(
                f"  [{src.upper()}] {species}/{marker}: "
                f"入库 {inserted} 条，跳过重复 {skipped} 条"
            )

        except Exception as e:
            logger.error(f"  [{src.upper()}] {species}/{marker} 异常: {e}")
            log_fetch(species, src.upper(), marker, "error", 0, str(e))

        time.sleep(1)  # 两数据源之间稍作等待

    return total_inserted


# 批量运行

def run_pipeline(
    species_list: list[str],
    markers: list[str] = None,
    source: Literal["both", "ncbi", "bold"] = "both",
    ncbi_retmax: int = 500,
    verbose: bool = False,
):
    """
    主管线：对每个物种 × 每个标记，分别从指定数据源获取数据。

    Args:
        species_list: 物种/属名列表
        markers:      条形码标记列表 (默认使用 config.TARGET_MARKERS) 
        source:       数据源 'both'/'ncbi'/'bold'
        ncbi_retmax:  NCBI 每次最大返回数
        verbose:      是否输出 DEBUG 日志
    """
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    markers = markers or TARGET_MARKERS
    init_db()

    total_species = len(species_list)
    grand_total = 0

    logger.info("=" * 60)
    logger.info(f"任务开始: {total_species} 个分类群 × {len(markers)} 个标记")
    logger.info(f"数据源: {source.upper()}  |  标记: {', '.join(markers)}")
    logger.info("=" * 60)

    for idx, species in enumerate(species_list, 1):
        logger.info(f"\n[{idx}/{total_species}] 处理: {species}")
        species_total = 0

        for marker in markers:
            n = fetch_one_species(species, marker, source, ncbi_retmax)
            species_total += n

        grand_total += species_total
        logger.info(f"  → {species} 累计入库: {species_total} 条")

        # 每处理完一个物种，稍作间隔避免服务器封禁
        if idx < total_species:
            time.sleep(2)

    # ── 汇总统计 ──
    logger.info("\n" + "=" * 60)
    logger.info("任务完成，数据库统计：")
    stats = get_stats()
    logger.info(f"  总记录数:   {stats['total']}")
    logger.info(f"  NCBI 来源:  {stats['ncbi_count']}")
    logger.info(f"  BOLD 来源:  {stats['bold_count']}")
    logger.info(f"  物种数:     {stats['species_count']}")
    logger.info(f"  按标记分布: {stats['by_marker']}")
    logger.info("=" * 60)

    return grand_total


# 导出工具

def run_export(output_dir: str = None, marker: str = None, species: str = None):
    # 导出数据库内容为 FASTA 文件
    setup_logging()
    output_dir = output_dir or FASTA_OUTPUT_DIR
    count = export_fasta(output_dir, marker=marker, species=species)
    logging.getLogger(__name__).info(f"导出完成: {count} 条序列 → {output_dir}/")
    return count


# 统计工具

def print_stats():
    # 打印当前数据库统计
    setup_logging()
    stats = get_stats()
    print("\n数据库统计")
    print(f"  总记录数:  {stats['total']}")
    print(f"  NCBI 来源: {stats['ncbi_count']}")
    print(f"  BOLD 来源: {stats['bold_count']}")
    print(f"  物种数量:  {stats['species_count']}")
    print(f"\n  按标记分布:")
    for marker, cnt in stats["by_marker"].items():
        print(f"    {marker:<12} {cnt}")
    print(f"\n  记录最多的物种 (Top 20) :")
    for sp, cnt in stats["top_species"]:
        print(f"    {sp:<40} {cnt}")
