#!/usr/bin/env python3
"""GitHub 指标采集、三级容错降级链与官方分位数评级计算（零第三方依赖）。"""

from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

GITHUB_GRAPHQL_API = "https://api.github.com/graphql"
GITHUB_REST_API = "https://api.github.com"
USER_AGENT = "huanxin886-profile-metrics/2.0"
DEFAULT_EXTRA_ORGS = ("HuanXinWork",)

RING_RADIUS = 33
RING_CIRCUMFERENCE = round(2.0 * math.pi * RING_RADIUS, 2)

LEVEL_MAP = {
    "NONE": "lv0",
    "FIRST_QUARTILE": "lv1",
    "SECOND_QUARTILE": "lv2",
    "THIRD_QUARTILE": "lv3",
    "FOURTH_QUARTILE": "lv4",
}

MONTH_ABBR = (
    "",
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

# Level 1 完整查询：含跨组织协作仓库及私有受限贡献计数（需具备对应读取权限的 PAT）。
GRAPHQL_USER_QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    login
    followers { totalCount }
    issues { totalCount }
    pullRequests(states: MERGED) { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
            contributionLevel
          }
        }
      }
    }
    repositories(
      ownerAffiliations: [OWNER, ORGANIZATION_MEMBER, COLLABORATOR]
      privacy: PUBLIC
      first: 100
      after: $after
      orderBy: {field: STARGAZERS, direction: DESC}
    ) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        nameWithOwner
        stargazerCount
      }
    }
  }
}
""".strip()

# Level 2 最小公开兼容查询：剥离受限字段与跨组织 affiliation，适配低权限内置令牌。
GRAPHQL_PUBLIC_USER_QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    login
    followers { totalCount }
    issues { totalCount }
    pullRequests(states: MERGED) { totalCount }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
            contributionLevel
          }
        }
      }
    }
    repositories(
      ownerAffiliations: [OWNER]
      privacy: PUBLIC
      first: 100
      after: $after
      orderBy: {field: STARGAZERS, direction: DESC}
    ) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        nameWithOwner
        stargazerCount
      }
    }
  }
}
""".strip()


@dataclass(frozen=True)
class RankResult:
    level: str
    percentile: float
    dashoffset: float


@dataclass(frozen=True)
class ContributionDay:
    date: str
    count: int
    level: str


@dataclass(frozen=True)
class GitHubMetrics:
    username: str
    commits_1y: int
    total_contributions_1y: int
    merged_prs: int
    total_stars: int
    peak_month_label: str
    isometric_grid: list[list[str]]
    rank: RankResult


def _exp_cdf(x: float) -> float:
    return 1.0 - (2.0 ** (-max(0.0, x)))


def _log_normal_cdf(x: float) -> float:
    safe_x = max(0.0, x)
    return safe_x / (1.0 + safe_x)


def calculate_rank(
    *,
    commits: int,
    prs: int,
    issues: int,
    reviews: int,
    stars: int,
    followers: int,
) -> RankResult:
    """复刻 anuraghazra/github-readme-stats (src/calculateRank.js) 的加权分位数公式。"""
    commits_median, commits_weight = 250.0, 2.0
    prs_median, prs_weight = 50.0, 3.0
    issues_median, issues_weight = 25.0, 1.0
    reviews_median, reviews_weight = 2.0, 1.0
    stars_median, stars_weight = 50.0, 4.0
    followers_median, followers_weight = 10.0, 1.0
    total_weight = (
        commits_weight
        + prs_weight
        + issues_weight
        + reviews_weight
        + stars_weight
        + followers_weight
    )

    weighted_score = (
        commits_weight * _exp_cdf(commits / commits_median)
        + prs_weight * _exp_cdf(prs / prs_median)
        + issues_weight * _exp_cdf(issues / issues_median)
        + reviews_weight * _exp_cdf(reviews / reviews_median)
        + stars_weight * _log_normal_cdf(stars / stars_median)
        + followers_weight * _log_normal_cdf(followers / followers_median)
    )
    percentile = max(0.0, min(100.0, (1.0 - weighted_score / total_weight) * 100.0))

    thresholds = (1.0, 12.5, 25.0, 37.5, 50.0, 62.5, 75.0, 87.5, 100.0)
    levels = ("S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C")
    level = "C"
    for threshold, candidate in zip(thresholds, levels):
        if percentile <= threshold:
            level = candidate
            break

    dashoffset = round(RING_CIRCUMFERENCE * (percentile / 100.0), 2)
    return RankResult(level=level, percentile=round(percentile, 2), dashoffset=dashoffset)


