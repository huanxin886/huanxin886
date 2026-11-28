#!/usr/bin/env python3
"""主页指标 SVG 生成入口：拉取 WakaTime 与 GitHub 数据并渲染全套 6 张双主题卡片。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 支持直接执行 `python scripts/update_waka.py` 时解析顶层 `scripts.*` 包路径。
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.fetch_metrics import collect_profile_metrics  # noqa: E402
from scripts.svg_renderer import write_all_svgs  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate GitHub Profile Dark/Light SVG dashboards."
    )
    parser.add_argument(
        "--out-dir",
        default="dist",
        help="Output directory for generated SVG files (default: dist).",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use deterministic built-in snapshot data without network/API tokens.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    metrics = collect_profile_metrics(demo=args.demo)
    written = write_all_svgs(metrics, args.out_dir)

    gh = metrics.github
    wk = metrics.waka
    mode_tag = "DEMO" if args.demo else "LIVE"
    top_langs = ", ".join(f"{item.name} ({item.percent:.1f}%)" for item in wk.languages) or "none"

    print(
        f"[{mode_tag}] Generated {len(written)} validated SVGs in '{args.out_dir}': "
        f"user=@{gh.username}, rank={gh.rank.level} (TOP {max(1, round(gh.rank.percentile))}%), "
        f"contribs_1y={gh.total_contributions_1y}, stars={gh.total_stars}, "
        f"waka_total={wk.all_time_hours}h {wk.all_time_minutes}m, langs=[{top_langs}]"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
