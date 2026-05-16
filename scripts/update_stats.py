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
    """GitHub 잔디 스타일 일별 비용 heatmap (1년 윈도우, 항상 최근 1년 표시)."""
    if not daily:
        return ""
    today = date.today()
    # 1년 윈도우 (last 53 weeks)
    end = today
    # 첫 주 일요일 정렬
    end_wd_sun0 = (end.weekday() + 1) % 7  # Sun=0
    last_sat = end + timedelta(days=(6 - end_wd_sun0))  # 다음 토요일
    start = last_sat - timedelta(days=52 * 7 + 6)  # 53주 전 일요일

    days_with_data = {d: daily[d] for d in daily}
    max_cost = max((v["cost"] for v in days_with_data.values()), default=1)

    def color(cost):
        if cost == 0: return "#161b22"
        ratio = cost / max_cost if max_cost > 0 else 0
        if ratio < 0.10: return "#0e4429"
        if ratio < 0.30: return "#006d32"
        if ratio < 0.60: return "#26a641"
        return "#39d353"

    cell = 12; gap = 3; col_width = cell + gap
    n_cols = 53
    label_w = 32; label_h = 22; pad = 16
    w = label_w + n_cols * col_width + pad
    h = label_h + 7 * col_width + pad

    bg = "#0d1117"; border = "#30363d"; text = "#8b949e"

    svg = [
        f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">',
        f'  <rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="6" fill="{bg}" stroke="{border}"/>',
    ]

    # 요일 레이블 (Mon, Wed, Fri만) — 셀 중앙 정렬
    weekday_labels = {1: "Mon", 3: "Wed", 5: "Fri"}
    for wd, lbl in weekday_labels.items():
        y = label_h + wd * col_width + cell - 2
        svg.append(f'  <text x="4" y="{y}" font-family="-apple-system,sans-serif" font-size="9" fill="{text}">{lbl}</text>')

    # 셀 그리기 + 월 레이블
    cur = start
    col = 0
    last_month_drawn = None
    while col < n_cols:
        wd_sun0 = (cur.weekday() + 1) % 7  # Sun=0
        if wd_sun0 != 0:
            # start가 일요일이 아니면 정렬 위해 스킵 (안 일어남, 위에서 정렬했지만 안전망)
            cur += timedelta(days=1)
            continue
        # 한 컬럼 (7일)
        for offset in range(7):
            d = cur + timedelta(days=offset)
            if d > today:
                break
            d_str = d.strftime("%Y-%m-%d")
            cost = days_with_data.get(d_str, {}).get("cost", 0)
            x = label_w + col * col_width
            y = label_h + offset * col_width
            c = color(cost)
            tooltip = f'{d_str}: ${cost:,.0f}' if cost > 0 else f'{d_str}: 0'
            svg.append(f'  <rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{c}"><title>{tooltip}</title></rect>')

        # 월 레이블 (각 월의 첫 번째 주가 시작되는 컬럼에만)
        if cur.month != last_month_drawn:
            month_lbl = cur.strftime("%b")
            mx = label_w + col * col_width
            svg.append(f'  <text x="{mx}" y="14" font-family="-apple-system,sans-serif" font-size="9" fill="{text}">{month_lbl}</text>')
            last_month_drawn = cur.month

        cur += timedelta(days=7)
        col += 1

    # 색 범례 (오른쪽 하단)
    legend_y = h - 14
    legend_x = w - 130
    svg.append(f'  <text x="{legend_x - 30}" y="{legend_y + 2}" font-family="-apple-system,sans-serif" font-size="9" fill="{text}">Less</text>')
    for i, c in enumerate(["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]):
        svg.append(f'  <rect x="{legend_x + i*15}" y="{legend_y - 6}" width="10" height="10" rx="2" fill="{c}"/>')
    svg.append(f'  <text x="{legend_x + 5*15 + 4}" y="{legend_y + 2}" font-family="-apple-system,sans-serif" font-size="9" fill="{text}">More</text>')

    svg.append('</svg>')
    return "\n".join(svg)


def svg_daily_cost(daily):
    """일별 비용 라인 차트 — 연속 날짜 (휴식일 = 0)."""
    if not daily:
        return ""
    days_with_data = sorted(daily.keys())
    if len(days_with_data) < 2:
        return ""

    # 첫 활동일 ~ 마지막 활동일 사이 모든 날짜 채우기
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

    bg = "#0d1117"; border = "#30363d"; text = "#c9d1d9"; line = "#58a6ff"; grid = "#21262d"
    fill_color = "#58a6ff"  # use opacity attribute instead of rgba (better GitHub compat)

    def xpos(i):
        return pad_l + (i / (n - 1)) * plot_w
    def ypos(c):
        return pad_t + plot_h - (c / max_c) * plot_h

    svg = [
        f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">',
        f'  <rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="6" fill="{bg}" stroke="{border}"/>',
        f'  <text x="{w//2}" y="20" font-family="-apple-system,sans-serif" font-size="13" font-weight="600" fill="{text}" text-anchor="middle">Daily Cost (USD)</text>',
    ]

    # Y axis grid (5 lines)
    for i in range(5):
        v = max_c * (4 - i) / 4
        y = pad_t + plot_h * i / 4
        svg.append(f'  <line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" stroke="{grid}" stroke-width="0.5"/>')
        svg.append(f'  <text x="{pad_l - 5}" y="{y+3:.1f}" font-family="-apple-system,sans-serif" font-size="10" fill="{text}" text-anchor="end">${v:,.0f}</text>')

    # X axis labels — 월별
    months_shown = set()
    for i, d in enumerate(all_days):
        m = d[:7]
        if m not in months_shown:
            months_shown.add(m)
            x = xpos(i)
            lbl = d[5:7] + "월"
            svg.append(f'  <text x="{x:.1f}" y="{h-15}" font-family="-apple-system,sans-serif" font-size="10" fill="{text}" text-anchor="middle">{lbl}</text>')

    # Area fill (opacity로 GitHub 호환)
    points = [f"{xpos(i):.1f},{ypos(c):.1f}" for i, c in enumerate(costs)]
    area = f"M{pad_l:.1f},{(pad_t + plot_h):.1f} L " + " L ".join(points) + f" L {(w-pad_r):.1f},{(pad_t + plot_h):.1f} Z"
    svg.append(f'  <path d="{area}" fill="{fill_color}" fill-opacity="0.2"/>')
    # Line
    line_path = "M " + " L ".join(points)
    svg.append(f'  <path d="{line_path}" stroke="{line}" stroke-width="1.5" fill="none"/>')

    # Highlight max
    max_i = costs.index(max(costs))
    svg.append(f'  <circle cx="{xpos(max_i):.1f}" cy="{ypos(costs[max_i]):.1f}" r="4" fill="#f78166"/>')
    svg.append(f'  <text x="{xpos(max_i):.1f}" y="{ypos(costs[max_i])-8:.1f}" font-family="-apple-system,sans-serif" font-size="10" font-weight="600" fill="#f78166" text-anchor="middle">${costs[max_i]:,.0f}</text>')

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
