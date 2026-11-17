#!/usr/bin/env python3
"""Regenerate the waka section of README.md from the WakaTime API.

WakaTime now rejects API keys on read endpoints (403: "API Keys are only for
plugins"), so this script authenticates with an OAuth access token
(scope: read_stats) supplied through the WAKATIME_TOKEN environment variable.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = "https://api.wakatime.com/api/v1"
README = "README.md"
START = "<!--START_SECTION:waka-->"
END = "<!--END_SECTION:waka-->"
MAX_ITEMS = 5
BAR_WIDTH = 25
EMPTY = "本周没有记录到任何活动"

# Heartbeats sent while testing the plugin show up as editors; keep them out.
IGNORED_EDITORS = {"key validity check", "key-validity", "key-validity-check"}


def api_get(path: str) -> dict:
    token = os.environ.get("WAKATIME_TOKEN")
    if not token:
        sys.exit("WAKATIME_TOKEN is not set")

    request = urllib.request.Request(
        f"{API}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "huanxin886-readme-stats/1.0",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))["data"]


def api_get_fresh(path: str, max_wait: int = 300) -> dict:
    """Stats endpoints answer 202 while WakaTime recomputes them.

    Poll until the payload is up to date, falling back to the last partial
    response when the wait budget runs out.
    """
    deadline = time.time() + max_wait

    while True:
        data = api_get(path)

        if data.get("is_up_to_date") is not False:
            return data

        if time.time() >= deadline:
            print(f"warning: {path} still updating after {max_wait}s, using partial data")
            return data

        print(f"{path} is still being computed, retrying in 15s")
        time.sleep(15)


def humanize(seconds: float) -> str:
    minutes = int(seconds // 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        hour_label = "hr" if hours == 1 else "hrs"
        return f"{hours} {hour_label} {minutes} mins"

    return f"{minutes} min" if minutes == 1 else f"{minutes} mins"


def bar(percent: float) -> str:
    filled = max(0, min(BAR_WIDTH, round(percent / 100 * BAR_WIDTH)))
    return "█" * filled + "░" * (BAR_WIDTH - filled)


def badge(label: str, message: str, color: str = "blue") -> str:
    def escape(text: str) -> str:
        return text.replace("-", "--").replace("_", "__").replace(" ", "_")

    return f"https://img.shields.io/badge/{escape(label)}-{escape(message)}-{color}?style=flat"


def section(title: str, items: list[dict]) -> str:
    if not items:
        return f"**{title}**\n\n```text\n{EMPTY}\n```\n"

    rows = []
    for item in items[:MAX_ITEMS]:
        name = item["name"][:24]
        rows.append(
            f"{name:<24} {humanize(item['total_seconds']):<16} "
            f"{bar(item['percent'])} {item['percent']:5.2f} %"
        )

    return f"**{title}**\n\n```text\n" + "\n".join(rows) + "\n```\n"


def main() -> None:
    all_time = api_get_fresh("/users/current/stats/all_time")
    week = api_get_fresh("/users/current/stats/last_7_days", max_wait=120)

    start = (week.get("start") or "")[:10]
    end = (week.get("end") or "")[:10]
    period = f"{start} ~ {end}" if start and end else "最近 7 天"

    parts = [
        f"![Code Time]({badge('Code Time', humanize(all_time.get('total_seconds') or 0))})",
        "",
        f"**📅 {period}**",
        "",
        section("💬 编程语言", week.get("languages") or []),
        section("🔥 编辑器", [
            editor
            for editor in (week.get("editors") or [])
            if editor["name"].strip().lower() not in IGNORED_EDITORS
        ]),
        section("🐱‍💻 项目", week.get("projects") or []),
        section("💻 操作系统", week.get("operating_systems") or []),
        f"最后更新：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
    ]
    block = "\n".join(parts).rstrip() + "\n"

    with open(README, encoding="utf-8") as handle:
        content = handle.read()

    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(content):
        sys.exit(f"{START} / {END} markers not found in {README}")

    with open(README, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(pattern.sub(f"{START}\n{block}{END}", content))

    print("README waka section updated")


if __name__ == "__main__":
    main()
