import argparse
import email.utils
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from zoneinfo import ZoneInfo


TORONTO = ZoneInfo("America/Toronto")

QUERIES = [
    '"Canadian mutual fund" industry',
    '"Canadian mutual funds" fees OR flows',
    '"Canada mutual fund" launch OR closure',
    '"CIRO" "mutual fund"',
    '"CSA" "mutual fund"',
    '"OSC" "mutual fund"',
    '"AMF" "mutual fund"',
    '"Investment Funds Institute of Canada" mutual funds',
    '"Canadian mutual fund" ETF competition',
]

IMPORTANT_TERMS = [
    "mutual fund",
    "mutual funds",
    "fund flows",
    "fees",
    "MER",
    "CIRO",
    "CSA",
    "OSC",
    "AMF",
    "IFIC",
    "investment fund",
    "advisor",
    "dealer",
    "ETF",
    "fund launch",
    "fund closure",
]


@dataclass(frozen=True)
class NewsItem:
    title: str
    link: str
    source: str
    published: datetime | None
    summary: str


def fetch_url(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 news-monitor/1.0",
            "Accept": "application/rss+xml, application/xml, text/xml",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def google_news_rss_url(query: str) -> str:
    params = urllib.parse.urlencode(
        {
            "q": f"{query} when:7d",
            "hl": "en-CA",
            "gl": "CA",
            "ceid": "CA:en",
        }
    )
    return f"https://news.google.com/rss/search?{params}"


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\\s+", " ", value).strip()


def parse_published(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def parse_source(item: ET.Element, title: str) -> str:
    source = item.findtext("source")
    if source:
        return clean_text(source)
    parts = title.rsplit(" - ", 1)
    if len(parts) == 2:
        return clean_text(parts[1])
    return "Source not listed"


def parse_items(feed_xml: bytes) -> Iterable[NewsItem]:
    root = ET.fromstring(feed_xml)
    for item in root.findall(".//item"):
        raw_title = clean_text(item.findtext("title"))
        source = parse_source(item, raw_title)
        title = raw_title
        suffix = f" - {source}"
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
        link = clean_text(item.findtext("link"))
        summary = clean_text(item.findtext("description"))
        published = parse_published(item.findtext("pubDate"))
        if title and link:
            yield NewsItem(title=title, link=link, source=source, published=published, summary=summary)


def relevance_score(item: NewsItem) -> int:
    text = f"{item.title} {item.summary} {item.source}".lower()
    score = 0
    for term in IMPORTANT_TERMS:
        if term.lower() in text:
            score += 2
    if "canada" in text or "canadian" in text:
        score += 3
    if any(regulator.lower() in text for regulator in ["ciro", "csa", "osc", "amf", "ific"]):
        score += 2
    return score


def collect_news() -> list[NewsItem]:
    seen_links: set[str] = set()
    items: list[NewsItem] = []
    for query in QUERIES:
        try:
            feed = fetch_url(google_news_rss_url(query))
            for item in parse_items(feed):
                if item.link in seen_links:
                    continue
                seen_links.add(item.link)
                if relevance_score(item) >= 5:
                    items.append(item)
        except Exception as exc:
            print(f"Warning: failed query {query!r}: {exc}", file=sys.stderr)

    items.sort(
        key=lambda item: (
            relevance_score(item),
            item.published or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    return items[:10]


def summarize(item: NewsItem) -> str:
    summary = item.summary
    if summary.startswith(item.title):
        summary = summary[len(item.title) :].strip(" -")
    if not summary:
        return "A relevant Canadian mutual fund industry item was found. Review the source for full details."
    words = summary.split()
    if len(words) > 42:
        summary = " ".join(words[:42]).rstrip(".,;:") + "."
    return summary


def format_date(value: datetime | None) -> str:
    if not value:
        return "Date not listed"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TORONTO).strftime("%Y-%m-%d")


def build_briefing(items: list[NewsItem], report_date: datetime) -> str:
    date_label = report_date.astimezone(TORONTO).strftime("%Y-%m-%d")
    lines = [
        f"# Canadian mutual fund news briefing - {date_label}",
        "",
        "Automated morning scan for Canadian mutual fund industry news and regulatory updates.",
        "",
    ]

    if not items:
        lines.extend(
            [
                "No meaningful Canadian mutual fund industry updates were found in today's scan.",
                "",
                "The search covered Canadian mutual fund news, regulatory sources, fund flows, fees, launches, closures, advisor/channel news, and ETF competition.",
            ]
        )
        return "\n".join(lines)

    for index, item in enumerate(items, start=1):
        lines.extend(
            [
                f"## {index}. {item.title}",
                "",
                f"- **Source:** {item.source}",
                f"- **Published:** {format_date(item.published)}",
                f"- **Summary:** {summarize(item)}",
                f"- **Why it matters:** This may affect Canadian fund manufacturers, advisors, compliance teams, product shelves, fees, or investor flows.",
                f"- **Link:** {item.link}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def github_api(method: str, path: str, payload: dict | None = None) -> dict:
    token = os.environ["GITHUB_TOKEN"]
    repository = os.environ["GITHUB_REPOSITORY"]
    url = f"https://api.github.com/repos/{repository}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "canadian-mutual-fund-news-agent",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else {}


def create_issue(title: str, body: str) -> None:
    github_api(
        "POST",
        "/issues",
        {
            "title": title,
            "body": body,
            "labels": ["news-briefing"],
        },
    )


def should_run_now(force: bool) -> bool:
    if force:
        return True
    now = datetime.now(TORONTO)
    return now.hour == 6 and now.minute == 15


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Run even when it is not 6:15 AM America/Toronto.")
    parser.add_argument("--dry-run", action="store_true", help="Print the briefing instead of creating a GitHub issue.")
    args = parser.parse_args()

    if not should_run_now(args.force):
        now = datetime.now(TORONTO).strftime("%Y-%m-%d %H:%M %Z")
        print(f"Skipping because it is {now}, not 06:15 America/Toronto.")
        return 0

    report_date = datetime.now(TORONTO)
    items = collect_news()
    body = build_briefing(items, report_date)
    title = f"Canadian mutual fund news briefing - {report_date.strftime('%Y-%m-%d')}"

    if args.dry_run:
        print(body)
    else:
        create_issue(title, body)
        print(f"Created issue: {title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
