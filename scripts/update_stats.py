#!/usr/bin/env python3
"""
update_stats.py — Claude Code 사용량 통계 + SVG 카드 자동 생성

매일 cron으로 실행:
  1. ~/.claude/projects/*.jsonl 전체 파싱
  2. 통계 계산 (총 비용/토큰/응답수, 일별, 모델별)
  3. SVG 생성 (stats-card, heatmap, daily-cost)
  4. data/stats.json 갱신
  5. README.md 마커 사이 자동 갱신

다음 단계 (별도): git commit + push
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta, date
from collections import defaultdict
import statistics

# 가격 (정가 기준, per 1M tokens, USD) — 2026 기준
PRICING = {
    "claude-opus-4-7": (15.0, 75.0),
    "claude-opus-4-6": (15.0, 75.0),
    "claude-opus-4-5": (15.0, 75.0),
    "claude-opus-4": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-haiku-4": (1.0, 5.0),
    "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3-5-haiku": (0.8, 4.0),
    "claude-3-opus": (15.0, 75.0),
}

def get_pricing(model: str):
    if not model:
        return (3.0, 15.0)
    m = model.lower()
    for k, v in PRICING.items():
        if k in m:
            return v
    return (3.0, 15.0)


def parse_all_logs():
    """모든 jsonl 파싱 → 통계 dict 반환."""
    base = Path.home() / ".claude" / "projects"
    daily = defaultdict(lambda: {"cost": 0.0, "msgs": 0, "input": 0, "cache_c": 0, "cache_r": 0, "output": 0})
    by_model = defaultdict(lambda: {"cost": 0.0, "msgs": 0, "tokens": 0})

    for proj_dir in base.iterdir():
        if not proj_dir.is_dir():
            continue
        for jsonl in proj_dir.rglob("*.jsonl"):
            try:
                with open(jsonl) as f:
                    for line in f:
                        try:
                            obj = json.loads(line)
                            if obj.get("type") != "assistant":
                                continue
                            msg = obj.get("message", {})
                            usage = msg.get("usage", {})
                            if not usage:
                                continue
                            ts = obj.get("timestamp", "")[:10]
                            if not ts:
                                continue
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
                        except Exception:
                            pass
            except Exception:
                pass

    return daily, by_model


def compute_summary(daily):
    days_sorted = sorted(daily.keys())
    if not days_sorted:
        return {}
    costs = [daily[d]["cost"] for d in days_sorted]
    msgs = [daily[d]["msgs"] for d in days_sorted]
    tokens = [daily[d]["input"] + daily[d]["cache_c"] + daily[d]["cache_r"] + daily[d]["output"] for d in days_sorted]

    heaviest_day = max(days_sorted, key=lambda d: daily[d]["cost"])

    return {
        "first_day": days_sorted[0],
        "last_day": days_sorted[-1],
        "total_days": len(days_sorted),
        "total_cost": sum(costs),
        "total_msgs": sum(msgs),
        "total_tokens": sum(tokens),
        "avg_cost": statistics.mean(costs),
        "median_cost": statistics.median(costs),
        "max_cost": max(costs),
        "heaviest_day": heaviest_day,
        "max_msgs": max(msgs),
        "max_tokens": max(tokens),
        "avg_msgs": statistics.mean(msgs),
        "avg_tokens": statistics.mean(tokens),
    }


# ───────────────────────────────────────────────────────
# SVG generators
# ───────────────────────────────────────────────────────
def svg_stats_card(summary, by_model):
    """github-readme-stats 스타일 통계 카드."""
    if not summary:
        return ""
    w, h = 480, 300
    bg = "#0d1117"; border = "#30363d"; title = "#58a6ff"; text = "#c9d1d9"; accent = "#7ee787"; warn = "#f78166"

    rows = [
        ("💰 Total Cost (est)", f"${summary['total_cost']:,.0f}", accent),
        ("🔥 Total Tokens", f"{summary['total_tokens']/1_000_000_000:.2f}B", text),
        ("💬 Total Responses", f"{summary['total_msgs']:,}", text),
        ("📅 Active Days", f"{summary['total_days']} days", text),
        ("📊 Daily Average", f"${summary['avg_cost']:,.0f} / day", text),
        ("🏆 Heaviest Day", f"${summary['max_cost']:,.0f} ({summary['heaviest_day']})", warn),
    ]

    svg = [
        f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">',
        f'  <rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="6" fill="{bg}" stroke="{border}"/>',
        f'  <text x="25" y="35" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="18" font-weight="600" fill="{title}">🤖 Claude Code Usage</text>',
        f'  <text x="25" y="55" font-family="-apple-system,sans-serif" font-size="11" fill="#8b949e">{summary["first_day"]} ~ {summary["last_day"]}</text>',
    ]
    for i, (label, value, color) in enumerate(rows):
        y = 90 + i * 32
        svg.append(f'  <text x="25" y="{y}" font-family="-apple-system,sans-serif" font-size="14" fill="{text}">{label}</text>')
        svg.append(f'  <text x="{w-25}" y="{y}" font-family="-apple-system,sans-serif" font-size="14" font-weight="600" fill="{color}" text-anchor="end">{value}</text>')

    svg.append(f'  <text x="{w-25}" y="{h-12}" font-family="-apple-system,sans-serif" font-size="9" fill="#6e7681" text-anchor="end">Updated: {datetime.now().strftime("%Y-%m-%d %H:%M KST")}</text>')
    svg.append('</svg>')
    return "\n".join(svg)


def svg_heatmap(daily):
    """GitHub 잔디 스타일 일별 비용 heatmap."""
    if not daily:
        return ""
    days_sorted = sorted(daily.keys())
    first = datetime.strptime(days_sorted[0], "%Y-%m-%d").date()
    last = datetime.strptime(days_sorted[-1], "%Y-%m-%d").date()

    # 첫 주 일요일부터 시작 (GitHub style)
    start = first - timedelta(days=first.weekday() + 1 if first.weekday() < 6 else 0)
    if start.weekday() != 6:  # not Sunday
        start = start - timedelta(days=(start.weekday() + 1) % 7)

    # 색 단계
    max_cost = max(daily[d]["cost"] for d in daily)
    def color(cost):
        if cost == 0: return "#161b22"
        ratio = cost / max_cost
        if ratio < 0.10: return "#0e4429"
        if ratio < 0.30: return "#006d32"
        if ratio < 0.60: return "#26a641"
        return "#39d353"

    cell = 11; gap = 2; col_width = cell + gap
    cols = (last - start).days // 7 + 1
    w = cols * col_width + 35
    h = 7 * col_width + 30

    bg = "#0d1117"; border = "#30363d"; text = "#8b949e"

    svg = [
        f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">',
        f'  <rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="6" fill="{bg}" stroke="{border}"/>',
    ]

    # 요일 레이블 (Mon, Wed, Fri만)
    weekday_labels = {1: "Mon", 3: "Wed", 5: "Fri"}
    for wd, lbl in weekday_labels.items():
        y = 20 + wd * col_width + cell - 2
        svg.append(f'  <text x="3" y="{y}" font-family="-apple-system,sans-serif" font-size="9" fill="{text}">{lbl}</text>')

    # 셀 그리기
    cur = start
    col = 0
    last_month = None
    while cur <= last:
        wd = (cur.weekday() + 1) % 7  # Sunday=0
        d_str = cur.strftime("%Y-%m-%d")
        cost = daily.get(d_str, {}).get("cost", 0) if cur >= first else 0
        x = 28 + col * col_width
        y = 20 + wd * col_width
        c = color(cost)
        svg.append(f'  <rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{c}"><title>{d_str}: ${cost:.0f}</title></rect>')

        # 월 레이블 (첫째 주만)
        if wd == 0:
            if cur.month != last_month:
                month_lbl = cur.strftime("%b")
                svg.append(f'  <text x="{x}" y="14" font-family="-apple-system,sans-serif" font-size="9" fill="{text}">{month_lbl}</text>')
                last_month = cur.month

        cur += timedelta(days=1)
        if wd == 6:  # Saturday → next column
            col += 1

    svg.append('</svg>')
    return "\n".join(svg)


def svg_daily_cost(daily):
    """일별 비용 라인 차트."""
    if not daily:
        return ""
    days_sorted = sorted(daily.keys())
    costs = [daily[d]["cost"] for d in days_sorted]
    n = len(costs)
    if n < 2:
        return ""

    w, h = 600, 200
    pad_l, pad_r, pad_t, pad_b = 50, 20, 25, 35
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b

    max_c = max(costs); min_c = 0
    bg = "#0d1117"; border = "#30363d"; text = "#c9d1d9"; line = "#58a6ff"; grid = "#21262d"; fill = "rgba(88,166,255,0.2)"

    def xpos(i):
        return pad_l + (i / (n - 1)) * plot_w
    def ypos(c):
        return pad_t + plot_h - (c / max_c) * plot_h

    svg = [
        f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">',
        f'  <rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="6" fill="{bg}" stroke="{border}"/>',
        f'  <text x="{w//2}" y="18" font-family="-apple-system,sans-serif" font-size="12" font-weight="600" fill="{text}" text-anchor="middle">Daily Cost (USD)</text>',
    ]

    # Y axis grid (4 lines)
    for i in range(5):
        v = max_c * (4 - i) / 4
        y = pad_t + plot_h * i / 4
        svg.append(f'  <line x1="{pad_l}" y1="{y}" x2="{w-pad_r}" y2="{y}" stroke="{grid}" stroke-width="0.5"/>')
        svg.append(f'  <text x="{pad_l - 5}" y="{y+3}" font-family="-apple-system,sans-serif" font-size="9" fill="{text}" text-anchor="end">${v:.0f}</text>')

    # X axis labels (first / mid / last)
    for i in [0, n // 2, n - 1]:
        x = xpos(i)
        lbl = days_sorted[i][5:]  # MM-DD
        svg.append(f'  <text x="{x}" y="{h-15}" font-family="-apple-system,sans-serif" font-size="9" fill="{text}" text-anchor="middle">{lbl}</text>')

    # Area fill
    points = [f"{xpos(i)},{ypos(c)}" for i, c in enumerate(costs)]
    area = f"M{pad_l},{pad_t + plot_h} L " + " L ".join(points) + f" L {w-pad_r},{pad_t + plot_h} Z"
    svg.append(f'  <path d="{area}" fill="{fill}"/>')
    # Line
    line_path = "M " + " L ".join(points)
    svg.append(f'  <path d="{line_path}" stroke="{line}" stroke-width="1.5" fill="none"/>')
    # Highlight max
    max_i = costs.index(max(costs))
    svg.append(f'  <circle cx="{xpos(max_i)}" cy="{ypos(costs[max_i])}" r="3" fill="#f78166"/>')
    svg.append(f'  <text x="{xpos(max_i)}" y="{ypos(costs[max_i])-6}" font-family="-apple-system,sans-serif" font-size="9" fill="#f78166" text-anchor="middle">${costs[max_i]:.0f}</text>')

    svg.append('</svg>')
    return "\n".join(svg)


# ───────────────────────────────────────────────────────
# Output
# ───────────────────────────────────────────────────────
def write_outputs(daily, by_model, summary, base_dir):
    base = Path(base_dir)
    assets = base / "assets"
    data = base / "data"
    assets.mkdir(exist_ok=True)
    data.mkdir(exist_ok=True)

    # SVGs
    (assets / "stats-card.svg").write_text(svg_stats_card(summary, by_model))
    (assets / "heatmap.svg").write_text(svg_heatmap(daily))
    (assets / "daily-cost.svg").write_text(svg_daily_cost(daily))

    # JSON
    snapshot = {
        "updated_at": datetime.now().isoformat(),
        "summary": summary,
        "by_model": {k: v for k, v in by_model.items()},
        "daily": {k: v for k, v in daily.items()},
    }
    (data / "stats.json").write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))

    # README 갱신
    readme = base / "README.md"
    if readme.exists():
        content = readme.read_text()
        start_marker = "<!-- CLAUDE_STATS_START -->"
        end_marker = "<!-- CLAUDE_STATS_END -->"
        if start_marker in content and end_marker in content:
            stats_block = build_stats_block(summary)
            new_content = (
                content.split(start_marker)[0]
                + start_marker + "\n" + stats_block + "\n" + end_marker
                + content.split(end_marker)[1]
            )
            readme.write_text(new_content)


def build_stats_block(summary):
    if not summary:
        return "_No data yet_"
    return f"""
