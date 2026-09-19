import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path


OUTPUT_FILE = Path("data/news.json")
ETF_OUTPUT_FILE = Path("data/active_etf_news.json")
ETF_HOLDINGS_FILE = Path("data/active_etf_holdings.json")
TZ_TAIPEI = timezone(timedelta(hours=8))

QUERIES = [
    "台股 when:7d",
    "上市公司 股票 when:7d",
    "ETF 台灣 when:7d",
    "金融市場 台灣 when:7d",
]

KEYWORDS = (
    "台股",
    "股票",
    "股市",
    "大盤",
    "上市",
    "上櫃",
    "櫃買",
    "加權指數",
    "外資",
    "投信",
    "法人",
    "ETF",
    "金融",
    "證券",
    "期貨",
    "財報",
    "營收",
)


def fetch_feed(query):
    params = urllib.parse.urlencode(
        {
            "q": query,
            "hl": "zh-TW",
            "gl": "TW",
            "ceid": "TW:zh-Hant",
        }
    )
    url = "https://news.google.com/rss/search?" + params
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; TaiwanStockAI/1.0)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def clean_title(title, source):
    title = re.sub(r"\s+", " ", title or "").strip()
    suffix = " - " + source if source else ""
    if suffix and title.endswith(suffix):
        title = title[: -len(suffix)].strip()
    return title


def parse_date(value):
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return date.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def parse_feed_articles(feed_bytes, limit=20):
    articles = []
    seen = set()
    root = ET.fromstring(feed_bytes)

    for item in root.findall("./channel/item"):
        source_node = item.find("source")
        source = (
            (source_node.text or "").strip()
            if source_node is not None
            else ""
        )
        title = clean_title(item.findtext("title", ""), source)
        url = item.findtext("link", "").strip()
        published = parse_date(item.findtext("pubDate", ""))

        if not title or not url:
            continue

        key = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", title.lower())
        if key in seen:
            continue
        seen.add(key)

        articles.append(
            {
                "title": title,
                "url": url,
                "source": source or "Google 新聞",
                "published_at": published.isoformat(),
            }
        )

    articles.sort(key=lambda row: row["published_at"], reverse=True)
    return articles[:limit]


def update_active_etf_news():
    if not ETF_HOLDINGS_FILE.exists():
        print("ETF NEWS SKIPPED: holdings file not found")
        return

    holdings_payload = json.loads(
        ETF_HOLDINGS_FILE.read_text(encoding="utf-8")
    )
    etfs = holdings_payload.get("etfs") or {}
    result = {}

    for code, etf in sorted(etfs.items()):
        name = str(etf.get("name") or "").strip()
        query = f'("{code}" OR "{name}") ETF when:30d'

        try:
            articles = parse_feed_articles(fetch_feed(query), limit=20)
        except Exception as error:
            print(f"ETF NEWS WARNING: {code}: {error}")
            articles = []

        result[code] = {
            "code": code,
            "name": name,
            "issuer": etf.get("issuer"),
            "count": len(articles),
            "news": articles,
        }
        print(f"ETF NEWS: {code}: {len(articles)} articles")
        time.sleep(0.2)

    payload = {
        "updated_at": datetime.now(TZ_TAIPEI).isoformat(),
        "source": "Google News RSS search by ETF code and official name",
        "etf_count": len(result),
        "etfs": result,
    }

    ETF_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    ETF_OUTPUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"ETF NEWS UPDATED: {len(result)} ETFs")


def main():
    articles = []
    seen = set()

    for query in QUERIES:
        root = ET.fromstring(fetch_feed(query))

        for item in root.findall("./channel/item"):
            source_node = item.find("source")
            source = (
                (source_node.text or "").strip()
                if source_node is not None
                else ""
            )
            title = clean_title(item.findtext("title", ""), source)
            url = item.findtext("link", "").strip()
            published = parse_date(item.findtext("pubDate", ""))

            if not title or not url:
                continue
            if not any(keyword.lower() in title.lower() for keyword in KEYWORDS):
                continue

            key = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", title.lower())
            if key in seen:
                continue
            seen.add(key)

            articles.append(
                {
                    "title": title,
                    "url": url,
                    "source": source or "Google 新聞",
                    "published_at": published.isoformat(),
                }
            )

    articles.sort(key=lambda row: row["published_at"], reverse=True)
    articles = articles[:100]

    payload = {
        "updated_at": datetime.now(TZ_TAIPEI).isoformat(),
        "source": "Google News RSS",
        "count": len(articles),
        "news": articles,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"NEWS UPDATED: {len(articles)} articles")
    update_active_etf_news()


if __name__ == "__main__":
    main()
