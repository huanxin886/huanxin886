#!/usr/bin/env python3
"""WakaTime 指标采集清洗与 Profile 聚合入口（零第三方依赖）。"""

from __future__ import annotations

import os
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from scripts.github_metrics import (
    RING_CIRCUMFERENCE,
    RING_RADIUS,
    ContributionDay,
    GitHubMetrics,
    RankResult,
    calculate_rank,
    compute_half_year_peak,
    extract_isometric_grid,
    fetch_github_metrics,
    http_json,
    parse_contributions_html,
    parse_github_metrics,
)

__all__ = [
    "IGNORED_EDITORS",
    "IGNORED_LANGUAGES",
    "IGNORED_PROJECTS",
    "RING_CIRCUMFERENCE",
    "RING_RADIUS",
    "ContributionDay",
    "EditorStat",
    "GitHubMetrics",
    "LanguageStat",
    "ProfileMetrics",
    "ProjectStat",
    "RankResult",
    "WakaMetrics",
    "build_demo_metrics",
    "calculate_rank",
    "collect_profile_metrics",
    "compute_half_year_peak",
    "extract_isometric_grid",
    "fetch_github_metrics",
    "fetch_waka_metrics",
    "format_short_duration",
    "parse_contributions_html",
    "parse_github_metrics",
    "parse_waka_metrics",
    "truncate_label",
    "waka_get_fresh",
]

WAKATIME_API = "https://api.wakatime.com/api/v1"

# WakaTime 会把非代码资源查看记录为语言耗时，需剔除后重算真实编码语言占比。
IGNORED_LANGUAGES = frozenset({
    "other",
    "image (png)",
    "image (svg)",
    "image (jpg)",
    "image (jpeg)",
    "image (webp)",
    "image (ico)",
    "binary",
    "text",
})

# 泛指目录或未命名工作区不具备项目辨识度，不在活跃仓库面板展示。
IGNORED_PROJECTS = frozenset({"work", "unknown", "unnamed"})

# 插件连通性探针心跳会伪装成编辑器名称，需沿用旧版黑名单剔除。
IGNORED_EDITORS = frozenset({"key validity check", "key-validity", "key-validity-check"})


@dataclass(frozen=True)
class LanguageStat:
    name: str
    total_seconds: float
    percent: float
    time_text: str


@dataclass(frozen=True)
class ProjectStat:
    name: str
    total_seconds: float
    percent: float
    time_text: str


@dataclass(frozen=True)
class EditorStat:
    name: str
    percent: float


@dataclass(frozen=True)
class WakaMetrics:
    all_time_hours: int
    all_time_minutes: int
    editors: list[EditorStat]
    os_name: str
    os_percent: float
    languages: list[LanguageStat]
    projects: list[ProjectStat]
    synced_date: str


@dataclass(frozen=True)
class ProfileMetrics:
    github: GitHubMetrics
    waka: WakaMetrics


def _char_display_width(ch: str) -> int:
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def truncate_label(text: str, max_chars: int = 24) -> str:
    """按等宽视觉列宽截断标签，避免长项目名侵入右侧时长数值区域。"""
    cleaned = " ".join(text.split())
    if max_chars <= 1:
        return cleaned[:max_chars]

    total_width = sum(_char_display_width(ch) for ch in cleaned)
    if total_width <= max_chars:
        return cleaned

    budget = max_chars - 1
    out: list[str] = []
    used = 0
    for ch in cleaned:
        w = _char_display_width(ch)
        if used + w > budget:
            break
        out.append(ch)
        used += w
    return "".join(out).rstrip() + "…"