def compute_half_year_peak(weeks: list[list[ContributionDay]]) -> str:
    recent_weeks = weeks[-26:] if len(weeks) > 26 else weeks
    monthly_counts: dict[str, int] = {}
    for week in recent_weeks:
        for day in week:
            if len(day.date) >= 7:
                ym = day.date[:7]
                monthly_counts[ym] = monthly_counts.get(ym, 0) + max(0, day.count)

    if not monthly_counts:
        return "Peak: 0 commits"

    # 若多个月份并列最高，优先展示时间更近的月份。
    best_ym, peak_count = max(monthly_counts.items(), key=lambda kv: (kv[1], kv[0]))
    if peak_count <= 0:
        return "Peak: 0 commits"

    try:
        month_idx = int(best_ym.split("-")[1])
        abbr = MONTH_ABBR[month_idx] if 1 <= month_idx <= 12 else best_ym
    except (IndexError, ValueError):
        abbr = best_ym
    return f"{abbr} Peak: {peak_count:,} commits"


def extract_isometric_grid(weeks: list[list[ContributionDay]], cols: int = 21) -> list[list[str]]:
    """提取最近 cols 周的 21x7 等距地形等级矩阵。

    首周或当前未完结周可能不满 7 天；按真实日期映射回周日(0)..周六(6)行号，
    可避免残缺周导致整列星期错位，未到来的日期自动保持 lv0 基底。
    """
    selected = weeks[-cols:] if len(weeks) >= cols else weeks
    pad_cols = max(0, cols - len(selected))
    grid: list[list[str]] = [["lv0"] * 7 for _ in range(pad_cols)]

    for week in selected:
        col_levels = ["lv0"] * 7
        for idx, day in enumerate(week[:7]):
            mapped = LEVEL_MAP.get(day.level, day.level if day.level in LEVEL_MAP.values() else "lv0")
            try:
                parsed = datetime.strptime(day.date, "%Y-%m-%d").date()
                row_idx = (parsed.weekday() + 1) % 7
            except ValueError:
                row_idx = idx
            col_levels[row_idx] = mapped
        grid.append(col_levels)

    return grid


def parse_github_metrics(user_node: dict, total_stars: int) -> GitHubMetrics:
    username = str(user_node.get("login") or "huanxin886")
    followers = int((user_node.get("followers") or {}).get("totalCount") or 0)
    issues_total = int((user_node.get("issues") or {}).get("totalCount") or 0)
    merged_prs = int((user_node.get("pullRequests") or {}).get("totalCount") or 0)

    collection = user_node.get("contributionsCollection") or {}
    commit_contribs = int(collection.get("totalCommitContributions") or 0)
    restricted_contribs = int(collection.get("restrictedContributionsCount") or 0)
    pr_contribs = int(collection.get("totalPullRequestContributions") or 0)
    issue_contribs = int(collection.get("totalIssueContributions") or 0)
    review_contribs = int(collection.get("totalPullRequestReviewContributions") or 0)

    calendar = collection.get("contributionCalendar") or {}
    total_contribs_1y = int(
        calendar.get("totalContributions") or (commit_contribs + restricted_contribs)
    )
    commits_1y = commit_contribs + restricted_contribs

    weeks: list[list[ContributionDay]] = []
    for raw_week in calendar.get("weeks") or []:
        days: list[ContributionDay] = []
        for raw_day in raw_week.get("contributionDays") or []:
            days.append(
                ContributionDay(
                    date=str(raw_day.get("date") or ""),
                    count=int(raw_day.get("contributionCount") or 0),
                    level=str(raw_day.get("contributionLevel") or "NONE"),
                )
            )
        weeks.append(days)

    rank = calculate_rank(
        commits=commits_1y,
        prs=max(merged_prs, pr_contribs),
        issues=max(issues_total, issue_contribs),
        reviews=review_contribs,
        stars=max(0, total_stars),
        followers=followers,
    )

    return GitHubMetrics(
        username=username,
        commits_1y=commits_1y,
        total_contributions_1y=total_contribs_1y,
        merged_prs=merged_prs,
        total_stars=max(0, total_stars),
        peak_month_label=compute_half_year_peak(weeks),
        isometric_grid=extract_isometric_grid(weeks, cols=21),
        rank=rank,
    )


