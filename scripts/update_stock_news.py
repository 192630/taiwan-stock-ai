import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path


STOCKS_FILE = Path("data/stocks.json")
OUTPUT_DIR = Path("data/stock_news")
PROGRESS_FILE = Path("data/stock_news_progress.json")
BATCH_SIZE = 80
TZ_TAIPEI = timezone(timedelta(hours=8))

PRIORITY_CODES = [
    "2330", "2454", "2317", "2382", "2308", "2881", "2882", "2303",
    "3711", "2412", "2891", "2886", "2884", "2885", "3231", "3037",
    "2383", "3017", "6669", "3443", "6223", "2345", "2368", "2379",
]


def clean_number(value):
    return str(value or "").strip()


def fetch_feed(query):
    params = urllib.parse.urlencode(
        {
            "q": query,
            "hl": "zh-TW",
            "gl": "TW",
            "ceid": "TW:zh-Hant",
        }
    )
    request = urllib.request.Request(
        "https://news.google.com/rss/search?" + params,
        headers={"User-Agent": "Mozilla/5.0 (compatible; TaiwanStockAI/1.0)"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()


def parse_date(value):
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return date.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def clean_title(title, source):
    title = re.sub(r"\s+", " ", title or "").strip()
    suffix = " - " + source if source else ""
    if suffix and title.endswith(suffix):
        title = title[: -len(suffix)].strip()
    return title


def parse_articles(feed_bytes, code, name):
    root = ET.fromstring(feed_bytes)
    articles = []
    seen = set()
    code_lower = code.lower()
    name_lower = name.lower()

    for item in root.findall("./channel/item"):
        source_node = item.find("source")
        source = (
            (source_node.text or "").strip()
            if source_node is not None
            else ""
        )
        title = clean_title(item.findtext("title", ""), source)
        url = item.findtext("link", "").strip()
        title_lower = title.lower()

        if not title or not url:
            continue
        if code_lower not in title_lower and name_lower not in title_lower:
            continue

        key = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", title_lower)
        if key in seen:
            continue
        seen.add(key)

        articles.append(
            {
                "title": title,
                "url": url,
                "source": source or "Google 新聞",
                "published_at": parse_date(
                    item.findtext("pubDate", "")
                ).isoformat(),
            }
        )

    articles.sort(key=lambda row: row["published_at"], reverse=True)
    return articles[:12]


def load_stocks():
    payload = json.loads(STOCKS_FILE.read_text(encoding="utf-8"))
    rows = payload.get("stocks") if isinstance(payload, dict) else payload
    result = []

    for row in rows or []:
        code = clean_number(
            row.get("Code") or row.get("code") or row.get("證券代號")
        )
        name = clean_number(
            row.get("Name") or row.get("name") or row.get("證券名稱")
        )

        # 個股新聞先處理四碼上市股票；ETF 由專屬流程負責。
        if not re.fullmatch(r"\d{4}", code) or not name:
            continue
        result.append({"code": code, "name": name})

    priority = {code: index for index, code in enumerate(PRIORITY_CODES)}
    result.sort(
        key=lambda row: (
            0 if row["code"] in priority else 1,
            priority.get(row["code"], 9999),
            row["code"],
        )
    )
    return result


def load_cursor(total):
    if not PROGRESS_FILE.exists() or total <= 0:
        return 0
    try:
        payload = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        return int(payload.get("next_index") or 0) % total
    except (ValueError, TypeError, json.JSONDecodeError):
        return 0


def main():
    stocks = load_stocks()
    if not stocks:
        raise RuntimeError("找不到可更新新聞的四碼股票")

    start = load_cursor(len(stocks))
    batch = [stocks[(start + offset) % len(stocks)] for offset in range(min(BATCH_SIZE, len(stocks)))]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    success = 0
    for stock in batch:
        code = stock["code"]
        name = stock["name"]
        query = f'("{code}" OR "{name}") 股票 when:30d'

        try:
            articles = parse_articles(fetch_feed(query), code, name)
            payload = {
                "updated_at": datetime.now(TZ_TAIPEI).isoformat(),
                "source": "Google News RSS search by stock code and name",
                "code": code,
                "name": name,
                "count": len(articles),
                "news": articles,
            }
            (OUTPUT_DIR / f"{code}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            success += 1
            print(f"STOCK NEWS: {code} {name}: {len(articles)} articles")
        except Exception as error:
            print(f"STOCK NEWS WARNING: {code} {name}: {error}")

        time.sleep(0.2)

    next_index = (start + len(batch)) % len(stocks)
    PROGRESS_FILE.write_text(
        json.dumps(
            {
                "updated_at": datetime.now(TZ_TAIPEI).isoformat(),
                "total_stocks": len(stocks),
                "batch_size": len(batch),
                "start_index": start,
                "next_index": next_index,
                "success_count": success,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"STOCK NEWS BATCH FINISHED: {success}/{len(batch)}")


if __name__ == "__main__":
    main()
