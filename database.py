"""
database.py - 本地 SQLite 数据库管理
负责建表、插入、查询、去重和导出
"""

import sqlite3
import os
import logging
from datetime import datetime
from config import DB_PATH

logger = logging.getLogger(__name__)


def get_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 支持按列名访问
    return conn


def init_db():
    """初始化数据库，建表（幂等操作）"""
    conn = get_connection()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS barcodes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            accession    TEXT    UNIQUE NOT NULL,
            source       TEXT    NOT NULL,    -- 'NCBI' 或 'BOLD'
            species      TEXT,
            genus        TEXT,
            family       TEXT,
            order_name   TEXT,
            marker       TEXT,
            sequence     TEXT,
            length       INTEGER,
            country      TEXT,
            lat          REAL,
            lon          REAL,
            bold_bin     TEXT,               -- BOLD BIN URI
            description  TEXT,               -- 原始标题/描述
            retrieved_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_species ON barcodes(species);
        CREATE INDEX IF NOT EXISTS idx_genus   ON barcodes(genus);
        CREATE INDEX IF NOT EXISTS idx_marker  ON barcodes(marker);
        CREATE INDEX IF NOT EXISTS idx_source  ON barcodes(source);

        CREATE TABLE IF NOT EXISTS fetch_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            species     TEXT,
            source      TEXT,
            marker      TEXT,
            status      TEXT,    -- 'success' / 'empty' / 'error'
            count       INTEGER DEFAULT 0,
            message     TEXT,
            fetched_at  TEXT
        );
    """)
    conn.commit()
    conn.close()
    logger.info(f"数据库已初始化：{DB_PATH}")


def insert_records(records: list[dict]) -> tuple[int, int]:
    """
    批量插入记录，自动跳过重复 accession。
    返回 (插入数, 跳过数)
    """
    if not records:
        return 0, 0

    conn = get_connection()
    c = conn.cursor()
    inserted, skipped = 0, 0

    for rec in records:
        try:
            c.execute("""
                INSERT INTO barcodes
                    (accession, source, species, genus, family, order_name,
                     marker, sequence, length, country, lat, lon,
                     bold_bin, description, retrieved_at)
                VALUES
                    (:accession, :source, :species, :genus, :family, :order_name,
                     :marker, :sequence, :length, :country, :lat, :lon,
                     :bold_bin, :description, :retrieved_at)
            """, {
                "accession":   rec.get("accession", ""),
                "source":      rec.get("source", ""),
                "species":     rec.get("species", ""),
                "genus":       rec.get("genus", ""),
                "family":      rec.get("family", ""),
                "order_name":  rec.get("order_name", ""),
                "marker":      rec.get("marker", ""),
                "sequence":    rec.get("sequence", ""),
                "length":      rec.get("length", 0),
                "country":     rec.get("country", ""),
                "lat":         rec.get("lat"),
                "lon":         rec.get("lon"),
                "bold_bin":    rec.get("bold_bin", ""),
                "description": rec.get("description", ""),
                "retrieved_at": datetime.now().isoformat(),
            })
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1  # accession 重复，跳过

    conn.commit()
    conn.close()
    return inserted, skipped


def log_fetch(species: str, source: str, marker: str,
              status: str, count: int = 0, message: str = ""):
    """记录每次抓取的状态"""
    conn = get_connection()
    conn.execute("""
        INSERT INTO fetch_log (species, source, marker, status, count, message, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (species, source, marker, status, count, message, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_stats() -> dict:
    """获取数据库统计信息"""
    conn = get_connection()
    c = conn.cursor()

    stats = {}
    stats["total"] = c.execute("SELECT COUNT(*) FROM barcodes").fetchone()[0]
    stats["ncbi_count"] = c.execute(
        "SELECT COUNT(*) FROM barcodes WHERE source='NCBI'").fetchone()[0]
    stats["bold_count"] = c.execute(
        "SELECT COUNT(*) FROM barcodes WHERE source='BOLD'").fetchone()[0]
    stats["species_count"] = c.execute(
        "SELECT COUNT(DISTINCT species) FROM barcodes").fetchone()[0]

    rows = c.execute(
        "SELECT marker, COUNT(*) as cnt FROM barcodes GROUP BY marker ORDER BY cnt DESC"
    ).fetchall()
    stats["by_marker"] = {r["marker"]: r["cnt"] for r in rows}

    rows = c.execute(
        "SELECT species, COUNT(*) as cnt FROM barcodes GROUP BY species ORDER BY cnt DESC LIMIT 20"
    ).fetchall()
    stats["top_species"] = [(r["species"], r["cnt"]) for r in rows]

    conn.close()
    return stats


def export_fasta(output_dir: str, marker: str = None, species: str = None):
    """
    将数据库记录导出为 FASTA 文件。
    可按 marker 或 species 过滤。
    """
    os.makedirs(output_dir, exist_ok=True)
    conn = get_connection()
    c = conn.cursor()

    query = "SELECT * FROM barcodes WHERE sequence IS NOT NULL AND sequence != ''"
    params = []
    if marker:
        query += " AND marker = ?"
        params.append(marker)
    if species:
        query += " AND species = ?"
        params.append(species)

    rows = c.execute(query, params).fetchall()
    conn.close()

    if not rows:
        logger.warning("没有找到符合条件的序列。")
        return 0

    # 按 marker 分文件输出
    files: dict = {}
    for row in rows:
        m = row["marker"] or "unknown"
        if m not in files:
            fname = os.path.join(output_dir, f"{m}.fasta")
            files[m] = open(fname, "w", encoding="utf-8")

        header = (f">{row['accession']} "
                  f"[{row['species'] or 'unknown'}] "
                  f"[{row['marker']}] "
                  f"[{row['source']}] "
                  f"[{row['country'] or ''}]")
        files[m].write(header + "\n")
        # 每行60字符
        seq = row["sequence"].replace(" ", "").replace("\n", "")
        for i in range(0, len(seq), 60):
            files[m].write(seq[i:i+60] + "\n")

    for f in files.values():
        f.close()

    logger.info(f"已导出 {len(rows)} 条序列到 {output_dir}/")
    return len(rows)


def query_records(species: str = None, marker: str = None,
                  source: str = None, min_length: int = None) -> list:
    """灵活查询记录"""
    conn = get_connection()
    c = conn.cursor()
    query = "SELECT * FROM barcodes WHERE 1=1"
    params = []
    if species:
        query += " AND species LIKE ?"
        params.append(f"%{species}%")
    if marker:
        query += " AND marker = ?"
        params.append(marker)
    if source:
        query += " AND source = ?"
        params.append(source)
    if min_length:
        query += " AND length >= ?"
        params.append(min_length)

    rows = c.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
