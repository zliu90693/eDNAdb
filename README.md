<div align="right">

**English** | [简体中文](README.zh-CN.md)

</div>

# Barcode Database Builder

Batch-retrieve species barcode sequences from **NCBI GenBank**, build a local SQLite database, and export FASTA files. No Biopython dependency required.

---

## Project Structure

```text
barcode_db/
├── main.py           # Command-line entry point
├── pipeline.py       # Main pipeline orchestrator
├── fetcher_ncbi.py   # NCBI E-utilities retrieval module
├── fetcher_bold.py   # BOLD Systems retrieval module
├── database.py       # SQLite database management
├── config.py         # Global configuration (edit this file to fit your needs)
├── species.txt       # Example species list
└── requirements.txt  # Dependencies
```

---

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configuration

Edit `config.py`:

```python
NCBI_API_KEY = "your_api_key"    # Strongly recommended: https://www.ncbi.nlm.nih.gov/account/
NCBI_EMAIL   = "your@email.com"  # Required by NCBI
TARGET_MARKERS = ["COI"]         # Target marker genes
```

### 3. Prepare the Species List

Edit `species.txt`, with one species name per line. Genus-level batch queries are also supported:

```text
# Invasive species
Solenopsis invicta
Solenopsis geminata
Frankliniella occidentalis

# Closely related native species
Solenopsis jacoti
Solenopsis fugax
Solenopsis tipuna
Frankliniella intonsa
```

---

## Usage

### Fetch Data

```bash
# Read species from a file and fetch COI sequences from both NCBI and BOLD
python main.py fetch --file species.txt --markers COI

# Use NCBI only to fetch COI and ITS
python main.py fetch --file species.txt --markers COI,ITS --source ncbi

# Specify species directly on the command line (quick test)
python main.py fetch --species "Harmonia axyridis,Harmonia yedoensis" --markers COI

# Fetch at most 200 records per species using BOLD only
python main.py fetch --file species.txt --source bold --retmax 200

# Enable verbose logging
python main.py fetch --file species.txt --verbose
```

### View Statistics

```bash
python main.py stats
```

Example output:

```text
Database Statistics
  Total records: 1836
  NCBI records:  1836
  BOLD records:  0
  Species count: 5

  Records by marker:
    COI          1835
    COXI         1

  Species with the most records (Top 20):
    Frankliniella occidentalis               500
    Solenopsis geminata                      499
    Frankliniella intonsa                    488
    Solenopsis invicta                       347
    Solenopsis fugax                         2
    ...
```

### Export FASTA

```bash
# Export all sequences (one file per marker)
python main.py export --output ./my_fasta

# Export COI only
python main.py export --marker COI --output ./coi_fasta

# Export a single species only
python main.py export --species "Harmonia axyridis" --output ./harmonia_fasta
```

---

## Using the Project in Python Scripts

```python
from pipeline import run_pipeline, run_export, print_stats

# Batch retrieval
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

# Export
run_export(output_dir="./output", marker="COI")

# Statistics
print_stats()
```

### Query the Database

```python
from database import query_records

# Query all COI sequences from the genus Harmonia
records = query_records(species="Harmonia", marker="COI")
for r in records:
    print(r["accession"], r["species"], r["length"])
```

---

## Notes

| Item | Description |
|------|-------------|
| NCBI API Key | Without an API key, requests are limited to 3 req/s; registered users can use up to 10 req/s. **Applying for a key is strongly recommended.** |
| BOLD performance | BOLD responses can be relatively slow. For large-scale retrieval, genus-level queries followed by local filtering are recommended. |
| Deduplication | Records with the same accession are skipped automatically. Overlapping records from NCBI and BOLD are not inserted twice. |
| Sequence filtering | Sequences with abnormal lengths or a high proportion of `N` bases (>5%) are filtered automatically. |
| Resume support | Records already stored in the database are skipped on repeated runs, so interrupted jobs can safely be resumed. |
| Logging | Detailed logs are written to `fetch.log`; the `fetch_log` table records the status of each retrieval run. |

---

## Database Schema

| Field | Description |
|------|-------------|
| accession | Unique identifier (GenBank accession or BOLD Process ID) |
| source | NCBI / BOLD |
| species | Species name (standardized binomial nomenclature) |
| genus / family / order_name | Taxonomic ranks |
| marker | Marker gene (COI/ITS/rbcL, etc.) |
| sequence | Nucleotide sequence |
| length | Sequence length (bp) |
| country | Country of collection |
| lat / lon | Latitude / longitude |
| bold_bin | BOLD BIN URI (species proxy unit) |
