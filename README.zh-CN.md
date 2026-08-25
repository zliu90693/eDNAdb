<div align="right">

[English](README.md) | **简体中文**

</div>

# 条形码数据库构建工具

从**NCBI GenBank**和**BOLD**批量获取物种条形码序列，构建本地SQLite数据库并导出FASTA文件。不依赖Biopython。

---

## 文件结构

```
barcode_db/
├── main.py           # 命令行入口
├── pipeline.py       # 主调度 pipeline
├── fetcher_ncbi.py   # NCBI E-utilities 获取模块
├── fetcher_bold.py   # BOLD Systems 获取模块
├── database.py       # SQLite 数据库管理
├── config.py         # 全局配置（修改此文件适配需求）
├── species.txt       # 物种列表示例
└── requirements.txt  # 依赖
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

编辑 `config.py`：

```python
NCBI_API_KEY = "your_api_key"    # 强烈建议：https://www.ncbi.nlm.nih.gov/account/
NCBI_EMAIL   = "your@email.com"  # NCBI 要求提供
TARGET_MARKERS = ["COI"]         # 目标标记基因
```

### 3. 准备物种列表

编辑 `species.txt`，每行一个物种名（支持属名批量查询）：

```
# 入侵物种
Solenopsis invicta
Solenopsis geminata
Frankliniella occidentalis

# 近缘本土物种
Solenopsis jacoti
Solenopsis fugax
Solenopsis tipuna
Frankliniella intonsa
```

---

## 使用方法

### 获取数据

```bash
# 从文件读取物种，获取 COI（NCBI + BOLD 双源）
python main.py fetch --file species.txt --markers COI

# 仅使用 NCBI，获取 COI 和 ITS
python main.py fetch --file species.txt --markers COI,ITS --source ncbi

# 命令行直接指定物种（快速测试）
python main.py fetch --species "Harmonia axyridis,Harmonia yedoensis" --markers COI

# 每物种最多获取 200 条，仅用 BOLD
python main.py fetch --file species.txt --source bold --retmax 200

# 输出详细日志
python main.py fetch --file species.txt --verbose
```

### 查看统计

```bash
python main.py stats
```

输出示例：
```
数据库统计
  总记录数:  1836
  NCBI 来源: 1836
  BOLD 来源: 0
  物种数量:  5

  按标记分布:
    COI          1835
    COXI         1

  记录最多的物种 (Top 20) :
    Frankliniella occidentalis               500
    Solenopsis geminata                      499
    Frankliniella intonsa                    488
    Solenopsis invicta                       347
    Solenopsis fugax                         2
    ...
```

### 导出 FASTA

```bash
# 导出所有序列（按标记分文件）
python main.py export --output ./my_fasta

# 仅导出 COI
python main.py export --marker COI --output ./coi_fasta

# 仅导出某物种
python main.py export --species "Harmonia axyridis" --output ./harmonia_fasta
```

---

## 在 Python 脚本中使用

```python
from pipeline import run_pipeline, run_export, print_stats

# 批量获取
species = [
    "Harmonia axyridis",
    "Harmonia yedoensis",
    "Solenopsis invicta",
]
run_pipeline(
    species_list=species,
    markers=["COI", "ITS"],
    source="both",
    ncbi_retmax=500,
)

# 导出
run_export(output_dir="./output", marker="COI")

# 统计
print_stats()
```

### 查询数据库

```python
from database import query_records

# 查询所有 Harmonia 属的 COI 序列
records = query_records(species="Harmonia", marker="COI")
for r in records:
    print(r["accession"], r["species"], r["length"])
```

---

## 注意事项

| 事项 | 说明 |
|------|------|
| NCBI API Key | 无 Key 限速 3 req/s；注册后 10 req/s，**强烈建议申请** |
| BOLD 速度 | BOLD 响应较慢，大批量时建议按属查询后本地筛选 |
| 去重 | 同一 accession 自动跳过，NCBI/BOLD 重叠记录不会重复入库 |
| 序列过滤 | 自动过滤长度异常和 N 比例过高（>5%）的序列 |
| 断点续传 | 重复运行时已入库的记录自动跳过，可安全中断后重跑 |
| 日志 | 详细记录见 `fetch.log`，fetch_log 表记录每次抓取状态 |

---

## 数据库结构

| 字段 | 说明 |
|------|------|
| accession | 唯一标识（GenBank Accession 或 BOLD Process ID） |
| source | NCBI / BOLD |
| species | 物种名（二名法标准化） |
| genus / family / order_name | 分类阶元 |
| marker | 标记基因（COI/ITS/rbcL 等） |
| sequence | 核苷酸序列 |
| length | 序列长度（bp） |
| country | 采集国家 |
| lat / lon | 经纬度 |
| bold_bin | BOLD BIN URI（物种代理单元） |
