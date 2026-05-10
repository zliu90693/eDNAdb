"""
config.py - 全局配置文件
修改此文件以适配你的项目需求
"""

# ─── NCBI 配置 ────────────────────────────────────────────────
# 强烈建议注册 NCBI API Key（免费）：
# https://www.ncbi.nlm.nih.gov/account/
NCBI_API_KEY = ""           # 留空则限速 3 req/s；填入后提升至 10 req/s
NCBI_EMAIL = "your@email.com"   # NCBI 要求提供联系邮箱

# ─── 目标条形码标记 ────────────────────────────────────────────
# 可选: COI, ITS, ITS2, rbcL, matK, 16S, 18S
TARGET_MARKERS = ["COI"]

# 每个标记对应的 NCBI Gene 查询词（支持同义词）
MARKER_QUERY_MAP = {
    "COI":  '(COI[Gene] OR COX1[Gene] OR "cytochrome oxidase subunit 1"[Title] OR "cytochrome c oxidase subunit I"[Title])',
    "ITS":  '("internal transcribed spacer"[Title] OR ITS1[Gene] OR ITS2[Gene])',
    "ITS2": '(ITS2[Gene] OR "internal transcribed spacer 2"[Title])',
    "rbcL": '(rbcL[Gene] OR "ribulose bisphosphate carboxylase"[Title])',
    "matK": '(matK[Gene] OR "maturase K"[Title])',
    "16S":  '(16S[Gene] OR "16S ribosomal"[Title])',
    "18S":  '(18S[Gene] OR "18S ribosomal"[Title])',
}

# ─── 序列质量过滤 ──────────────────────────────────────────────
SEQ_LENGTH_FILTER = {
    "COI":  (300, 900),
    "ITS":  (200, 800),
    "ITS2": (200, 500),
    "rbcL": (400, 800),
    "matK": (400, 900),
    "16S":  (200, 1600),
    "18S":  (500, 2000),
}
MAX_AMBIGUOUS_RATIO = 0.05  # 序列中模糊碱基（N）比例上限

# ─── 请求配置 ──────────────────────────────────────────────────
NCBI_BATCH_SIZE = 100       # 每次 efetch 的记录数
BOLD_TIMEOUT = 90           # BOLD 请求超时（秒）
RETRY_TIMES = 3             # 失败重试次数
RETRY_DELAY = 5             # 重试等待（秒）

# ─── 输出配置 ──────────────────────────────────────────────────
DB_PATH = "barcode_db.sqlite"       # SQLite 数据库路径
FASTA_OUTPUT_DIR = "fasta_output"   # FASTA 导出目录
LOG_FILE = "fetch.log"              # 日志文件
