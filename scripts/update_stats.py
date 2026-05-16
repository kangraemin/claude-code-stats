#!/usr/bin/env python3
"""
update_stats.py — Claude Code 사용량 통계 + SVG 카드 자동 생성 (dark + light)

매일 cron으로 실행:
  1. ~/.claude/projects/*.jsonl 전체 파싱
  2. 통계 계산 (총 비용/토큰/응답수, 일별, 모델별)
  3. SVG 생성 (각 6개: dark/light × stats/heatmap/daily-cost)
  4. data/stats.json 갱신
  5. README.md 마커 사이 자동 갱신
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta, date
from collections import defaultdict
import statistics

PRICING = {
    "claude-opus-4-7": (15.0, 75.0), "claude-opus-4-6": (15.0, 75.0),
    "claude-opus-4-5": (15.0, 75.0), "claude-opus-4": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0), "claude-sonnet-4-5": (3.0, 15.0),
    "claude-sonnet-4": (3.0, 15.0), "claude-haiku-4-5": (1.0, 5.0),
    "claude-haiku-4": (1.0, 5.0), "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3-5-haiku": (0.8, 4.0), "claude-3-opus": (15.0, 75.0),
}

# 테마 색 (GitHub 스타일)
THEMES = {
    "dark": {
        "bg": "#0d1117", "bg_card": "#161b22", "border": "#30363d",
        "text": "#c9d1d9", "text_muted": "#8b949e",
        "accent": "#58a6ff", "green": "#7ee787", "orange": "#f78166",
        "purple": "#d2a8ff", "yellow": "#f2cc60",
        "heat_0": "#161b22", "heat_1": "#0e4429", "heat_2": "#006d32",
        "heat_3": "#26a641", "heat_4": "#39d353", "grid": "#21262d",
    },
    "light": {
        "bg": "#ffffff", "bg_card": "#f6f8fa", "border": "#d0d7de",
        "text": "#1f2328", "text_muted": "#656d76",
        "accent": "#0969da", "green": "#1a7f37", "orange": "#cf222e",
        "purple": "#8250df", "yellow": "#9a6700",
        "heat_0": "#ebedf0", "heat_1": "#9be9a8", "heat_2": "#40c463",
        "heat_3": "#30a14e", "heat_4": "#216e39", "grid": "#eaeef2",
    },
}


def get_pricing(model: str):
    if not model: return (3.0, 15.0)
    m = model.lower()
    for k, v in PRICING.items():
        if k in m: return v
    return (3.0, 15.0)


def parse_all_logs():
    base = Path.home() / ".claude" / "projects"
    daily = defaultdict(lambda: {"cost": 0.0, "msgs": 0, "input": 0, "cache_c": 0, "cache_r": 0, "output": 0})
    by_model = defaultdict(lambda: {"cost": 0.0, "msgs": 0, "tokens": 0})

    for proj_dir in base.iterdir():
        if not proj_dir.is_dir(): continue
        for jsonl in proj_dir.rglob("*.jsonl"):
            try:
                with open(jsonl) as f:
                    for line in f:
                        try:
                            obj = json.loads(line)
                            if obj.get("type") != "assistant": continue
                            msg = obj.get("message", {})
                            usage = msg.get("usage", {})
                            if not usage: continue
                            ts = obj.get("timestamp", "")[:10]
                            if not ts: continue
                            model = msg.get("model", "unknown")
                            ip, op = get_pricing(model)
                            inp = usage.get("input_tokens", 0)
                            cc = usage.get("cache_creation_input_tokens", 0)
                            cr = usage.get("cache_read_input_tokens", 0)
                            out = usage.get("output_tokens", 0)
                            cost = (inp * ip + cc * ip * 1.25 + cr * ip * 0.1 + out * op) / 1_000_000

                            daily[ts]["cost"] += cost
                            daily[ts]["msgs"] += 1
                            daily[ts]["input"] += inp
                            daily[ts]["cache_c"] += cc
                            daily[ts]["cache_r"] += cr
                            daily[ts]["output"] += out

                            by_model[model]["cost"] += cost
                            by_model[model]["msgs"] += 1
                            by_model[model]["tokens"] += inp + cc + cr + out
                        except: pass
            except: pass

    return daily, by_model


def compute_summary(daily):
    days_sorted = sorted(daily.keys())
    if not days_sorted: return {}
    costs = [daily[d]["cost"] for d in days_sorted]
    msgs = [daily[d]["msgs"] for d in days_sorted]
    tokens = [daily[d]["input"] + daily[d]["cache_c"] + daily[d]["cache_r"] + daily[d]["output"] for d in days_sorted]
    heaviest_day = max(days_sorted, key=lambda d: daily[d]["cost"])
    return {
        "first_day": days_sorted[0], "last_day": days_sorted[-1],
        "total_days": len(days_sorted),
        "total_cost": sum(costs), "total_msgs": sum(msgs), "total_tokens": sum(tokens),
        "avg_cost": statistics.mean(costs), "median_cost": statistics.median(costs),
        "max_cost": max(costs), "heaviest_day": heaviest_day,
        "max_msgs": max(msgs), "max_tokens": max(tokens),
        "avg_msgs": statistics.mean(msgs), "avg_tokens": statistics.mean(tokens),
    }


# ───────────────────────────────────────────────────────
# SVG: Stats Card (애니메이션 + 그라데이션 + 스파크라인)
# ───────────────────────────────────────────────────────
def svg_stats_card(summary, daily, by_model, theme="dark"):
    if not summary: return ""
    t = THEMES[theme]
    w, h = 540, 340
    card_radius = 8

    days_sorted = sorted(daily.keys())
    costs = [daily[d]["cost"] for d in days_sorted]
    n = len(costs)

    # 스파크라인
    spark_w, spark_h = 270, 40
    spark_x = w - spark_w - 22
    spark_y = h - spark_h - 28
    max_c = max(costs) if costs else 1
    if n > 1:
        pts = " ".join(f"{spark_x + i / (n-1) * spark_w:.1f},{spark_y + spark_h - costs[i] / max_c * spark_h:.1f}" for i in range(n))
        area_pts = f"{spark_x:.1f},{spark_y + spark_h} " + pts + f" {spark_x + spark_w:.1f},{spark_y + spark_h}"
    else:
        pts = ""; area_pts = ""

    # 본전 배수 (Max $200 가정)
    period_days = max((datetime.strptime(summary["last_day"], "%Y-%m-%d").date() - datetime.strptime(summary["first_day"], "%Y-%m-%d").date()).days, 1)
    monthly_cost = summary["total_cost"] / max(period_days / 30, 1)
    rank_label, rank_color = "Heavy User 🔥", t["orange"]
    if monthly_cost > 5000:
        rank_label, rank_color = "Top 1% 🚀", t["purple"]
    elif monthly_cost > 1000:
        rank_label, rank_color = "Power User ⚡", t["accent"]

    avg_tokens = summary["total_tokens"] / summary["total_days"]

    svg = f'''<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{t['accent']}" stop-opacity="0.06"/>
      <stop offset="100%" stop-color="{t['green']}" stop-opacity="0.02"/>
    </linearGradient>
    <linearGradient id="costGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="{t['green']}"/>
      <stop offset="100%" stop-color="{t['accent']}"/>
    </linearGradient>
    <linearGradient id="sparkGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="{t['accent']}" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="{t['accent']}" stop-opacity="0"/>
    </linearGradient>
  </defs>

  <rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="{card_radius}" fill="{t['bg']}" stroke="{t['border']}" stroke-width="1"/>
  <rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="{card_radius}" fill="url(#bgGrad)"/>

  <!-- Header -->
  <text x="22" y="34" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="17" font-weight="700" fill="{t['accent']}">🤖 Claude Code Usage</text>
  <text x="22" y="52" font-family="-apple-system,sans-serif" font-size="11" fill="{t['text_muted']}">{summary['first_day']} → {summary['last_day']} · {summary['total_days']} active days</text>

  <!-- Rank 배지 -->
  <rect x="{w - 132}" y="20" width="110" height="22" rx="11" fill="{rank_color}" fill-opacity="0.15" stroke="{rank_color}" stroke-width="0.8"/>
  <text x="{w - 77}" y="35" font-family="-apple-system,sans-serif" font-size="11" font-weight="600" fill="{rank_color}" text-anchor="middle">{rank_label}</text>

  <!-- Total Cost (메인 강조) -->
  <text x="22" y="86" font-family="-apple-system,sans-serif" font-size="10" fill="{t['text_muted']}" letter-spacing="0.8">TOTAL COST (정가 기준 추정)</text>
  <text x="22" y="120" font-family="-apple-system,sans-serif" font-size="32" font-weight="800" fill="url(#costGrad)">${summary['total_cost']:,.0f}</text>
  <text x="22" y="138" font-family="-apple-system,sans-serif" font-size="10" fill="{t['text_muted']}">≈ {round(summary['total_cost'] * 1400):,}원</text>

  <!-- 2x3 그리드 통계 -->
  <g font-family="-apple-system,sans-serif">
    <!-- Row 1 -->
    <text x="22" y="172" font-size="10" fill="{t['text_muted']}" letter-spacing="0.5">📊 AVG / DAY</text>
    <text x="22" y="194" font-size="18" font-weight="700" fill="{t['text']}">${summary['avg_cost']:,.0f}</text>

    <text x="200" y="172" font-size="10" fill="{t['text_muted']}" letter-spacing="0.5">🔥 TOTAL TOKENS</text>
    <text x="200" y="194" font-size="18" font-weight="700" fill="{t['accent']}">{summary['total_tokens']/1e9:.2f}B</text>

    <text x="378" y="172" font-size="10" fill="{t['text_muted']}" letter-spacing="0.5">📦 AVG TOKENS/DAY</text>
    <text x="378" y="194" font-size="18" font-weight="700" fill="{t['text']}">{avg_tokens/1e6:.0f}M</text>

    <!-- Row 2 -->
    <text x="22" y="226" font-size="10" fill="{t['text_muted']}" letter-spacing="0.5">💬 RESPONSES</text>
    <text x="22" y="248" font-size="18" font-weight="700" fill="{t['text']}">{summary['total_msgs']:,}</text>

    <text x="200" y="226" font-size="10" fill="{t['text_muted']}" letter-spacing="0.5">📅 AVG MSGS/DAY</text>
    <text x="200" y="248" font-size="18" font-weight="700" fill="{t['text']}">{summary['avg_msgs']:,.0f}</text>

    <text x="378" y="226" font-size="10" fill="{t['text_muted']}" letter-spacing="0.5">🏆 BEST DAY</text>
    <text x="378" y="248" font-size="18" font-weight="700" fill="{t['orange']}">${summary['max_cost']:,.0f}</text>
  </g>

  <!-- 스파크라인 -->
  <text x="22" y="{spark_y - 8}" font-family="-apple-system,sans-serif" font-size="10" fill="{t['text_muted']}" letter-spacing="0.5">📈 DAILY COST TREND</text>
  <polygon points="{area_pts}" fill="url(#sparkGrad)"/>
  <polyline points="{pts}" fill="none" stroke="{t['accent']}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>

  <!-- Footer -->
  <text x="{w - 22}" y="{h - 8}" font-family="-apple-system,sans-serif" font-size="9" fill="{t['text_muted']}" text-anchor="end">Updated: {datetime.now().strftime("%Y-%m-%d %H:%M KST")}</text>
</svg>'''
    return svg


# ───────────────────────────────────────────────────────
# SVG: Heatmap (1년 잔디)
# ───────────────────────────────────────────────────────
def svg_heatmap(daily, theme="dark"):
    if not daily: return ""
    t = THEMES[theme]
    today = date.today()
    end_wd_sun0 = (today.weekday() + 1) % 7
    last_sat = today + timedelta(days=(6 - end_wd_sun0))
    start = last_sat - timedelta(days=52 * 7 + 6)

    days_with_data = {d: daily[d] for d in daily}
    max_cost = max((v["cost"] for v in days_with_data.values()), default=1)

    def color(cost):
        if cost == 0: return t["heat_0"]
        ratio = cost / max_cost if max_cost > 0 else 0
        if ratio < 0.10: return t["heat_1"]
        if ratio < 0.30: return t["heat_2"]
        if ratio < 0.60: return t["heat_3"]
        return t["heat_4"]

    cell = 12; gap = 3; col_width = cell + gap
    n_cols = 53
    label_w = 32; label_h = 22; pad = 16; legend_h = 28
    w = label_w + n_cols * col_width + pad
    h = label_h + 7 * col_width + legend_h + pad

    svg = [
        f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">',
        f'  <rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="6" fill="{t["bg"]}" stroke="{t["border"]}"/>',
    ]

    weekday_labels = {1: "Mon", 3: "Wed", 5: "Fri"}
    for wd, lbl in weekday_labels.items():
        y = label_h + wd * col_width + cell - 2
        svg.append(f'  <text x="4" y="{y}" font-family="-apple-system,sans-serif" font-size="9" fill="{t["text_muted"]}">{lbl}</text>')

    cur = start
    col = 0
    last_month_drawn = None
    cell_id = 0
    while col < n_cols:
        wd_sun0 = (cur.weekday() + 1) % 7
        if wd_sun0 != 0:
            cur += timedelta(days=1)
            continue
        for offset in range(7):
            d = cur + timedelta(days=offset)
            if d > today: break
            d_str = d.strftime("%Y-%m-%d")
            cost = days_with_data.get(d_str, {}).get("cost", 0)
            x = label_w + col * col_width
            y = label_h + offset * col_width
            c = color(cost)
            tooltip = f'{d_str}: ${cost:,.0f}' if cost > 0 else f'{d_str}'
            svg.append(f'  <rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{c}"><title>{tooltip}</title></rect>')
            cell_id += 1

        if cur.month != last_month_drawn:
            month_lbl = cur.strftime("%b")
            mx = label_w + col * col_width
            svg.append(f'  <text x="{mx}" y="14" font-family="-apple-system,sans-serif" font-size="9" fill="{t["text_muted"]}">{month_lbl}</text>')
            last_month_drawn = cur.month

        cur += timedelta(days=7)
        col += 1

    # 범례 — 셀 아래 별도 행에 배치 (우측 정렬, 안전한 width 보장)
    legend_baseline = label_h + 7 * col_width + 18
    swatch_size = 10
    swatch_gap = 4
    swatches_total_w = 5 * swatch_size + 4 * swatch_gap
    less_text_w = 26  # "Less" 글자 폭 추정
    more_text_w = 30  # "More" 글자 폭 추정
    legend_total_w = less_text_w + 6 + swatches_total_w + 6 + more_text_w
    legend_start_x = w - pad - legend_total_w  # 우측 정렬 (안전 마진)

    svg.append(f'  <text x="{legend_start_x}" y="{legend_baseline}" font-family="-apple-system,sans-serif" font-size="10" fill="{t["text_muted"]}">Less</text>')
    sx = legend_start_x + less_text_w + 6
    for i, c in enumerate([t["heat_0"], t["heat_1"], t["heat_2"], t["heat_3"], t["heat_4"]]):
        svg.append(f'  <rect x="{sx + i*(swatch_size+swatch_gap)}" y="{legend_baseline - 9}" width="{swatch_size}" height="{swatch_size}" rx="2" fill="{c}"/>')
    text_x = sx + swatches_total_w + 6
    svg.append(f'  <text x="{text_x}" y="{legend_baseline}" font-family="-apple-system,sans-serif" font-size="10" fill="{t["text_muted"]}">More</text>')

    svg.append('</svg>')
    return "\n".join(svg)


# ───────────────────────────────────────────────────────
# SVG: Daily Cost Line Chart (애니메이션)
# ───────────────────────────────────────────────────────
def svg_daily_cost(daily, theme="dark"):
    if not daily: return ""
    t = THEMES[theme]
    days_with_data = sorted(daily.keys())
    if len(days_with_data) < 2: return ""

    first = datetime.strptime(days_with_data[0], "%Y-%m-%d").date()
    last = datetime.strptime(days_with_data[-1], "%Y-%m-%d").date()
    all_days = []
    cur = first
    while cur <= last:
        all_days.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    costs = [daily.get(d, {}).get("cost", 0) for d in all_days]
    n = len(costs)

    w, h = 720, 240
    pad_l, pad_r, pad_t, pad_b = 55, 20, 30, 40
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b
    max_c = max(costs) if max(costs) > 0 else 1

    def xpos(i):
        return pad_l + (i / (n - 1)) * plot_w
    def ypos(c):
        return pad_t + plot_h - (c / max_c) * plot_h

    svg = [
        f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">',
        f'  <defs>',
        f'    <linearGradient id="lineFill" x1="0%" y1="0%" x2="0%" y2="100%">',
        f'      <stop offset="0%" stop-color="{t["accent"]}" stop-opacity="0.4"/>',
        f'      <stop offset="100%" stop-color="{t["accent"]}" stop-opacity="0"/>',
        f'    </linearGradient>',
        f'  </defs>',
        f'  <rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="6" fill="{t["bg"]}" stroke="{t["border"]}"/>',
        f'  <text x="{w//2}" y="20" font-family="-apple-system,sans-serif" font-size="13" font-weight="600" fill="{t["text"]}" text-anchor="middle">📈 Daily Cost (USD)</text>',
    ]

    for i in range(5):
        v = max_c * (4 - i) / 4
        y = pad_t + plot_h * i / 4
        svg.append(f'  <line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" stroke="{t["grid"]}" stroke-width="0.5"/>')
        svg.append(f'  <text x="{pad_l - 5}" y="{y+3:.1f}" font-family="-apple-system,sans-serif" font-size="10" fill="{t["text_muted"]}" text-anchor="end">${v:,.0f}</text>')

    months_shown = set()
    for i, d in enumerate(all_days):
        m = d[:7]
        if m not in months_shown:
            months_shown.add(m)
            x = xpos(i)
            lbl = d[5:7] + "월"
            svg.append(f'  <text x="{x:.1f}" y="{h-15}" font-family="-apple-system,sans-serif" font-size="10" fill="{t["text_muted"]}" text-anchor="middle">{lbl}</text>')

    points = [f"{xpos(i):.1f},{ypos(c):.1f}" for i, c in enumerate(costs)]
    area = f"M{pad_l:.1f},{(pad_t + plot_h):.1f} L " + " L ".join(points) + f" L {(w-pad_r):.1f},{(pad_t + plot_h):.1f} Z"
    svg.append(f'  <path d="{area}" fill="url(#lineFill)"/>')

    line_path = "M " + " L ".join(points)
    svg.append(f'  <path d="{line_path}" stroke="{t["accent"]}" stroke-width="2" fill="none" stroke-linejoin="round" stroke-linecap="round"/>')

    max_i = costs.index(max(costs))
    svg.append(f'  <circle cx="{xpos(max_i):.1f}" cy="{ypos(costs[max_i]):.1f}" r="4" fill="{t["orange"]}"/>')
    svg.append(f'  <text x="{xpos(max_i):.1f}" y="{ypos(costs[max_i])-10:.1f}" font-family="-apple-system,sans-serif" font-size="10" font-weight="600" fill="{t["orange"]}" text-anchor="middle">${costs[max_i]:,.0f}</text>')

    svg.append('</svg>')
    return "\n".join(svg)


# ───────────────────────────────────────────────────────
# Output
# ───────────────────────────────────────────────────────
def write_outputs(daily, by_model, summary, base_dir):
    base = Path(base_dir)
    assets = base / "assets"; data = base / "data"
    assets.mkdir(exist_ok=True); data.mkdir(exist_ok=True)

    for theme in ["dark", "light"]:
        (assets / f"stats-card-{theme}.svg").write_text(svg_stats_card(summary, daily, by_model, theme))
        (assets / f"heatmap-{theme}.svg").write_text(svg_heatmap(daily, theme))
        (assets / f"daily-cost-{theme}.svg").write_text(svg_daily_cost(daily, theme))

    snapshot = {
        "updated_at": datetime.now().isoformat(),
        "summary": summary,
        "by_model": dict(by_model),
        "daily": dict(daily),
    }
    (data / "stats.json").write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))

    readme = base / "README.md"
    if readme.exists():
        content = readme.read_text()
        s_marker = "<!-- CLAUDE_STATS_START -->"
        e_marker = "<!-- CLAUDE_STATS_END -->"
        if s_marker in content and e_marker in content:
            block = build_stats_block(summary)
            new_content = (
                content.split(s_marker)[0]
                + s_marker + "\n" + block + "\n" + e_marker
                + content.split(e_marker)[1]
            )
            readme.write_text(new_content)


def build_stats_block(summary):
    if not summary: return "_No data yet_"
    base = "https://raw.githubusercontent.com/kangraemin/claude-code-stats/main/assets"
    return f"""
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="{base}/stats-card-dark.svg">
  <img src="{base}/stats-card-light.svg" alt="Claude Code Stats" width="520">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="{base}/heatmap-dark.svg">
  <img src="{base}/heatmap-light.svg" alt="Activity Heatmap" width="843">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="{base}/daily-cost-dark.svg">
  <img src="{base}/daily-cost-light.svg" alt="Daily Cost Trend" width="720">
</picture>

**Last update**: {datetime.now().strftime("%Y-%m-%d %H:%M KST")}
"""


def main():
    base_dir = Path(__file__).parent.parent
    print(f"📊 Claude Code 사용량 분석 시작...")
    daily, by_model = parse_all_logs()
    summary = compute_summary(daily)
    if not summary:
        print("⚠ 데이터 없음"); sys.exit(1)
    print(f"  활동일: {summary['total_days']}일 / 응답: {summary['total_msgs']:,} / 토큰: {summary['total_tokens']/1e9:.2f}B / 비용(추정): ${summary['total_cost']:,.2f}")
    print(f"🎨 SVG 생성 (dark/light 각 3종)...")
    write_outputs(daily, by_model, summary, base_dir)
    print(f"✅ 완료: {base_dir}")


if __name__ == "__main__":
    main()
