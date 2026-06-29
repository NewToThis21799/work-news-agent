# Canadian Mutual Fund News Agent

This repository runs a daily GitHub Actions job that searches for Canadian mutual fund industry news and posts a morning briefing as a GitHub issue.

## What It Tracks

- Canadian mutual fund companies and product launches or closures
- Fund flows, fees, performance trends, and advisor/channel news
- CIRO, CSA, OSC, AMF, and other regulatory updates
- ETF competition and market or tax changes affecting Canadian mutual funds

## Schedule

The workflow is scheduled for 6:15 AM America/Toronto time. GitHub Actions uses UTC, so the workflow checks both possible UTC times and the script exits unless the local Toronto time is 6:15 AM.

## Setup

1. Go to the repository's **Settings > Actions > General**.
2. Under **Workflow permissions**, choose **Read and write permissions**.
3. Commit these files to the repository.
4. Check the **Actions** tab after the next scheduled run, or run it manually with **Run workflow**.

## Output

Each run creates a GitHub issue titled like:

`Canadian mutual fund news briefing - 2026-06-29`

If there is little meaningful news, the issue will say so instead of padding the report.