def parse_contributions_html(html: str) -> tuple[int, dict[str, ContributionDay]]:
    """从 GitHub 公开贡献日历 HTML 提取年度总数与每日等级。

    先定位含 data-date 的标签片段，再独立提取 data-date 与 data-level，
    避免依赖服务端 HTML 属性渲染先后顺序。
    """
    total_1y = 0
    heading_match = re.search(r"([\d,]+)\s+contributions?\s+in\s+the\s+last\s+year", html, re.I)
    if heading_match:
        total_1y = int(heading_match.group(1).replace(",", ""))

    level_lookup = {
        "0": "NONE",
        "1": "FIRST_QUARTILE",
        "2": "SECOND_QUARTILE",
        "3": "THIRD_QUARTILE",
        "4": "FOURTH_QUARTILE",
    }
    days_by_date: dict[str, ContributionDay] = {}
    for tag_match in re.finditer(r"<[a-zA-Z0-9]+\b[^>]*\bdata-date=[^>]*>", html):
        tag_text = tag_match.group(0)
        date_m = re.search(r'\bdata-date=["\'](\d{4}-\d{2}-\d{2})["\']', tag_text)
        level_m = re.search(r'\bdata-level=["\']([0-4])["\']', tag_text)
        if not date_m or not level_m:
            continue
        d_str, lv_num = date_m.group(1), level_m.group(1)
        approx_count = int(lv_num) * 2
        days_by_date[d_str] = ContributionDay(
            date=d_str,
            count=approx_count,
            level=level_lookup.get(lv_num, "NONE"),
        )

    if total_1y == 0 and days_by_date:
        total_1y = sum(day.count for day in days_by_date.values())
    return total_1y, days_by_date


def http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict | None = None,
    timeout: int = 30,
) -> tuple[int, dict | list]:
    req_headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if headers:
        req_headers.update(headers)
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    if body is not None:
        req_headers.setdefault("Content-Type", "application/json")

    request = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:240]
        except Exception:
            detail = ""
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail or exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(f"Network error requesting {url}: {reason}") from exc


def _rest_get_optional_auth(url: str, token: str | None) -> dict | list:
    """优先携带可选令牌避免公共 IP 低配额限流；若令牌报 401/403 则自动降级免鉴权重试一次。"""
    if token:
        try:
            _, data = http_json(url, headers={"Authorization": f"Bearer {token}"})
            return data
        except RuntimeError as exc:
            if "HTTP 401 " not in str(exc) and "HTTP 403 " not in str(exc):
                raise
    _, data = http_json(url)
    return data


def _resolve_extra_orgs(extra_orgs: tuple[str, ...] | list[str] | None = None) -> tuple[str, ...]:
    if extra_orgs is not None:
        return tuple(org.strip() for org in extra_orgs if org.strip())
    raw = os.environ.get("GITHUB_EXTRA_ORGS", ",".join(DEFAULT_EXTRA_ORGS))
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _merge_extra_org_stars(
    stars_by_repo: dict[str, int],
    extra_orgs: tuple[str, ...],
    token: str | None,
) -> None:
    """补齐隐藏组织成员身份下的公开组织星标，按 full_name 小写键去重防止与 GraphQL 重复计入。"""
    for org in extra_orgs:
        safe_org = urllib.parse.quote(org)
        url = f"{GITHUB_REST_API}/orgs/{safe_org}/repos?per_page=100&type=public"
        try:
            repos_data = _rest_get_optional_auth(url, token)
        except RuntimeError as exc:
            print(f"warning: skipping extra org '{org}' repos lookup: {exc}")
            continue

        if not isinstance(repos_data, list):
            continue
        for idx, repo in enumerate(repos_data):
            if not isinstance(repo, dict):
                continue
            full_name = str(repo.get("full_name") or f"{org}/__repo_{idx}").strip().lower()
            stars = int(repo.get("stargazers_count") or 0)
            stars_by_repo[full_name] = max(stars_by_repo.get(full_name, 0), stars)


