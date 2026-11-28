#!/usr/bin/env python3
"""主页 SVG 生成器单元测试：覆盖分位数评级、数据清洗边界、XML 注入转义与全链路渲染。"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from scripts.fetch_metrics import (
    RING_CIRCUMFERENCE,
    ContributionDay,
    EditorStat,
    GitHubMetrics,
    LanguageStat,
    ProfileMetrics,
    ProjectStat,
    WakaMetrics,
    calculate_rank,
    compute_half_year_peak,
    extract_isometric_grid,
    fetch_github_metrics,
    parse_contributions_html,
    parse_waka_metrics,
    truncate_label,
)
from scripts.svg_renderer import (
    render_all_svgs,
    validate_svg_xml,
)
from scripts.update_waka import main as cli_main

EXPECTED_FILES = (
    "hero-dark.svg",
    "hero-light.svg",
    "waka-bento-dark.svg",
    "waka-bento-light.svg",
    "contrib-3d-dark.svg",
    "contrib-3d-light.svg",
)


class ProfileGeneratorTests(unittest.TestCase):
    def test_calculate_rank_percentiles_and_levels(self) -> None:
        zero_rank = calculate_rank(
            commits=0, prs=0, issues=0, reviews=0, stars=0, followers=0
        )
        self.assertEqual(zero_rank.level, "C")
        self.assertAlmostEqual(zero_rank.percentile, 100.0, places=2)
        self.assertAlmostEqual(zero_rank.dashoffset, RING_CIRCUMFERENCE, places=2)

        # 所有维度恰好处于中位数时，exp_cdf(1)=0.5 且 log_normal_cdf(1)=0.5，分位数严格为 50% -> B+
        median_rank = calculate_rank(
            commits=250, prs=50, issues=25, reviews=2, stars=50, followers=10
        )
        self.assertAlmostEqual(median_rank.percentile, 50.0, places=2)
        self.assertEqual(median_rank.level, "B+")
        self.assertAlmostEqual(
            median_rank.dashoffset, round(RING_CIRCUMFERENCE * 0.5, 2), places=2
        )

        # 头部高活跃指标应命中 S 级（TOP 1% 以内）
        top_rank = calculate_rank(
            commits=5000, prs=800, issues=400, reviews=200, stars=25000, followers=5000
        )
        self.assertEqual(top_rank.level, "S")
        self.assertLessEqual(top_rank.percentile, 1.0)

        # A- 区间（25 < percentile <= 37.5）校验
        a_minus = calculate_rank(
            commits=233, prs=48, issues=26, reviews=8, stars=215, followers=32
        )
        self.assertEqual(a_minus.level, "A-")
        self.assertGreater(a_minus.percentile, 25.0)
        self.assertLessEqual(a_minus.percentile, 37.5)

    def test_waka_filtering_recompute_and_zero_division_guard(self) -> None:
        all_time = {"total_seconds": 3665}
        week_noise_and_valid = {
            "languages": [
                {"name": "OTHER", "total_seconds": 9000},
                {"name": "Image (PNG)", "total_seconds": 3000},
                {"name": "Image (svg)", "total_seconds": 1200},
                {"name": "binary", "total_seconds": 500},
                {"name": "Text", "total_seconds": 400},
                {"name": "C#", "total_seconds": 3000},
                {"name": "Python", "total_seconds": 1000},
            ],
            "projects": [
                {"name": "Work", "total_seconds": 8000},
                {"name": "UNKNOWN", "total_seconds": 2000},
                {"name": "unnamed", "total_seconds": 1000},
                {
                    "name": "SuperLongRepositoryNameThatExceedsTwentyFourCharacters",
                    "total_seconds": 3600,
                },
            ],
            "editors": [
                {"name": "Key Validity Check", "total_seconds": 900, "percent": 50.0},
                {"name": "VS Code", "total_seconds": 1800, "percent": 50.0},
            ],
            "operating_systems": [{"name": "Windows", "total_seconds": 1800}],
        }
        parsed = parse_waka_metrics(all_time, week_noise_and_valid, synced_date="2026-11-28")
        self.assertEqual(parsed.all_time_hours, 1)
        self.assertEqual(parsed.all_time_minutes, 1)
        self.assertEqual([lang.name for lang in parsed.languages], ["C#", "Python"])
        self.assertAlmostEqual(parsed.languages[0].percent, 75.0, places=1)
        self.assertAlmostEqual(parsed.languages[1].percent, 25.0, places=1)

        self.assertEqual(len(parsed.projects), 1)
        proj_name = parsed.projects[0].name
        self.assertLessEqual(len(proj_name), 24)
        self.assertTrue(proj_name.endswith("…"))

        self.assertEqual(len(parsed.editors), 1)
        self.assertEqual(parsed.editors[0].name, "VS Code")
        self.assertAlmostEqual(parsed.editors[0].percent, 100.0, places=1)

        # 全噪音或全空输入：验证不抛 ZeroDivisionError 且安全回退空列表
        only_noise = {
            "languages": [{"name": "Other", "total_seconds": 5000}],
            "projects": [{"name": "Work", "total_seconds": 5000}],
            "editors": [{"name": "key-validity", "total_seconds": 100}],
            "operating_systems": [],
        }
        empty_metrics = parse_waka_metrics({"total_seconds": 0}, only_noise, synced_date="2026-11-28")
        self.assertEqual(empty_metrics.languages, [])
        self.assertEqual(empty_metrics.projects, [])
        self.assertEqual(empty_metrics.editors, [])
        self.assertEqual(empty_metrics.os_name, "Unknown")

    def test_truncate_label_wide_cjk_and_ascii(self) -> None:
        self.assertEqual(truncate_label("CasualtiesUnknown-SkinEd", 24), "CasualtiesUnknown-SkinEd")
        truncated_ascii = truncate_label("CasualtiesUnknown-SkinEditorExtra", 24)
        self.assertEqual(len(truncated_ascii), 24)
        self.assertTrue(truncated_ascii.endswith("…"))

        # 中文全角字符按 2 列宽计，防止超宽溢出卡片
        truncated_cjk = truncate_label("明日方舟终端皮肤编辑器超长仓库名称测试", 16)
        self.assertTrue(truncated_cjk.endswith("…"))
        self.assertLessEqual(len(truncated_cjk), 9)

    def test_isometric_grid_alignment_and_peak_month(self) -> None:
        # 2026-11-25 是周三 -> 在周日(0)..周六(6)坐标系中应落在 row=3
        partial_week = [[ContributionDay(date="2026-11-25", count=14, level="FOURTH_QUARTILE")]]
        grid = extract_isometric_grid(partial_week, cols=21)
        self.assertEqual(len(grid), 21)
        self.assertTrue(all(len(col) == 7 for col in grid))
        self.assertEqual(grid[-1][3], "lv4")
        self.assertEqual(grid[-1][0], "lv0")
        self.assertEqual(compute_half_year_peak(partial_week), "Nov Peak: 14 commits")

    def test_xml_special_characters_and_control_bytes_escaping(self) -> None:
        hostile_str = 'C# & C++ <Test> "Quote" \'Single\'\x07'
        rank = calculate_rank(
            commits=120, prs=12, issues=5, reviews=3, stars=45, followers=9
        )
        github = GitHubMetrics(
            username='user<&>"\'',
            commits_1y=120,
            total_contributions_1y=150,
            merged_prs=12,
            total_stars=45,
            peak_month_label='Nov <Peak> & "72" \'commits\'',
            isometric_grid=[["lv0"] * 7 for _ in range(21)],
            rank=rank,
        )
        waka = WakaMetrics(
            all_time_hours=88,
            all_time_minutes=15,
            editors=[
                EditorStat(name='VS <Code> & "1"', percent=80.0),
                EditorStat(name="Codex 'CLI' & 2", percent=20.0),
            ],
            os_name='Win <11> & "Pro"',
            os_percent=100.0,
            languages=[
                LanguageStat(name=hostile_str, total_seconds=3600, percent=100.0, time_text="1h 00m"),
            ],
            projects=[
                ProjectStat(name=hostile_str, total_seconds=3600, percent=100.0, time_text="1h 00m"),
            ],
            synced_date='2026-11-28<&>"',
        )
        svgs = render_all_svgs(
            ProfileMetrics(github=github, waka=waka),
            stack_lines=(hostile_str, "Alt <Line> & 'Quote' \"2\""),
        )
        self.assertEqual(set(svgs.keys()), set(EXPECTED_FILES))
        for name, content in svgs.items():
            root = ET.fromstring(content)
            self.assertTrue(root.tag.endswith("svg"), msg=f"Unexpected root tag in {name}")

        with self.assertRaises(ValueError):
            validate_svg_xml("<svg><unclosed></svg>", "broken.svg")

    def test_demo_cli_generates_all_six_valid_svgs_without_plain_slashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            exit_code = cli_main(["--demo", "--out-dir", tmp_dir])
            self.assertEqual(exit_code, 0)

            out_path = Path(tmp_dir)
            for filename in EXPECTED_FILES:
                svg_file = out_path / filename
                self.assertTrue(svg_file.is_file(), f"Missing output file: {filename}")
                raw_bytes = svg_file.read_bytes()
                self.assertGreater(len(raw_bytes), 500, f"Empty or truncated SVG: {filename}")
                self.assertFalse(
                    raw_bytes.startswith(b"\xef\xbb\xbf"),
                    f"UTF-8 BOM is forbidden: {filename}",
                )

                svg_text = raw_bytes.decode("utf-8")
                root = ET.fromstring(svg_text)
                self.assertTrue(root.tag.endswith("svg"))
                # 确保所有卡片标题已全面迁移为原生 <polygon> 矢量斜切刃标，不含废弃裸 `// ` 标题前缀
                self.assertNotIn("// ", svg_text, f"Deprecated plain '// ' found in {filename}")
                self.assertIn("<polygon", svg_text, f"Vector slash polygon missing in {filename}")

    def test_contributions_html_attribute_order_independent(self) -> None:
        sample_html = """
        <h2>188 contributions in the last year</h2>
        <table>
          <td data-level="3" class="ContributionCalendar-day" data-date="2026-11-25"></td>
          <td id="cell-2" data-date="2026-11-26" data-level="4"></td>
          <rect data-level='2' data-date='2026-11-27' />
        </table>
        """
        total_1y, days = parse_contributions_html(sample_html)
        self.assertEqual(total_1y, 188)
        self.assertEqual(days["2026-11-25"].level, "THIRD_QUARTILE")
        self.assertEqual(days["2026-11-26"].level, "FOURTH_QUARTILE")
        self.assertEqual(days["2026-11-27"].level, "SECOND_QUARTILE")

    def test_graphql_forbidden_degrades_to_level3_with_deduped_org_stars(self) -> None:
        class _FakeHTTPResponse:
            def __init__(self, body: str, status: int = 200) -> None:
                self.status = status
                self._raw = body.encode("utf-8")

            def read(self) -> bytes:
                return self._raw

            def __enter__(self) -> _FakeHTTPResponse:
                return self

            def __exit__(self, *_: object) -> None:
                return None

        seen_auth_headers: list[str | None] = []

        def _fake_urlopen(request: object, timeout: int = 30) -> _FakeHTTPResponse:
            req = request  # urllib.request.Request
            url = getattr(req, "full_url")
            auth = req.headers.get("Authorization")  # type: ignore[attr-defined]
            seen_auth_headers.append(auth)

            if url.endswith("/graphql"):
                err_payload = json.dumps({
                    "errors": [{"type": "FORBIDDEN", "message": "Resource not accessible by integration"}]
                }).encode("utf-8")
                raise urllib.error.HTTPError(url, 403, "Forbidden", hdrs=None, fp=io.BytesIO(err_payload))  # type: ignore[arg-type]

            if "/search/issues" in url:
                rate_err = b'{"message": "API rate limit exceeded"}'
                raise urllib.error.HTTPError(url, 403, "Rate Limit", hdrs=None, fp=io.BytesIO(rate_err))  # type: ignore[arg-type]

            # 模拟携带受限 token 访问 REST 报 403，剥离 token 重试后返回 200
            if auth == "Bearer restricted-actions-token":
                raise urllib.error.HTTPError(url, 403, "Bad token scope", hdrs=None, fp=io.BytesIO(b"{}"))  # type: ignore[arg-type]

            if url.endswith("/users/huanxin886"):
                return _FakeHTTPResponse(json.dumps({"login": "huanxin886", "followers": 25}))

            if "/users/huanxin886/repos" in url:
                return _FakeHTTPResponse(json.dumps([
                    {"full_name": "huanxin886/solo-repo", "stargazers_count": 15},
                    {"full_name": "HuanXinWork/shared-mod", "stargazers_count": 20},
                ]))

            if "/orgs/HuanXinWork/repos" in url:
                return _FakeHTTPResponse(json.dumps([
                    {"full_name": "huanxinwork/shared-mod", "stargazers_count": 20},
                    {"full_name": "HuanXinWork/arknights-skin", "stargazers_count": 50},
                ]))

            if url.endswith("/users/huanxin886/contributions"):
                html = """
                <h2>210 contributions in the last year</h2>
                <td data-level="4" data-date="2026-11-25"></td>
                """
                return _FakeHTTPResponse(html)

            raise AssertionError(f"Unexpected URL in test: {url}")

        with patch.dict(
            os.environ,
            {
                "GH_TOKEN": "restricted-actions-token",
                "METRICS_TOKEN": "should-not-win",
                "GITHUB_TOKEN": "also-lower-priority",
                "GITHUB_EXTRA_ORGS": "HuanXinWork",
            },
            clear=False,
        ), patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            metrics = fetch_github_metrics("huanxin886")

        # 确认优先读取了 GH_TOKEN
        self.assertIn("Bearer restricted-actions-token", seen_auth_headers)
        self.assertEqual(metrics.username, "huanxin886")
        self.assertEqual(metrics.total_contributions_1y, 210)
        self.assertEqual(metrics.merged_prs, 0)
        # 星数按 full_name 不区分大小写去重：15 + 20 + 50 = 85（未重复计入 shared-mod）
        self.assertEqual(metrics.total_stars, 85)
        self.assertEqual(metrics.isometric_grid[-1][3], "lv4")

    def test_level1_partial_or_scope_error_falls_back_to_level2_graphql(self) -> None:
        calls = 0

        def _fake_http_json(url: str, **kwargs: object) -> tuple[int, dict | list]:
            nonlocal calls
            if url.endswith("/graphql"):
                calls += 1
                if calls == 1:
                    return 200, {"errors": [{"type": "INSUFFICIENT_SCOPES", "message": "requires read:org"}]}
                return 200, {
                    "data": {
                        "user": {
                            "login": "huanxin886",
                            "followers": {"totalCount": 12},
                            "issues": {"totalCount": 4},
                            "pullRequests": {"totalCount": 9},
                            "contributionsCollection": {
                                "totalCommitContributions": 80,
                                "totalPullRequestContributions": 9,
                                "totalIssueContributions": 4,
                                "totalPullRequestReviewContributions": 2,
                                "contributionCalendar": {
                                    "totalContributions": 95,
                                    "weeks": [{"contributionDays": [
                                        {"date": "2026-11-25", "contributionCount": 6, "contributionLevel": "THIRD_QUARTILE"}
                                    ]}],
                                },
                            },
                            "repositories": {
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                                "nodes": [
                                    {"nameWithOwner": "huanxin886/personal", "stargazerCount": 10},
                                    {"nameWithOwner": "HuanXinWork/dup-repo", "stargazerCount": 30},
                                ],
                            },
                        }
                    }
                }
            if "/orgs/HuanXinWork/repos" in url:
                return 200, [
                    {"full_name": "HuanXinWork/dup-repo", "stargazers_count": 30},
                    {"full_name": "HuanXinWork/hidden-member-repo", "stargazers_count": 45},
                ]
            raise AssertionError(f"Unexpected URL: {url}")

        with patch("scripts.github_metrics.http_json", side_effect=_fake_http_json):
            gh = fetch_github_metrics("huanxin886", token="ghp_test", extra_orgs=("HuanXinWork",))

        self.assertEqual(calls, 2)
        self.assertEqual(gh.total_contributions_1y, 95)
        # 10 + 30 + 45 = 85（dup-repo 不重复累加）
        self.assertEqual(gh.total_stars, 85)
        self.assertEqual(gh.isometric_grid[-1][3], "lv3")

    def test_scramble_dissolve_frames_contain_no_hardcoded_phrase_leak(self) -> None:
        base_demo = render_all_svgs(
            ProfileMetrics(
                github=GitHubMetrics(
                    username="huanxin886",
                    commits_1y=10,
                    total_contributions_1y=10,
                    merged_prs=2,
                    total_stars=5,
                    peak_month_label="Nov Peak: 10 commits",
                    isometric_grid=[["lv0"] * 7 for _ in range(21)],
                    rank=calculate_rank(commits=10, prs=2, issues=1, reviews=0, stars=5, followers=1),
                ),
                waka=parse_waka_metrics({"total_seconds": 600}, {}, synced_date="2026-11-28"),
            ),
            stack_lines=("Rust · WebAssembly", "Kernel · eBPF"),
        )
        hero_svg = base_demo["hero-dark.svg"]
        self.assertNotIn("M░dd▓ng", hero_svg)
        self.assertNotIn("CL!", hero_svg)


if __name__ == "__main__":
    unittest.main()
