#!/usr/bin/env python3

# 命令行入口, 用法见 README.md 或运行 python main.py --help


import argparse
import sys
from pipeline import run_pipeline, run_export, print_stats, load_species_list
from config import TARGET_MARKERS


def cmd_fetch(args):
    # 执行数据获取, 优先用命令行物种列表，否则读取文件
    if args.species:
        species_list = [s.strip() for s in args.species.split(",") if s.strip()]
    elif args.file:
        species_list = load_species_list(args.file)
    else:
        print("错误：请指定 --species 或 --file")
        sys.exit(1)

    markers = [m.strip() for m in args.markers.split(",")] if args.markers else None

    run_pipeline(
        species_list=species_list,
        markers=markers,
        source=args.source,
        ncbi_retmax=args.retmax,
        verbose=args.verbose,
    )


def cmd_export(args):
    # 执行导出
    run_export(
        output_dir=args.output,
        marker=args.marker or None,
        species=args.species or None,
    )


def cmd_stats(_args):
    # 打印统计
    print_stats()


def main():
    parser = argparse.ArgumentParser(
        prog="barcode-db",
        description="条形码数据库构建工具：从 NCBI / BOLD 批量获取物种条形码序列",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 从文件读取物种列表，获取 COI 序列（NCBI + BOLD）
  python main.py fetch --file species.txt --markers COI

  # 命令行直接指定物种，仅用 NCBI，获取多个标记
  python main.py fetch --species "Harmonia axyridis,Harmonia yedoensis" \\
                       --markers COI,ITS --source ncbi

  # 查看数据库统计
  python main.py stats

  # 导出所有 COI 序列为 FASTA
  python main.py export --marker COI --output ./my_fasta
        """,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # fetch 子命令
    fetch_p = subparsers.add_parser("fetch", help="从 NCBI/BOLD 获取条形码数据")
    fetch_p.add_argument(
        "--file", "-f",
        help="物种列表文件路径（每行一个物种名，# 开头为注释）"
    )
    fetch_p.add_argument(
        "--species", "-s",
        help="直接指定物种名，多个用英文逗号分隔"
    )
    fetch_p.add_argument(
        "--markers", "-m",
        default=",".join(TARGET_MARKERS),
        help=f"条形码标记，逗号分隔（默认: {','.join(TARGET_MARKERS)}）"
    )
    fetch_p.add_argument(
        "--source",
        choices=["both", "ncbi", "bold"],
        default="both",
        help="数据来源（默认: both）"
    )
    fetch_p.add_argument(
        "--retmax",
        type=int,
        default=500,
        help="NCBI 每个物种最大获取数量（默认: 500）"
    )
    fetch_p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="输出详细调试日志"
    )
    fetch_p.set_defaults(func=cmd_fetch)

    # export 子命令
    export_p = subparsers.add_parser("export", help="将数据库导出为 FASTA 文件")
    export_p.add_argument(
        "--output", "-o",
        default="fasta_output",
        help="输出目录（默认: fasta_output/）"
    )
    export_p.add_argument(
        "--marker",
        help="仅导出指定标记（如 COI）"
    )
    export_p.add_argument(
        "--species",
        help="仅导出指定物种（支持模糊匹配，如 'Harmonia'）"
    )
    export_p.set_defaults(func=cmd_export)

    # stats 子命令
    stats_p = subparsers.add_parser("stats", help="查看数据库统计信息")
    stats_p.set_defaults(func=cmd_stats)

    # 解析并执行
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