def _run_graphql_query(
    query: str,
    username: str,
    token: str,
) -> tuple[dict, dict[str, int]]:
    headers = {"Authorization": f"Bearer {token}"}
    after_cursor: str | None = None
    first_user_node: dict | None = None
    stars_by_repo: dict[str, int] = {}
    anon_counter = 0

    # 仓库已按 STARGAZERS DESC 排序：一旦本页末尾星数为 0，后续分页全部为 0 星，可提前终止请求。
    for _ in range(10):
        _, body = http_json(
            GITHUB_GRAPHQL_API,
            method="POST",
            headers=headers,
            payload={"query": query, "variables": {"login": username, "after": after_cursor}},
        )
        if not isinstance(body, dict):
            raise RuntimeError("Unexpected GraphQL response type")

        user_node = (body.get("data") or {}).get("user")
        if body.get("errors"):
            err_msg = "; ".join(str(e.get("message") or e) for e in body["errors"])
            if not isinstance(user_node, dict):
                raise RuntimeError(f"GitHub GraphQL error for {username}: {err_msg}")
            print(f"warning: partial GraphQL errors tolerated for {username}: {err_msg}")

        if not isinstance(user_node, dict):
            raise RuntimeError(f"GitHub user '{username}' not found in GraphQL response")

        if first_user_node is None:
            first_user_node = user_node

        repos = user_node.get("repositories") or {}
        nodes = repos.get("nodes") or []
        for repo in nodes:
            if not isinstance(repo, dict):
                continue
            anon_counter += 1
            raw_key = str(repo.get("nameWithOwner") or f"__graphql_repo_{anon_counter}").strip().lower()
            stars = int(repo.get("stargazerCount") or 0)
            stars_by_repo[raw_key] = max(stars_by_repo.get(raw_key, 0), stars)

        page_info = repos.get("pageInfo") or {}
        last_stars = int(nodes[-1].get("stargazerCount") or 0) if nodes else 0
        if not page_info.get("hasNextPage") or last_stars == 0:
            break
        after_cursor = page_info.get("endCursor")

    assert first_user_node is not None
    return first_user_node, stars_by_repo


def _safe_search_count(query_expr: str, token: str | None) -> int:
    """Search API 限流严苛（匿名 10 req/min），任何限流或权限异常均降级返回 0 而不中断构建。"""
    url = f"{GITHUB_REST_API}/search/issues?q={query_expr}&per_page=1"
    try:
        payload = _rest_get_optional_auth(url, token)
        return int(payload.get("total_count") or 0) if isinstance(payload, dict) else 0
    except RuntimeError as exc:
        print(f"warning: GitHub search fallback degraded to 0 for '{query_expr}': {exc}")
        return 0


