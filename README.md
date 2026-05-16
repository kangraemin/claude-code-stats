# 🤖 Claude Code Stats — kangraemin

Daily auto-generated stats from local `~/.claude/projects/` logs.

<!-- CLAUDE_STATS_START -->

![Claude Code Usage](./assets/stats-card.svg)

![Activity Heatmap](./assets/heatmap.svg)

![Daily Cost Trend](./assets/daily-cost.svg)

**Last update**: 2026-05-16 09:52 KST

| Metric | Value |
|---|---:|
| Total Cost (est) | **$35,012** |
| Total Tokens | 23.36B |
| Total Responses | 226,793 |
| Active Days | 59 |
| Heaviest Day | $3,099 (2026-05-15) |
| Daily Average | $593 |
| Period | 2026-01-18 ~ 2026-05-16 |

<!-- CLAUDE_STATS_END -->

---

## How it works

매일 cron이 로컬 `~/.claude/projects/*.jsonl` 파싱 → SVG 카드 생성 → 이 repo에 commit + push.

### 자기 사용량도 추적하고 싶다면 (fork 가이드)

1. 이 repo를 fork 또는 clone
2. `scripts/update_stats.py` 실행 — `~/.claude/projects/`에서 자동으로 본인 데이터 파싱
3. crontab 등록 (예: 매일 02:00 KST)
   ```bash
   0 2 * * * cd /path/to/claude-code-stats && python3 scripts/update_stats.py && git add -A && git commit -m "chore: daily update" && git push
   ```
4. 본인 GitHub 프로필 README에 임베드:
   ```markdown
   ![Claude Code Usage](https://raw.githubusercontent.com/USERNAME/claude-code-stats/main/assets/stats-card.svg)
   ```

### 주의

- 누적 비용은 **Anthropic 정가 기준 추정**. Pro/Max 구독 정액과 다름.
- `~/.claude/projects/`는 **현재 컴퓨터의 로컬 파일**. 여러 노트북 합산은 별도 동기화 필요.
- 가격표는 `scripts/update_stats.py`의 `PRICING` 딕셔너리에서 수정.

## License

MIT