![Claude Code Usage](./assets/stats-card.svg)

![Activity Heatmap](./assets/heatmap.svg)

![Daily Cost Trend](./assets/daily-cost.svg)

**Last update**: {datetime.now().strftime("%Y-%m-%d %H:%M KST")}

| Metric | Value |
|---|---:|
| Total Cost (est) | **${summary['total_cost']:,.0f}** |
| Total Tokens | {summary['total_tokens']/1_000_000_000:.2f}B |
| Total Responses | {summary['total_msgs']:,} |
| Active Days | {summary['total_days']} |
| Heaviest Day | ${summary['max_cost']:,.0f} ({summary['heaviest_day']}) |
| Daily Average | ${summary['avg_cost']:,.0f} |
| Period | {summary['first_day']} ~ {summary['last_day']} |
"""


def main():
    base_dir = Path(__file__).parent.parent
    print(f"📊 Claude Code 사용량 분석 시작...")
    daily, by_model = parse_all_logs()
    summary = compute_summary(daily)
    if not summary:
        print("⚠ 데이터 없음")
        sys.exit(1)
    print(f"  활동일: {summary['total_days']}일")
    print(f"  총 응답: {summary['total_msgs']:,}")
    print(f"  총 토큰: {summary['total_tokens']/1e9:.2f}B")
    print(f"  총 비용 (정가): ${summary['total_cost']:,.2f}")
    print()
    print(f"🎨 SVG 생성 + README 갱신...")
    write_outputs(daily, by_model, summary, base_dir)
    print(f"✅ 완료: {base_dir}")


if __name__ == "__main__":
    main()