def _fetch_github_public_fallback(
    username: str,
    *,
    token: str | None = None,
    extra_orgs: tuple[str, ...] = DEFAULT_EXTRA_ORGS,
) -> GitHubMetrics:
    """Level 3 公开 REST + 贡献页 HTML 兜底路径（兼容无令牌与受限 github.token 场景）。"""
    safe_user = urllib.parse.quote(username)
    user_info = _rest_get_optional_auth(f"{GITHUB_REST_API}/users/{safe_user}", token)
    if not isinstance(user_info, dict):
        raise RuntimeError("Unexpected GitHub REST user response")

    repos_info = _rest_get_optional_auth(
        f"{GITHUB_REST_API}/users/{safe_user}/repos?per_page=100&sort=pushed", token
    )
    stars_by_repo: dict[str, int] = {}
    if isinstance(repos_info, list):
        for idx, repo in enumerate(repos_info):
            if not isinstance(repo, dict):
                continue
            key = str(repo.get("full_name") or f"{username}/__repo_{idx}").strip().lower()
            stars_by_repo[key] = max(stars_by_repo.get(key, 0), int(repo.get("stargazers_count") or 0))

    _merge_extra_org_stars(stars_by_repo, extra_orgs, token)
    total_stars = sum(stars_by_repo.values())

    merged_prs = _safe_search_count(f"author:{safe_user}+type:pr+is:merged", token)
    issues_total = _safe_search_count(f"author:{safe_user}+type:issue", token)

    contrib_url = f"https://github.com/users/{safe_user}/contributions"
    req = urllib.request.Request(contrib_url, headers={"User-Agent": USER_AGENT})
    days_by_date: dict[str, ContributionDay] = {}
    total_1y = 0
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        total_1y, days_by_date = parse_contributions_html(html)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"warning: public contributions HTML fetch failed for {username}: {exc}")

    weeks: list[list[ContributionDay]] = []
    if days_by_date:
        current_week: list[ContributionDay] = []
        for d_str in sorted(days_by_date.keys()):
            dt = datetime.strptime(d_str, "%Y-%m-%d").date()
            if current_week and (dt.weekday() + 1) % 7 == 0:
                weeks.append(current_week)
                current_week = []
            current_week.append(days_by_date[d_str])
        if current_week:
            weeks.append(current_week)

    followers = int(user_info.get("followers") or 0)
    rank = calculate_rank(
        commits=total_1y,
        prs=merged_prs,
        issues=issues_total,
        reviews=0,
        stars=total_stars,
        followers=followers,
    )
    return GitHubMetrics(
        username=str(user_info.get("login") or username),
        commits_1y=total_1y,
        total_contributions_1y=total_1y,
        merged_prs=merged_prs,
        total_stars=total_stars,
        peak_month_label=compute_half_year_peak(weeks),
        isometric_grid=extract_isometric_grid(weeks, cols=21),
        rank=rank,
    )


def fetch_github_metrics(
    username: str | None = None,
    token: str | None = None,
    *,
    extra_orgs: tuple[str, ...] | list[str] | None = None,
) -> GitHubMetrics:
    """按 Level 1 (完整 GraphQL) -> Level 2 (公开兼容 GraphQL + 组织补齐) -> Level 3 (公开 REST/HTML) 采集。"""
    resolved_user = (username or os.environ.get("GITHUB_USER") or "huanxin886").strip()
    resolved_token = (
        token
        or os.environ.get("GH_TOKEN")
        or os.environ.get("METRICS_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or ""
    ).strip()
    orgs = _resolve_extra_orgs(extra_orgs)

    if not resolved_token:
        return _fetch_github_public_fallback(resolved_user, token=None, extra_orgs=orgs)

    # Level 1: 完整 GraphQL 查询 + 隐藏成员公开组织星标去重补齐
    try:
        user_node, stars_by_repo = _run_graphql_query(GRAPHQL_USER_QUERY, resolved_user, resolved_token)
        _merge_extra_org_stars(stars_by_repo, orgs, resolved_token)
        return parse_github_metrics(user_node, total_stars=sum(stars_by_repo.values()))
    except RuntimeError as lv1_exc:
        print(f"warning: Level 1 GraphQL failed ({lv1_exc}), retrying Level 2 public GraphQL")

    # Level 2: 剥离受限字段的最小公开兼容版 GraphQL + 公开组织星标去重补齐
    try:
        user_node, stars_by_repo = _run_graphql_query(
            GRAPHQL_PUBLIC_USER_QUERY, resolved_user, resolved_token
        )
        _merge_extra_org_stars(stars_by_repo, orgs, resolved_token)
        return parse_github_metrics(user_node, total_stars=sum(stars_by_repo.values()))
    except RuntimeError as lv2_exc:
        print(f"warning: Level 2 GraphQL failed ({lv2_exc}), falling back to Level 3 REST/HTML")

    # Level 3: 公开 REST + HTML 兜底
    return _fetch_github_public_fallback(resolved_user, token=resolved_token, extra_orgs=orgs)
