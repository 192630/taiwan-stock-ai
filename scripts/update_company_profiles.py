import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


OUTPUT_FILE = Path("data/company_profiles.json")
TZ_TAIPEI = timezone(timedelta(hours=8))
SOURCES = (
    ("上市", "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"),
    ("上櫃", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"),
)


def fetch_json(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; TaiwanStockAI/1.0)"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def first(row, *keys):
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def normalize_date(value):
    text = str(value or "").strip().replace("/", "-")
    digits = "".join(char for char in text if char.isdigit())
    if len(digits) == 7:
        return f"{int(digits[:3]) + 1911}-{digits[3:5]}-{digits[5:7]}"
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return text


def normalize(row, market):
    code = first(row, "公司代號", "公司代码", "SecuritiesCompanyCode")
    if not code:
        return None
    return {
        "code": code,
        "market": market,
        "company_name": first(row, "公司名稱", "公司名称"),
        "short_name": first(row, "公司簡稱", "公司简称"),
        "industry": first(row, "產業別", "产业别"),
        "founded_date": normalize_date(first(row, "成立日期")),
        "listed_date": normalize_date(first(row, "上市日期", "上櫃日期", "上柜日期")),
        "address": first(row, "住址", "地址"),
        "phone": first(row, "總機電話", "总机电话"),
        "website": first(row, "公司網址", "公司网站"),
    }


def main():
    profiles = {}
    source_status = []
    for market, url in SOURCES:
        try:
            rows = fetch_json(url)
            count = 0
            for row in rows if isinstance(rows, list) else []:
                profile = normalize(row, market)
                if profile:
                    profiles[profile["code"]] = profile
                    count += 1
            source_status.append({"market": market, "url": url, "count": count})
            print(f"COMPANY PROFILES: {market}: {count}")
        except Exception as error:
            source_status.append({"market": market, "url": url, "error": str(error)})
            print(f"COMPANY PROFILES WARNING: {market}: {error}")

    if not profiles:
        raise RuntimeError("上市與上櫃公司基本資料皆抓取失敗")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(
            {
                "updated_at": datetime.now(TZ_TAIPEI).isoformat(),
                "source": "TWSE OpenAPI / TPEx OpenAPI",
                "count": len(profiles),
                "sources": source_status,
                "profiles": profiles,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"COMPANY PROFILES FINISHED: {len(profiles)}")


if __name__ == "__main__":
    main()
