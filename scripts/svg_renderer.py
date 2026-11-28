#!/usr/bin/env python3
"""毛玻璃终端风 SVG 渲染器：产出 Dark / Light 双主题共 6 张矢量卡片并执行 XML 强校验。"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape as sax_escape

from scripts.fetch_metrics import (
    RING_CIRCUMFERENCE,
    GitHubMetrics,
    ProfileMetrics,
    WakaMetrics,
)

STACK_LINE_1 = "C# · TypeScript · Python · Modding & Tooling"
STACK_LINE_2 = "Game Modding · Skin Tools · Desktop & CLI"

# XML 1.0 禁止除 \t \n \r 以外的 C0 控制字符及 \x7f，渲染前必须剥离以防外部脏数据破坏解析。
_ILLEGAL_XML_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

LANGUAGE_COLORS: dict[str, tuple[str, str]] = {
    "c#": ("#2ea043", "#16a34a"),
    "python": ("#38bdf8", "#0284c7"),
    "typescript": ("#3b82f6", "#2563eb"),
    "javascript": ("#facc15", "#ca8a04"),
    "markdown": ("#a78bfa", "#7c3aed"),
    "rust": ("#fb923c", "#ea580c"),
    "go": ("#22d3ee", "#0891b2"),
    "c++": ("#f472b6", "#db2777"),
    "c": ("#60a5fa", "#2563eb"),
    "java": ("#f97316", "#ea580c"),
    "kotlin": ("#a855f7", "#7e22ce"),
    "vue": ("#34d399", "#059669"),
    "html": ("#f87171", "#dc2626"),
    "xml": ("#fb7185", "#e11d48"),
    "css": ("#c084fc", "#9333ea"),
    "scss": ("#f472b6", "#db2777"),
    "powershell": ("#60a5fa", "#2563eb"),
    "bash": ("#34d399", "#059669"),
    "shell": ("#34d399", "#059669"),
    "json": ("#2dd4bf", "#0d9488"),
    "yaml": ("#fbbf24", "#d97706"),
    "toml": ("#fb923c", "#ea580c"),
    "lua": ("#818cf8", "#4f46e5"),
    "hlsl": ("#22d3ee", "#0891b2"),
    "shaderlab": ("#22d3ee", "#0891b2"),
    "sql": ("#f472b6", "#db2777"),
}

FALLBACK_LANG_COLORS: tuple[tuple[str, str], ...] = (
    ("#22d3ee", "#0284c7"),
    ("#34d399", "#059669"),
    ("#a78bfa", "#7c3aed"),
    ("#fbbf24", "#d97706"),
)

CLI_KEYWORDS = ("cli", "vim", "nvim", "neovim", "terminal", "zsh", "bash", "powershell", "nano")

_CIPHER_SUB = str.maketrans({
    "a": "@", "e": "3", "i": "1", "o": "0", "s": "$",
    "t": "+", "y": "¥", "c": "¢", "l": "!", "E": "3",
    "I": "1", "O": "0", "S": "$", "A": "@",
})
_CORRUPT_SUB = str.maketrans({
    "a": "░", "e": "▓", "i": "1", "o": "▒", "u": "░",
    "s": "$", "t": "+", "n": "▓", "r": "#", "l": "!",
    "A": "░", "E": "▓", "I": "1", "O": "0", "S": "$",
})
_NOISE_TAIL_POOL = (
    "9@!▓▒░",
    "#@7▓▒░",
    "8K!▓▒░",
    "9@!#▓▒",
    "7F#K▓▒",
    " · 0x9▓",
    "+h0n#▓",
    "0n · M▓",
    "dd!n#▓",
    "1ng & ▓",
    " T00l▓",
    "l!ng▓",
    "g#",
)


def xml_escape(value: object) -> str:
    cleaned = _ILLEGAL_XML_CHARS_RE.sub("", str(value))
    return sax_escape(cleaned, {'"': "&quot;", "'": "&apos;"})


def validate_svg_xml(svg_text: str, filename: str) -> None:
    try:
        ET.fromstring(svg_text)
    except ET.ParseError as exc:
        raise ValueError(f"Generated invalid SVG XML for {filename}: {exc}") from exc


def _lang_color(name: str, is_dark: bool, index: int) -> str:
    pair = LANGUAGE_COLORS.get(name.strip().lower())
    if pair is None:
        pair = FALLBACK_LANG_COLORS[index % len(FALLBACK_LANG_COLORS)]
    return pair[0] if is_dark else pair[1]


def _build_scramble_animation(
    line1: str,
    line2: str,
    cursor_color: str,
) -> tuple[str, str]:
    """程序化生成 33 帧 CSS steps(1, end) 赛博乱码重组打字动画。

    必须在原始 Unicode 字符串上按字符切片，随后对各片段独立执行 xml_escape，
    否则会把 `&amp;` 等实体切碎导致整张 SVG XML 解析失败。
    """
    stops = [
        0.0, 1.2, 2.4, 3.6, 4.8, 6.0, 7.2, 8.4, 9.6, 10.8,
        12.0, 13.2, 14.4, 15.6, 16.8, 46.4, 47.6, 48.8, 50.0, 51.2,
        52.4, 53.6, 54.8, 56.0, 57.2, 58.4, 59.6, 60.8, 62.0, 63.2,
        64.4, 96.4, 98.2, 100.0,
    ]
    css_lines: list[str] = []
    for idx in range(33):
        t0, t1 = stops[idx], stops[idx + 1]
        if idx == 0:
            css_lines.append(
                f"      @keyframes k0  {{ 0% {{ opacity: 1; }} {t1:.1f}% {{ opacity: 0; }} 100% {{ opacity: 0; }} }}"
            )
        elif idx == 32:
            css_lines.append(
                f"      @keyframes k32 {{ 0% {{ opacity: 0; }} {t0:.1f}% {{ opacity: 1; }} 100% {{ opacity: 1; }} }}"
            )
        else:
            css_lines.append(
                f"      @keyframes k{idx:<2d} {{ 0% {{ opacity: 0; }} {t0:.1f}% {{ opacity: 1; }} {t1:.1f}% {{ opacity: 0; }} 100% {{ opacity: 0; }} }}"
            )
    class_bindings = " ".join(f".f{i} {{ animation-name: k{i}; }}" for i in range(33))
    css_lines.append(f"      {class_bindings}")

    def _decode_frames(target: str, steps_count: int) -> list[str]:
        frames: list[str] = []
        n = max(1, len(target))
        for step in range(1, steps_count + 1):
            if step == steps_count:
                prefix = target[:-2] if n > 2 else ""
                tail = target[-2:] if n > 2 else target
                frames.append(
                    f'{xml_escape(prefix)}<tspan class="gl">{xml_escape(tail)}█</tspan>'
                )
                continue
            reveal_end = max(1, round(n * step / (steps_count + 1)))
            glitch_end = min(n, reveal_end + 4)
            prefix = target[:reveal_end]
            glitch_raw = target[reveal_end:glitch_end].translate(_CIPHER_SUB) or "0x7F"
            noise = _NOISE_TAIL_POOL[(step - 1) % len(_NOISE_TAIL_POOL)]
            frames.append(
                f'{xml_escape(prefix)}<tspan class="gl">{xml_escape(glitch_raw)}</tspan>'
                f'<tspan class="dm">{xml_escape(noise)}</tspan>'
            )
        return frames

    def _dissolve_frame(target: str, *, heavy: bool) -> tuple[bool, str]:
        n = len(target)
        if heavy or n < 8:
            cut = max(1, min(5, n // 6 or 1))
            head_gl = target[:cut].translate(_CIPHER_SUB) or "0x7F"
            tail_dm = target[cut:cut + 24].translate(_CORRUPT_SUB) or "▓▒░#7K"
            return (
                False,
                f'<tspan class="gl">{xml_escape(head_gl)}</tspan>'
                f'<tspan class="dm">{xml_escape(tail_dm)}</tspan>',
            )
        c1 = max(1, n // 6)
        c2 = max(c1 + 1, n // 4)
        c3 = max(c2 + 1, (n * 5) // 11)
        c4 = min(n, c3 + 4)
        keep_head = xml_escape(target[:c1])
        gl_mid1 = xml_escape(target[c1:c2].translate(_CIPHER_SUB) or "0x9A")
        keep_mid = xml_escape(target[c2:c3])
        gl_mid2 = xml_escape(target[c3:c4].translate(_CIPHER_SUB) or "#7F!")
        corrupt_tail = xml_escape(target[c4:].translate(_CORRUPT_SUB) or "▓▒░")
        return (
            True,
            f'{keep_head}<tspan class="gl">{gl_mid1}</tspan>{keep_mid}'
            f'<tspan class="gl">{gl_mid2}</tspan><tspan class="dm">{corrupt_tail}</tspan>',
        )

    esc_cursor = xml_escape(cursor_color)
    seq: list[tuple[bool, str]] = []
    # f0: 初始乱码唤醒
    seq.append((False, '<tspan class="gl">0x7F#K</tspan><tspan class="dm">9@!▓▒</tspan>'))
    # f1..f13: 第一句渐进解码（13 帧）
    for body in _decode_frames(line1, 13):
        seq.append((True, body))
    # f14: 第一句完整停留 + 闪烁光标
    seq.append((True, f'{xml_escape(line1)}<tspan fill="{esc_cursor}" class="cursor">▋</tspan>'))
    # f15..f17: 信号崩解切换（3 帧，全部由 line1 动态派生，零固定词段）
    seq.append(_dissolve_frame(line1, heavy=False))
    seq.append(_dissolve_frame(line1[::-1], heavy=True))
    seq.append((False, '<tspan class="gl">0x3E#9</tspan><tspan class="dm">▓▒░@!7K$</tspan>'))
    # f18..f29: 第二句渐进解码（12 帧）
    for body in _decode_frames(line2, 12):
        seq.append((True, body))
    # f30: 第二句完整停留 + 闪烁光标
    seq.append((True, f'{xml_escape(line2)}<tspan fill="{esc_cursor}" class="cursor">▋</tspan>'))
    # f31..f32: 第二句崩解回环（2 帧，由 line2 动态派生）
    seq.append(_dissolve_frame(line2, heavy=True))
    seq.append((False, '<tspan class="gl">#9F!0x</tspan><tspan class="dm">7K@▓▒░</tspan>'))

    assert len(seq) == 33
    frame_nodes = []
    for idx, (use_tx, inner) in enumerate(seq):
        tx_attr = ' class="tx"' if use_tx else ""
        frame_nodes.append(f'      <g class="fr f{idx}"><text x="90" y="153"{tx_attr}>{inner}</text></g>')

    return "\n".join(css_lines), "\n".join(frame_nodes)


def render_hero_svg(
    github: GitHubMetrics,
    *,
    dark: bool,
    stack_lines: tuple[str, str] = (STACK_LINE_1, STACK_LINE_2),
) -> str:
    sfx = "" if dark else "L"
    if dark:
        p = {
            "bg0": "#0b0f17", "bg1": "#0f172a", "bg2": "#0b1120",
            "hud0": "#1e293b", "hud0_op": "0.58", "hud1": "#0f172a", "hud1_op": "0.72",
            "acc0": "#22d3ee", "acc1": "#34d399", "acc_op": "0.85",
            "slash0": "#22d3ee", "slash1": "#34d399", "slash1_op": "0.65",
            "glow_std": "30", "glow0": "#06b6d4", "glow0_op": "0.15", "glow1": "#10b981", "glow1_op": "0.14",
            "grid": "#94a3b8", "grid_op": "0.045",
            "gl": "#22d3ee", "dm": "#475569", "tx": "#e2e8f0",
            "bar_bg": "#161f30", "bar_op": "0.74", "bar_line": "#94a3b8", "bar_line_op": "0.14",
            "title_tx": "#94a3b8", "dot": "#34d399", "live_tx": "#cbd5e1",
            "prompt": "#22d3ee", "cmd": "#94a3b8",
            "name_tx": "#f8fafc",
            "tag_bg": "#22d3ee", "tag_bg_op": "0.12", "tag_st_op": "0.32", "tag_tx": "#67e8f9",
            "pill_bg": "#1e293b", "pill_op": "0.55", "pill_tx": "#cbd5e1",
            "hud_st": "#e2e8f0", "hud_st_op": "0.14",
            "hud_hdr": "#67e8f9", "dash": "#94a3b8", "dash_op": "0.14",
            "lbl": "#94a3b8", "val1": "#f1f5f9", "val2": "#34d399", "val3": "#67e8f9",
            "ring_bg": "#0b1120", "ring_bg_op": "0.55", "ring_track": "#334155",
            "rank_tx": "#f8fafc", "top_tx": "#34d399",
            "border": "#cbd5e1", "border_op": "0.16",
        }
    else:
        p = {
            "bg0": "#f8fafc", "bg1": "#f1f5f9", "bg2": "#eef2ff",
            "hud0": "#ffffff", "hud0_op": "0.88", "hud1": "#f8fafc", "hud1_op": "0.82",
            "acc0": "#0284c7", "acc1": "#10b981", "acc_op": "0.75",
            "slash0": "#0284c7", "slash1": "#10b981", "slash1_op": "0.70",
            "glow_std": "28", "glow0": "#38bdf8", "glow0_op": "0.16", "glow1": "#10b981", "glow1_op": "0.14",
            "grid": "#0f172a", "grid_op": "0.04",
            "gl": "#0284c7", "dm": "#94a3b8", "tx": "#0f172a",
            "bar_bg": "#e2e8f0", "bar_op": "0.70", "bar_line": "#0f172a", "bar_line_op": "0.09",
            "title_tx": "#475569", "dot": "#059669", "live_tx": "#334155",
            "prompt": "#0284c7", "cmd": "#64748b",
            "name_tx": "#0f172a",
            "tag_bg": "#0284c7", "tag_bg_op": "0.10", "tag_st_op": "0.30", "tag_tx": "#0369a1",
            "pill_bg": "#e2e8f0", "pill_op": "0.65", "pill_tx": "#334155",
            "hud_st": "#0f172a", "hud_st_op": "0.10",
            "hud_hdr": "#0284c7", "dash": "#0f172a", "dash_op": "0.10",
            "lbl": "#64748b", "val1": "#0f172a", "val2": "#059669", "val3": "#0284c7",
            "ring_bg": "#f1f5f9", "ring_bg_op": "1", "ring_track": "#cbd5e1",
            "rank_tx": "#0f172a", "top_tx": "#059669",
            "border": "#0f172a", "border_op": "0.12",
        }

    keyframes_css, frame_elements = _build_scramble_animation(
        stack_lines[0], stack_lines[1], p["prompt"]
    )
    circumference = f"{RING_CIRCUMFERENCE:.2f}"
    dashoffset = f"{github.rank.dashoffset:.2f}"
    top_pct = max(1, round(github.rank.percentile))
    esc_user = xml_escape(github.username)
    accent_end = "#34d399" if dark else "#059669"

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 178" width="840" height="178">
  <defs>
    <linearGradient id="bg{sfx}" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{p['bg0']}"/>
      <stop offset="55%" stop-color="{p['bg1']}"/>
      <stop offset="100%" stop-color="{p['bg2']}"/>
    </linearGradient>
    <linearGradient id="hudBg{sfx}" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="{p['hud0']}" stop-opacity="{p['hud0_op']}"/>
      <stop offset="100%" stop-color="{p['hud1']}" stop-opacity="{p['hud1_op']}"/>
    </linearGradient>
    <linearGradient id="accentLine{sfx}" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="{p['acc0']}" stop-opacity="0"/>
      <stop offset="35%" stop-color="{p['acc0']}" stop-opacity="{p['acc_op']}"/>
      <stop offset="70%" stop-color="{accent_end}" stop-opacity="{p['acc_op']}"/>
      <stop offset="100%" stop-color="{accent_end}" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="rankGrad{sfx}" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{p['acc0']}"/>
      <stop offset="100%" stop-color="{p['acc1']}"/>
    </linearGradient>
    <linearGradient id="quoteBar{sfx}" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="{p['acc0']}"/>
      <stop offset="100%" stop-color="{p['acc1']}"/>
    </linearGradient>
    <g id="slashes{sfx}">
      <polygon points="3,0 6,0 3,10 0,10" fill="{p['slash0']}"/>
      <polygon points="8.5,0 11.5,0 8.5,10 5.5,10" fill="{p['slash1']}" fill-opacity="{p['slash1_op']}"/>
    </g>
    <filter id="glow{sfx}" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="{p['glow_std']}"/>
    </filter>
    <pattern id="grid{sfx}" width="22" height="22" patternUnits="userSpaceOnUse">
      <path d="M 22 0 L 0 0 0 22" fill="none" stroke="{p['grid']}" stroke-opacity="{p['grid_op']}" stroke-width="1"/>
    </pattern>
    <clipPath id="cardClip{sfx}">
      <rect x="2" y="2" width="836" height="174" rx="12"/>
    </clipPath>
    <style>
      .mono {{ font-family: 'Cascadia Code', 'JetBrains Mono', 'Fira Code', Consolas, monospace; }}
      .sans {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei UI', 'PingFang SC', system-ui, sans-serif; }}
      .gl {{ fill: {p['gl']}; font-weight: 600; }}
      .dm {{ fill: {p['dm']}; }}
      .tx {{ fill: {p['tx']}; }}
      .fr {{ opacity: 0; animation-duration: 9.6s; animation-iteration-count: infinite; animation-timing-function: steps(1, end); }}
      @keyframes blink {{ 0%, 49% {{ opacity: 1; }} 50%, 100% {{ opacity: 0; }} }}
      @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.35; }} }}
      @keyframes ringFill {{ from {{ stroke-dashoffset: {circumference}; }} to {{ stroke-dashoffset: {dashoffset}; }} }}
      .cursor {{ animation: blink 1s infinite; }}
      .dot-live {{ animation: pulse 2.4s ease-in-out infinite; }}
      .rank-arc {{ stroke-dasharray: {circumference}; stroke-dashoffset: {dashoffset}; animation: ringFill 1.4s cubic-bezier(0.22, 1, 0.36, 1) forwards; }}
{keyframes_css}
    </style>
  </defs>

  <g clip-path="url(#cardClip{sfx})">
    <rect x="2" y="2" width="836" height="174" fill="url(#bg{sfx})"/>
    <rect x="2" y="2" width="836" height="174" fill="url(#grid{sfx})"/>
    <circle cx="145" cy="28" r="88" fill="{p['glow0']}" fill-opacity="{p['glow0_op']}" filter="url(#glow{sfx})"/>
    <circle cx="690" cy="150" r="100" fill="{p['glow1']}" fill-opacity="{p['glow1_op']}" filter="url(#glow{sfx})"/>

    <rect x="2" y="2" width="836" height="30" fill="{p['bar_bg']}" fill-opacity="{p['bar_op']}"/>
    <line x1="2" y1="32" x2="838" y2="32" stroke="{p['bar_line']}" stroke-opacity="{p['bar_line_op']}" stroke-width="1"/>
    <circle cx="20" cy="17" r="4.3" fill="#ef4444" fill-opacity="0.85"/>
    <circle cx="35" cy="17" r="4.3" fill="#f59e0b" fill-opacity="0.85"/>
    <circle cx="50" cy="17" r="4.3" fill="#10b981" fill-opacity="0.85"/>
    <text x="420" y="21" text-anchor="middle" class="mono" font-size="11" fill="{p['title_tx']}">{esc_user}@dream: ~/profile (zsh)</text>
    <circle cx="736" cy="17" r="3.5" fill="{p['dot']}" class="dot-live"/>
    <text x="746" y="21" class="mono" font-size="10.5" fill="{p['live_tx']}">ONLINE · UTC+8</text>

    <text x="26" y="57" class="mono" font-size="11.5" fill="{p['prompt']}">❯ <tspan fill="{p['cmd']}">whoami --profile</tspan></text>

    <text x="26" y="90" class="sans" font-size="25" font-weight="700" fill="{p['name_tx']}" letter-spacing="0.4">幻歆Hx</text>
    <rect x="122" y="73" width="104" height="21" rx="5" fill="{p['tag_bg']}" fill-opacity="{p['tag_bg_op']}" stroke="{p['tag_bg']}" stroke-opacity="{p['tag_st_op']}"/>
    <text x="174" y="87.5" text-anchor="middle" class="mono" font-size="11.2" fill="{p['tag_tx']}">@{esc_user}</text>

    <rect x="26" y="105" width="236" height="24" rx="5" fill="{p['pill_bg']}" fill-opacity="{p['pill_op']}"/>
    <rect x="26" y="105" width="3" height="24" rx="1.5" fill="url(#quoteBar{sfx})"/>
    <use href="#slashes{sfx}" x="36" y="112"/>
    <text x="54" y="121" class="sans" font-size="12.2" fill="{p['pill_tx']}" letter-spacing="0.3">你还沉浸在过往之中吗</text>

    <text x="26" y="153" class="mono" font-size="11.8" fill="{p['prompt']}">❯ <tspan fill="{p['cmd']}">stack:</tspan></text>

    <g class="mono" font-size="11.8">
{frame_elements}
    </g>

    <rect x="540" y="45" width="276" height="116" rx="10" fill="url(#hudBg{sfx})" stroke="{p['hud_st']}" stroke-opacity="{p['hud_st_op']}" stroke-width="1"/>
    <line x1="556" y1="45" x2="800" y2="45" stroke="url(#accentLine{sfx})" stroke-width="1.5"/>
    <use href="#slashes{sfx}" x="556" y="55"/>
    <text x="573" y="64.5" class="mono" font-size="10.5" font-weight="600" fill="{p['hud_hdr']}" letter-spacing="0.8">GITHUB RATING</text>
    <line x1="556" y1="73" x2="704" y2="73" stroke="{p['dash']}" stroke-opacity="{p['dash_op']}" stroke-dasharray="3 3"/>

    <text x="556" y="94" class="mono" font-size="10.8" fill="{p['lbl']}">COMMITS (1Y)</text>
    <text x="704" y="94" text-anchor="end" class="mono" font-size="11" font-weight="600" fill="{p['val1']}">{xml_escape(f"{github.commits_1y:,}")}</text>

    <text x="556" y="117" class="mono" font-size="10.8" fill="{p['lbl']}">MERGED PRs</text>
    <text x="704" y="117" text-anchor="end" class="mono" font-size="11" font-weight="600" fill="{p['val2']}">{xml_escape(f"{github.merged_prs:,}")}</text>

    <text x="556" y="140" class="mono" font-size="10.8" fill="{p['lbl']}">ORG STARS</text>
    <text x="704" y="140" text-anchor="end" class="mono" font-size="11" font-weight="600" fill="{p['val3']}">{xml_escape(f"{github.total_stars:,}")}</text>

    <circle cx="762" cy="104" r="33" fill="{p['ring_bg']}" fill-opacity="{p['ring_bg_op']}" stroke="{p['ring_track']}" stroke-width="5.2"/>
    <circle cx="762" cy="104" r="33" fill="none" stroke="url(#rankGrad{sfx})" stroke-width="5.2" stroke-linecap="round" transform="rotate(-90 762 104)" class="rank-arc"/>
    <text x="762" y="106" text-anchor="middle" class="mono" font-size="20" font-weight="700" fill="{p['rank_tx']}">{xml_escape(github.rank.level)}</text>
    <text x="762" y="120" text-anchor="middle" class="mono" font-size="8" fill="{p['top_tx']}">TOP {top_pct}%</text>
  </g>

  <rect x="2" y="2" width="836" height="174" rx="12" fill="none" stroke="{p['border']}" stroke-opacity="{p['border_op']}" stroke-width="1.2"/>
</svg>
'''


def render_waka_bento_svg(waka: WakaMetrics, *, dark: bool) -> str:
    sfx = "" if dark else "L"
    if dark:
        p = {
            "bg0": "#0b0f17", "bg1": "#111827",
            "tile0": "#1e293b", "tile0_op": "0.52", "tile1": "#0f172a", "tile1_op": "0.68",
            "slash0": "#22d3ee", "slash1": "#34d399", "slash1_op": "0.65",
            "glow_std": "34", "glow0": "#10b981", "glow0_op": "0.11", "glow1": "#06b6d4", "glow1_op": "0.12",
            "bar_bg": "#161f30", "bar_op": "0.72", "bar_line": "#94a3b8", "bar_line_op": "0.14",
            "prompt": "#22d3ee", "cmd": "#cbd5e1", "sync": "#64748b",
            "tile_st": "#cbd5e1", "tile_st_op": "0.13",
            "hdr": "#67e8f9", "sub": "#64748b",
            "big_tx": "#f8fafc", "unit_tx": "#94a3b8", "ver_tx": "#34d399",
            "div": "#94a3b8", "div_op": "0.14",
            "meta_lbl": "#94a3b8", "meta_val": "#e2e8f0",
            "lang_tx": "#f1f5f9", "lang_val": "#94a3b8",
            "track": "#334155", "track_op": "0.6",
            "proj_tx": "#f1f5f9", "proj_hi": "#67e8f9", "proj_lo": "#94a3b8",
            "proj_bars": ("#22d3ee", "#38bdf8", "#818cf8", "#a78bfa"),
            "border": "#cbd5e1", "border_op": "0.16",
        }
    else:
        p = {
            "bg0": "#f8fafc", "bg1": "#f1f5f9",
            "tile0": "#ffffff", "tile0_op": "0.88", "tile1": "#f8fafc", "tile1_op": "0.82",
            "slash0": "#0284c7", "slash1": "#10b981", "slash1_op": "0.70",
            "glow_std": "32", "glow0": "#34d399", "glow0_op": "0.14", "glow1": "#38bdf8", "glow1_op": "0.14",
            "bar_bg": "#e2e8f0", "bar_op": "0.68", "bar_line": "#0f172a", "bar_line_op": "0.09",
            "prompt": "#0284c7", "cmd": "#334155", "sync": "#64748b",
            "tile_st": "#0f172a", "tile_st_op": "0.09",
            "hdr": "#0284c7", "sub": "#64748b",
            "big_tx": "#0f172a", "unit_tx": "#64748b", "ver_tx": "#059669",
            "div": "#0f172a", "div_op": "0.09",
            "meta_lbl": "#64748b", "meta_val": "#0f172a",
            "lang_tx": "#0f172a", "lang_val": "#475569",
            "track": "#cbd5e1", "track_op": "0.7",
            "proj_tx": "#0f172a", "proj_hi": "#0284c7", "proj_lo": "#475569",
            "proj_bars": ("#0284c7", "#0ea5e9", "#6366f1", "#8b5cf6"),
            "border": "#0f172a", "border_op": "0.12",
        }

    ed1_val = (
        f"{waka.editors[0].name} · {waka.editors[0].percent:.1f}%"
        if len(waka.editors) >= 1
        else "No Data"
    )
    if len(waka.editors) >= 2:
        ed2_name_low = waka.editors[1].name.lower()
        ed2_label = "CLI" if any(k in ed2_name_low for k in CLI_KEYWORDS) else "TOOL"
        ed2_val = f"{waka.editors[1].name} · {waka.editors[1].percent:.1f}%"
    else:
        ed2_label = "CLI"
        ed2_val = "—"

    if waka.os_percent >= 99.95:
        os_val = f"{waka.os_name} · 100%"
    elif waka.os_percent > 0:
        os_val = f"{waka.os_name} · {waka.os_percent:.1f}%"
    else:
        os_val = waka.os_name

    # 组合光谱条：底槽兜底 + 按展示语言相对时长铺满 248px，尾段对齐 x=516 消除舍入缝隙。
    spectrum_rects = [
        f'      <rect x="268" y="82" width="248" height="7" fill="{p["track"]}" fill-opacity="{p["track_op"]}"/>'
    ]
    lang_rows: list[str] = []
    shown_langs = waka.languages[:3]
    shown_lang_secs = sum(item.total_seconds for item in shown_langs)

    if shown_langs and shown_lang_secs > 0:
        cursor_x = 268
        for idx, lang in enumerate(shown_langs):
            color = _lang_color(lang.name, dark, idx)
            if idx == len(shown_langs) - 1:
                seg_w = max(0, 516 - cursor_x)
            else:
                seg_w = max(4, round(248 * (lang.total_seconds / shown_lang_secs)))
                seg_w = min(seg_w, 516 - cursor_x)
            if seg_w > 0:
                spectrum_rects.append(
                    f'      <rect x="{cursor_x}" y="82" width="{seg_w}" height="7" fill="{color}"/>'
                )
                cursor_x += seg_w

            row_y = 117 + idx * 40
            bar_y = 125 + idx * 40
            bar_w = max(4, min(248, round(248 * lang.percent / 100.0)))
            lang_rows.append(
                f'    <circle cx="273" cy="{row_y - 4}" r="4" fill="{color}"/>\n'
                f'    <text x="283" y="{row_y}" class="mono" font-size="12" font-weight="600" fill="{p["lang_tx"]}">{xml_escape(lang.name)}</text>\n'
                f'    <text x="516" y="{row_y}" text-anchor="end" class="mono" font-size="11" fill="{p["lang_val"]}">{xml_escape(f"{lang.time_text} · {lang.percent:.1f}%")}</text>\n'
                f'    <rect x="268" y="{bar_y}" width="248" height="5" rx="2.5" fill="{p["track"]}" fill-opacity="{p["track_op"]}"/>\n'
                f'    <rect x="268" y="{bar_y}" width="{bar_w}" height="5" rx="2.5" fill="{color}"/>'
            )
    else:
        lang_rows.append(
            f'    <text x="392" y="156" text-anchor="middle" class="mono" font-size="11" fill="{p["sub"]}">No coding activity in last 7d</text>'
        )

    proj_rows: list[str] = []
    shown_projs = waka.projects[:4]
    if shown_projs:
        for idx, proj in enumerate(shown_projs):
            row_y = 97 + idx * 36
            bar_y = 104 + idx * 36
            bar_w = max(8, min(248, round(248 * proj.percent / 100.0)))
            bar_color = p["proj_bars"][idx % len(p["proj_bars"])]
            dur_color = p["proj_hi"] if idx < 2 else p["proj_lo"]
            proj_rows.append(
                f'    <text x="560" y="{row_y}" class="mono" font-size="11.2" fill="{p["proj_tx"]}">{xml_escape(proj.name)}</text>\n'
                f'    <text x="808" y="{row_y}" text-anchor="end" class="mono" font-size="10.8" fill="{dur_color}">{xml_escape(proj.time_text)}</text>\n'
                f'    <rect x="560" y="{bar_y}" width="248" height="4.5" rx="2.2" fill="{p["track"]}" fill-opacity="{p["track_op"]}"/>\n'
                f'    <rect x="560" y="{bar_y}" width="{bar_w}" height="4.5" rx="2.2" fill="{bar_color}"/>'
            )
    else:
        proj_rows.append(
            f'    <text x="684" y="156" text-anchor="middle" class="mono" font-size="11" fill="{p["sub"]}">No active workspace in last 7d</text>'
        )

    spectrum_block = "\n".join(spectrum_rects)
    lang_block = "\n\n".join(lang_rows)
    proj_block = "\n\n".join(proj_rows)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 252" width="840" height="252">
  <defs>
    <linearGradient id="bentoBg{sfx}" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{p['bg0']}"/>
      <stop offset="100%" stop-color="{p['bg1']}"/>
    </linearGradient>
    <linearGradient id="tileBg{sfx}" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="{p['tile0']}" stop-opacity="{p['tile0_op']}"/>
      <stop offset="100%" stop-color="{p['tile1']}" stop-opacity="{p['tile1_op']}"/>
    </linearGradient>
    <g id="slashes{sfx}">
      <polygon points="3,0 6,0 3,10 0,10" fill="{p['slash0']}"/>
      <polygon points="8.5,0 11.5,0 8.5,10 5.5,10" fill="{p['slash1']}" fill-opacity="{p['slash1_op']}"/>
    </g>
    <filter id="blurGlow{sfx}" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="{p['glow_std']}"/>
    </filter>
    <clipPath id="bentoClip{sfx}">
      <rect x="2" y="2" width="836" height="248" rx="14"/>
    </clipPath>
    <clipPath id="langBarClip{sfx}">
      <rect x="268" y="82" width="248" height="7" rx="3.5"/>
    </clipPath>
    <style>
      .mono {{ font-family: 'Cascadia Code', 'JetBrains Mono', 'Fira Code', Consolas, monospace; }}
    </style>
  </defs>

  <g clip-path="url(#bentoClip{sfx})">
    <rect x="2" y="2" width="836" height="248" fill="url(#bentoBg{sfx})"/>
    <circle cx="220" cy="220" r="110" fill="{p['glow0']}" fill-opacity="{p['glow0_op']}" filter="url(#blurGlow{sfx})"/>
    <circle cx="660" cy="50" r="110" fill="{p['glow1']}" fill-opacity="{p['glow1_op']}" filter="url(#blurGlow{sfx})"/>

    <rect x="2" y="2" width="836" height="32" fill="{p['bar_bg']}" fill-opacity="{p['bar_op']}"/>
    <line x1="2" y1="34" x2="838" y2="34" stroke="{p['bar_line']}" stroke-opacity="{p['bar_line_op']}"/>
    <text x="18" y="22" class="mono" font-size="11.5" fill="{p['prompt']}">❯ <tspan fill="{p['cmd']}">wakatime --bento --window=7d --exclude=Other,Image</tspan></text>
    <text x="822" y="22" text-anchor="end" class="mono" font-size="10.5" fill="{p['sync']}">SYNCED {xml_escape(waka.synced_date)} UTC</text>

    <rect x="16" y="46" width="224" height="190" rx="11" fill="url(#tileBg{sfx})" stroke="{p['tile_st']}" stroke-opacity="{p['tile_st_op']}"/>
    <use href="#slashes{sfx}" x="32" y="59.5"/>
    <text x="49" y="69" class="mono" font-size="10.5" font-weight="600" fill="{p['hdr']}" letter-spacing="0.6">ALL-TIME CODING</text>
    <text x="32" y="108" class="mono" font-size="31" font-weight="700" fill="{p['big_tx']}">{xml_escape(f"{waka.all_time_hours:,}")}<tspan font-size="13" font-weight="400" fill="{p['unit_tx']}"> hrs</tspan></text>
    <text x="32" y="126" class="mono" font-size="11" fill="{p['ver_tx']}">+{waka.all_time_minutes} mins verified via WakaTime</text>
    <line x1="32" y1="141" x2="224" y2="141" stroke="{p['div']}" stroke-opacity="{p['div_op']}"/>

    <text x="32" y="164" class="mono" font-size="11" fill="{p['meta_lbl']}">EDITOR</text>
    <text x="224" y="164" text-anchor="end" class="mono" font-size="11" fill="{p['meta_val']}">{xml_escape(ed1_val)}</text>

    <text x="32" y="188" class="mono" font-size="11" fill="{p['meta_lbl']}">{xml_escape(ed2_label)}</text>
    <text x="224" y="188" text-anchor="end" class="mono" font-size="11" fill="{p['meta_val']}">{xml_escape(ed2_val)}</text>

    <text x="32" y="212" class="mono" font-size="11" fill="{p['meta_lbl']}">SYSTEM</text>
    <text x="224" y="212" text-anchor="end" class="mono" font-size="11" fill="{p['meta_val']}">{xml_escape(os_val)}</text>

    <rect x="252" y="46" width="280" height="190" rx="11" fill="url(#tileBg{sfx})" stroke="{p['tile_st']}" stroke-opacity="{p['tile_st_op']}"/>
    <use href="#slashes{sfx}" x="268" y="59.5"/>
    <text x="285" y="69" class="mono" font-size="10.5" font-weight="600" fill="{p['hdr']}" letter-spacing="0.6">CORE LANGUAGES</text>
    <text x="516" y="69" text-anchor="end" class="mono" font-size="10" fill="{p['sub']}">noise-free</text>

    <g clip-path="url(#langBarClip{sfx})">
{spectrum_block}
    </g>

{lang_block}

    <rect x="544" y="46" width="280" height="190" rx="11" fill="url(#tileBg{sfx})" stroke="{p['tile_st']}" stroke-opacity="{p['tile_st_op']}"/>
    <use href="#slashes{sfx}" x="560" y="59.5"/>
    <text x="577" y="69" class="mono" font-size="10.5" font-weight="600" fill="{p['hdr']}" letter-spacing="0.6">ACTIVE WORKSPACES</text>
    <text x="808" y="69" text-anchor="end" class="mono" font-size="10" fill="{p['sub']}">7d focus</text>

{proj_block}
  </g>

  <rect x="2" y="2" width="836" height="248" rx="14" fill="none" stroke="{p['border']}" stroke-opacity="{p['border_op']}" stroke-width="1.2"/>
</svg>
'''


def render_contrib_3d_svg(github: GitHubMetrics, *, dark: bool) -> str:
    sfx = "" if dark else "L"
    if dark:
        p = {
            "bg0": "#0b0f17", "bg1": "#0f172a",
            "side0": "#1e293b", "side0_op": "0.52", "side1": "#0f172a", "side1_op": "0.70",
            "glow_std": "36", "glow_op": "0.13",
            "slash0": "#22d3ee", "slash1": "#34d399", "slash1_op": "0.65",
            "bar_bg": "#161f30", "bar_op": "0.72", "bar_line": "#94a3b8", "bar_line_op": "0.14",
            "prompt": "#22d3ee", "cmd": "#cbd5e1",
            "card_st": "#cbd5e1", "card_st_op": "0.13",
            "hdr": "#67e8f9", "big_num": "#34d399", "unit": "#94a3b8",
            "peak_tx": "#e2e8f0", "pr_tx": "#94a3b8",
            "div": "#94a3b8", "div_op": "0.14",
            "border": "#cbd5e1", "border_op": "0.16",
            "lv0": ("#161f30", "#0f172a", "#1e293b", ' stroke="#334155" stroke-opacity="0.45" stroke-width="0.5"'),
            "lv1": ("#0d4429", "#072b19", "#156d3f"),
            "lv2": ("#137547", "#0b4f2f", "#22a565"),
            "lv3": ("#10b981", "#057a55", "#34d399"),
            "lv4": ("#14b8a6", "#0d746b", "#5eead4"),
        }
    else:
        p = {
            "bg0": "#f8fafc", "bg1": "#f1f5f9",
            "side0": "#ffffff", "side0_op": "0.88", "side1": "#f8fafc", "side1_op": "0.82",
            "glow_std": "34", "glow_op": "0.14",
            "slash0": "#0284c7", "slash1": "#10b981", "slash1_op": "0.70",
            "bar_bg": "#e2e8f0", "bar_op": "0.68", "bar_line": "#0f172a", "bar_line_op": "0.09",
            "prompt": "#0284c7", "cmd": "#334155",
            "card_st": "#0f172a", "card_st_op": "0.09",
            "hdr": "#0284c7", "big_num": "#059669", "unit": "#64748b",
            "peak_tx": "#0f172a", "pr_tx": "#475569",
            "div": "#0f172a", "div_op": "0.09",
            "border": "#0f172a", "border_op": "0.12",
            "lv0": ("#cbd5e1", "#94a3b8", "#e2e8f0", ' stroke="#cbd5e1" stroke-width="0.5"'),
            "lv1": ("#86efac", "#4ade80", "#bbf7d0"),
            "lv2": ("#22c55e", "#16a34a", "#4ade80"),
            "lv3": ("#10b981", "#059669", "#34d399"),
            "lv4": ("#0d9488", "#0f766e", "#2dd4bf"),
        }

    # 等距网格必须严格按 col 0..20、row 0..6 顺序输出，满足画家算法前后遮挡偏序关系。
    grid = github.isometric_grid
    prism_rows: list[str] = []
    for col in range(21):
        col_data = grid[col] if col < len(grid) else ["lv0"] * 7
        cells: list[str] = []
        for row in range(7):
            lv = col_data[row] if row < len(col_data) else "lv0"
            if lv not in ("lv0", "lv1", "lv2", "lv3", "lv4"):
                lv = "lv0"
            x = 430 + (col - row) * 15
            y = 75.0 + (col + row) * 6.5
            cells.append(f'<use href="#{lv}" x="{x}" y="{y:.1f}"/>')
        prism_rows.append("    " + "".join(cells))
    prisms_block = "\n".join(prism_rows)

    badge_suffix = "Pull Shark" if github.merged_prs >= 2 else "Verified"
    pr_line = f"Merged PRs: {github.merged_prs:,} · {badge_suffix}"

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 264" width="840" height="264">
  <defs>
    <linearGradient id="isoBg{sfx}" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{p['bg0']}"/>
      <stop offset="100%" stop-color="{p['bg1']}"/>
    </linearGradient>
    <linearGradient id="sideBg{sfx}" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="{p['side0']}" stop-opacity="{p['side0_op']}"/>
      <stop offset="100%" stop-color="{p['side1']}" stop-opacity="{p['side1_op']}"/>
    </linearGradient>
    <filter id="isoGlow{sfx}" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="{p['glow_std']}"/>
    </filter>
    <clipPath id="isoClip{sfx}">
      <rect x="2" y="2" width="836" height="260" rx="14"/>
    </clipPath>

    <g id="lv0">
      <polygon points="-12.5,-2 0,3.8 0,5.8 -12.5,0" fill="{p['lv0'][0]}"/>
      <polygon points="0,3.8 12.5,-2 12.5,0 0,5.8" fill="{p['lv0'][1]}"/>
      <polygon points="0,-7.8 12.5,-2 0,3.8 -12.5,-2" fill="{p['lv0'][2]}"{p['lv0'][3]}/>
    </g>
    <g id="lv1">
      <polygon points="-12.5,-9 0,-3.2 0,5.8 -12.5,0" fill="{p['lv1'][0]}"/>
      <polygon points="0,-3.2 12.5,-9 12.5,0 0,5.8" fill="{p['lv1'][1]}"/>
      <polygon points="0,-14.8 12.5,-9 0,-3.2 -12.5,-9" fill="{p['lv1'][2]}"/>
    </g>
    <g id="lv2">
      <polygon points="-12.5,-17 0,-11.2 0,5.8 -12.5,0" fill="{p['lv2'][0]}"/>
      <polygon points="0,-11.2 12.5,-17 12.5,0 0,5.8" fill="{p['lv2'][1]}"/>
      <polygon points="0,-22.8 12.5,-17 0,-11.2 -12.5,-17" fill="{p['lv2'][2]}"/>
    </g>
    <g id="lv3">
      <polygon points="-12.5,-26 0,-20.2 0,5.8 -12.5,0" fill="{p['lv3'][0]}"/>
      <polygon points="0,-20.2 12.5,-26 12.5,0 0,5.8" fill="{p['lv3'][1]}"/>
      <polygon points="0,-31.8 12.5,-26 0,-20.2 -12.5,-26" fill="{p['lv3'][2]}"/>
    </g>
    <g id="lv4">
      <polygon points="-12.5,-36 0,-30.2 0,5.8 -12.5,0" fill="{p['lv4'][0]}"/>
      <polygon points="0,-30.2 12.5,-36 12.5,0 0,5.8" fill="{p['lv4'][1]}"/>
      <polygon points="0,-41.8 12.5,-36 0,-30.2 -12.5,-36" fill="{p['lv4'][2]}"/>
    </g>

    <g id="slashes{sfx}">
      <polygon points="3,0 6,0 3,10 0,10" fill="{p['slash0']}"/>
      <polygon points="8.5,0 11.5,0 8.5,10 5.5,10" fill="{p['slash1']}" fill-opacity="{p['slash1_op']}"/>
    </g>
    <style>
      .mono {{ font-family: 'Cascadia Code', 'JetBrains Mono', 'Fira Code', Consolas, monospace; }}
    </style>
  </defs>

  <g clip-path="url(#isoClip{sfx})">
    <rect x="2" y="2" width="836" height="260" fill="url(#isoBg{sfx})"/>
    <circle cx="610" cy="155" r="135" fill="#10b981" fill-opacity="{p['glow_op']}" filter="url(#isoGlow{sfx})"/>

    <rect x="2" y="2" width="836" height="32" fill="{p['bar_bg']}" fill-opacity="{p['bar_op']}"/>
    <line x1="2" y1="34" x2="838" y2="34" stroke="{p['bar_line']}" stroke-opacity="{p['bar_line_op']}"/>
    <text x="18" y="22" class="mono" font-size="11.5" fill="{p['prompt']}">❯ <tspan fill="{p['cmd']}">git log --isometric --duration=half-year</tspan></text>
    <text x="822" y="22" text-anchor="end" class="mono" font-size="10.5" fill="#64748b">2.5D CONTRIBUTION TERRAIN</text>

    <rect x="16" y="48" width="236" height="198" rx="11" fill="url(#sideBg{sfx})" stroke="{p['card_st']}" stroke-opacity="{p['card_st_op']}"/>
    <use href="#slashes{sfx}" x="32" y="62.5"/>
    <text x="49" y="72" class="mono" font-size="10.5" font-weight="600" fill="{p['hdr']}" letter-spacing="0.6">COMMIT MATRIX</text>
    <text x="32" y="114" class="mono" font-size="34" font-weight="700" fill="{p['big_num']}">{xml_escape(f"{github.total_contributions_1y:,}")}<tspan font-size="11.5" font-weight="400" fill="{p['unit']}"> contribs / 1Y</tspan></text>
    <text x="32" y="136" class="mono" font-size="11" fill="{p['peak_tx']}">{xml_escape(github.peak_month_label)}</text>
    <text x="32" y="156" class="mono" font-size="11" fill="{p['pr_tx']}">{xml_escape(pr_line)}</text>
    <line x1="32" y1="176" x2="236" y2="176" stroke="{p['div']}" stroke-opacity="{p['div_op']}"/>
    <text x="32" y="198" class="mono" font-size="10" fill="#64748b">INTENSITY SCALE</text>
    <text x="32" y="226" class="mono" font-size="10" fill="#64748b">LESS</text>
    <g transform="translate(76, 224) scale(0.55)"><use href="#lv0"/></g>
    <g transform="translate(98, 224) scale(0.55)"><use href="#lv1"/></g>
    <g transform="translate(120, 224) scale(0.55)"><use href="#lv2"/></g>
    <g transform="translate(142, 224) scale(0.55)"><use href="#lv3"/></g>
    <g transform="translate(164, 224) scale(0.55)"><use href="#lv4"/></g>
    <text x="184" y="226" class="mono" font-size="10" fill="#64748b">MORE</text>

{prisms_block}
  </g>

  <rect x="2" y="2" width="836" height="260" rx="14" fill="none" stroke="{p['border']}" stroke-opacity="{p['border_op']}" stroke-width="1.2"/>
</svg>
'''


def render_all_svgs(
    metrics: ProfileMetrics,
    *,
    stack_lines: tuple[str, str] = (STACK_LINE_1, STACK_LINE_2),
) -> dict[str, str]:
    outputs = {
        "hero-dark.svg": render_hero_svg(metrics.github, dark=True, stack_lines=stack_lines),
        "hero-light.svg": render_hero_svg(metrics.github, dark=False, stack_lines=stack_lines),
        "waka-bento-dark.svg": render_waka_bento_svg(metrics.waka, dark=True),
        "waka-bento-light.svg": render_waka_bento_svg(metrics.waka, dark=False),
        "contrib-3d-dark.svg": render_contrib_3d_svg(metrics.github, dark=True),
        "contrib-3d-light.svg": render_contrib_3d_svg(metrics.github, dark=False),
    }
    for filename, svg_content in outputs.items():
        validate_svg_xml(svg_content, filename)
    return outputs


def write_all_svgs(
    metrics: ProfileMetrics,
    out_dir: str | Path,
    *,
    stack_lines: tuple[str, str] = (STACK_LINE_1, STACK_LINE_2),
) -> list[Path]:
    rendered = render_all_svgs(metrics, stack_lines=stack_lines)
    target_dir = Path(out_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for filename, content in rendered.items():
        dest = target_dir / filename
        dest.write_text(content, encoding="utf-8", newline="\n")
        written.append(dest)
    return written