def format_short_duration(seconds: float) -> str:
    safe_seconds = max(0.0, float(seconds))
    if 0 < safe_seconds < 60:
        return "<1m"
    total_minutes = int(safe_seconds // 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def parse_waka_metrics(
    all_time_data: dict,
    week_data: dict,
    *,
    synced_date: str | None = None,
) -> WakaMetrics:
    total_seconds = max(0.0, float(all_time_data.get("total_seconds") or 0.0))
    total_minutes = int(total_seconds // 60)
    all_time_hours, all_time_minutes = divmod(total_minutes, 60)

    # 语言：过滤噪音条目并基于剩余有效编码总时长重算百分比，空列表安全回退避免除零。
    valid_langs: list[tuple[str, float]] = []
    for item in week_data.get("languages") or []:
        raw_name = str(item.get("name") or "").strip()
        secs = float(item.get("total_seconds") or 0.0)
        if not raw_name or secs <= 0 or raw_name.lower() in IGNORED_LANGUAGES:
            continue
        valid_langs.append((truncate_label(raw_name, 16), secs))
    valid_langs.sort(key=lambda pair: pair[1], reverse=True)
    lang_total = sum(secs for _, secs in valid_langs)
    languages = (
        [
            LanguageStat(
                name=name,
                total_seconds=secs,
                percent=round((secs / lang_total) * 100.0, 1),
                time_text=format_short_duration(secs),
            )
            for name, secs in valid_langs[:3]
        ]
        if lang_total > 0
        else []
    )

    # 项目：过滤 Work/Unknown 等泛化名称，取 Top 4 供右侧活跃仓库面板渲染。
    valid_projects: list[tuple[str, float]] = []
    for item in week_data.get("projects") or []:
        raw_name = str(item.get("name") or "").strip()
        secs = float(item.get("total_seconds") or 0.0)
        if not raw_name or secs <= 0 or raw_name.lower() in IGNORED_PROJECTS:
            continue
        valid_projects.append((truncate_label(raw_name, 24), secs))
    valid_projects.sort(key=lambda pair: pair[1], reverse=True)
    proj_total = sum(secs for _, secs in valid_projects)
    projects = (
        [
            ProjectStat(
                name=name,
                total_seconds=secs,
                percent=round((secs / proj_total) * 100.0, 1),
                time_text=format_short_duration(secs),
            )
            for name, secs in valid_projects[:4]
        ]
        if proj_total > 0
        else []
    )

    # 编辑器：剔除探针心跳后重算有效占比，取 Top 2。
    valid_editors: list[tuple[str, float, float]] = []
    for item in week_data.get("editors") or []:
        raw_name = str(item.get("name") or "").strip()
        if not raw_name or raw_name.lower() in IGNORED_EDITORS:
            continue
        secs = float(item.get("total_seconds") or 0.0)
        pct = float(item.get("percent") or 0.0)
        if secs <= 0 and pct <= 0:
            continue
        valid_editors.append((truncate_label(raw_name, 14), secs, pct))
    valid_editors.sort(key=lambda item: (item[1], item[2]), reverse=True)
    ed_total = sum(secs for _, secs, _ in valid_editors)
    editors: list[EditorStat] = []
    for name, secs, raw_pct in valid_editors[:2]:
        pct = (secs / ed_total * 100.0) if ed_total > 0 else raw_pct
        editors.append(EditorStat(name=name, percent=round(pct, 1)))

    os_items = [
        item
        for item in (week_data.get("operating_systems") or [])
        if str(item.get("name") or "").strip()
    ]
    os_items.sort(
        key=lambda item: (float(item.get("total_seconds") or 0.0), float(item.get("percent") or 0.0)),
        reverse=True,
    )
    if os_items:
        top_os = os_items[0]
        os_name = truncate_label(str(top_os["name"]).strip(), 12)
        os_total = sum(float(x.get("total_seconds") or 0.0) for x in os_items)
        os_secs = float(top_os.get("total_seconds") or 0.0)
        os_percent = (
            round(os_secs / os_total * 100.0, 1)
            if os_total > 0
            else round(float(top_os.get("percent") or 0.0), 1)
        )
    else:
        os_name, os_percent = "Unknown", 0.0

    resolved_date = synced_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return WakaMetrics(
        all_time_hours=all_time_hours,
        all_time_minutes=all_time_minutes,
        editors=editors,
        os_name=os_name,
        os_percent=os_percent,
        languages=languages,
        projects=projects,
        synced_date=resolved_date,
    )


def waka_get_fresh(
    path: str,
    token: str,
    *,
    max_wait: int = 300,
    poll_interval: int = 15,
) -> dict:
    """WakaTime 统计端点在后台重算期间会返回 202 或 is_up_to_date=False，需轮询等待。"""
    deadline = time.monotonic() + max_wait
    headers = {"Authorization": f"Bearer {token}"}

    while True:
        status, body = http_json(f"{WAKATIME_API}{path}", headers=headers)
        if not isinstance(body, dict) or not isinstance(body.get("data"), dict):
            raise RuntimeError(f"Unexpected WakaTime payload structure for {path}")
        data = body["data"]

        if status != 202 and data.get("is_up_to_date") is not False:
            return data

        if time.monotonic() >= deadline:
            print(f"warning: {path} still updating after {max_wait}s, using partial data")
            return data

        print(f"{path} is still being computed, retrying in {poll_interval}s")
        time.sleep(poll_interval)


def fetch_waka_metrics(token: str | None = None) -> WakaMetrics:
    resolved_token = (token or os.environ.get("WAKATIME_TOKEN") or "").strip()
    if not resolved_token:
        raise RuntimeError("WAKATIME_TOKEN is not set (use --demo for offline rendering)")

    all_time = waka_get_fresh("/users/current/stats/all_time", resolved_token, max_wait=300)
    week = waka_get_fresh("/users/current/stats/last_7_days", resolved_token, max_wait=120)
    return parse_waka_metrics(all_time, week)


def build_demo_metrics() -> ProfileMetrics:
    """生成确定性离线快照数据，供本地 --demo 预览及单元测试全链路验证。"""
    demo_grid_levels = [
        [0, 1, 0, 0, 1, 0, 0],
        [0, 0, 2, 1, 0, 0, 1],
        [1, 0, 0, 0, 2, 1, 0],
        [0, 1, 1, 0, 0, 0, 0],
        [0, 2, 3, 1, 0, 1, 0],
        [0, 0, 1, 2, 1, 0, 0],
        [1, 0, 0, 0, 1, 2, 0],
        [0, 1, 2, 0, 0, 1, 0],
        [0, 0, 1, 3, 2, 0, 1],
        [1, 2, 0, 1, 0, 0, 0],
        [0, 1, 2, 2, 1, 0, 1],
        [2, 1, 0, 1, 3, 2, 0],
        [0, 2, 3, 1, 1, 0, 1],
        [1, 2, 1, 2, 3, 1, 0],
        [2, 3, 2, 4, 2, 2, 1],
        [2, 3, 4, 3, 2, 3, 2],
        [3, 4, 3, 4, 3, 2, 1],
        [2, 3, 4, 3, 4, 3, 2],
        [3, 2, 3, 4, 2, 3, 1],
        [4, 3, 4, 3, 3, 2, 2],
        [3, 4, 2, 3, 4, 2, 1],
    ]
    num_to_enum = {
        0: "NONE",
        1: "FIRST_QUARTILE",
        2: "SECOND_QUARTILE",
        3: "THIRD_QUARTILE",
        4: "FOURTH_QUARTILE",
    }
    anchor_sunday = date(2026, 11, 22) - timedelta(weeks=20)
    weeks_payload = []
    for col_idx, col in enumerate(demo_grid_levels):
        days_payload = []
        for row_idx, lv in enumerate(col):
            d = anchor_sunday + timedelta(weeks=col_idx, days=row_idx)
            count = (0, 1, 2, 3, 4)[lv] if d.month == 11 else (0, 1, 1, 2, 3)[lv]
            days_payload.append({
                "date": d.isoformat(),
                "contributionCount": count,
                "contributionLevel": num_to_enum[lv],
            })
        weeks_payload.append({"contributionDays": days_payload})

    demo_user = {
        "login": "huanxin886",
        "followers": {"totalCount": 32},
        "issues": {"totalCount": 26},
        "pullRequests": {"totalCount": 48},
        "contributionsCollection": {
            "totalCommitContributions": 215,
            "restrictedContributionsCount": 18,
            "totalPullRequestContributions": 48,
            "totalIssueContributions": 26,
            "totalPullRequestReviewContributions": 8,
            "contributionCalendar": {
                "totalContributions": 233,
                "weeks": weeks_payload,
            },
        },
    }
    github = parse_github_metrics(demo_user, total_stars=215)

    waka_all_time = {"total_seconds": (1220 * 3600) + (20 * 60)}
    waka_week = {
        "languages": [
            {"name": "Other", "total_seconds": 18000},
            {"name": "Image (png)", "total_seconds": 3600},
            {"name": "C#", "total_seconds": 36960},
            {"name": "Python", "total_seconds": 7980},
            {"name": "Markdown", "total_seconds": 7140},
        ],
        "projects": [
            {"name": "Work", "total_seconds": 25000},
            {"name": "asp-assistant-arknights", "total_seconds": 48300},
            {"name": "CasualtiesUnknown-SkinEd", "total_seconds": 41580},
            {"name": "SkinSync", "total_seconds": 10980},
            {"name": "CuSaveManager", "total_seconds": 7800},
        ],
        "editors": [
            {"name": "key-validity-check", "total_seconds": 120, "percent": 0.5},
            {"name": "VS Code", "total_seconds": 50600, "percent": 90.3},
            {"name": "Codex CLI", "total_seconds": 1960, "percent": 3.5},
        ],
        "operating_systems": [
            {"name": "Windows", "total_seconds": 52560, "percent": 100.0},
        ],
    }
    waka = parse_waka_metrics(waka_all_time, waka_week, synced_date="2026-11-28")
    return ProfileMetrics(github=github, waka=waka)


def collect_profile_metrics(*, demo: bool = False) -> ProfileMetrics:
    if demo:
        return build_demo_metrics()
    waka = fetch_waka_metrics()
    github = fetch_github_metrics()
    return ProfileMetrics(github=github, waka=waka)
