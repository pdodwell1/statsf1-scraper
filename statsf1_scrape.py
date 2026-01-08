import re
import datetime as dt
from pathlib import Path

import requests
import pandas as pd
from bs4 import BeautifulSoup

BASE = "https://www.statsf1.com"
YEAR = 2025

HEADERS = {"User-Agent": "Mozilla/5.0"}

PAGES = [
    "engages.aspx",
    "qualification.aspx",
    "grille.aspx",
    "classement.aspx",
    "en-tete.aspx",
    "meilleur-tour.aspx",
    "tour-par-tour.aspx",
    "championnat.aspx",
]

def get_race_slugs_for_year(year: int) -> list[str]:
    """
    Discover race slugs by parsing href attributes and accepting only clean slugs.
    Handles both:
      /en/2025/abou-dhabi/...
      /en/2025/abou-dhabi.aspx
    """
    anchor = f"{BASE}/en/{year}/abou-dhabi/classement.aspx"
    resp = requests.get(anchor, headers=HEADERS, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    slugs = set()
    for a in soup.select("a[href]"):
        href = a["href"].strip()

        m = re.match(rf"^/en/{year}/([a-z0-9\-]+)(?:/|\.aspx)", href)
        if m:
            slugs.add(m.group(1))

    return sorted(slugs)
    
def pick_latest_race_slug(slugs: list[str]) -> str:
    best = None
    best_dt = None

    for slug in slugs:
        if not re.fullmatch(r"[a-z0-9\-]+", slug):
            continue
        url = f"{BASE}/en/{YEAR}/{slug}/classement.aspx"
        try:
            r = requests.head(url, headers=HEADERS, timeout=15, allow_redirects=True)
            if r.status_code >= 400:
                continue

            lm = r.headers.get("Last-Modified")
            if lm:
                t = dt.datetime.strptime(lm, "%a, %d %b %Y %H:%M:%S %Z")
            else:
                t = dt.datetime.min

            if best_dt is None or t > best_dt:
                best_dt = t
                best = slug
        except Exception:
            continue

    if not best:
        raise RuntimeError("Could not determine latest race slug for this year.")
    return best

def scrape_tables(url: str) -> list[pd.DataFrame]:
    dfs = pd.read_html(url)
    out = []
    for df in dfs:
        df.columns = [str(c).strip() for c in df.columns]
        out.append(df)
    return out

def safe_sheet_name(name: str) -> str:
    bad = r'[:\\/?*\[\]]'
    name = re.sub(bad, "-", name)
    return name[:31]

def main():
    slugs = get_race_slugs_for_year(YEAR)
    if not slugs:
        raise RuntimeError("No race slugs found. The season page structure may have changed.")

    latest_slug = pick_latest_race_slug(slugs)

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    out_file = Path(f"statsf1_{YEAR}_{latest_slug}_{timestamp}.xlsx")

    with pd.ExcelWriter(out_file, engine="openpyxl") as writer:
        pd.DataFrame([{
            "run_timestamp": timestamp,
            "year": YEAR,
            "race_slug": latest_slug,
        }]).to_excel(writer, sheet_name="RunLog", index=False)

        for page in PAGES:
            url = f"{BASE}/en/{YEAR}/{latest_slug}/{page}"
            dfs = scrape_tables(url)

            for i, df in enumerate(dfs, start=1):
                sheet = safe_sheet_name(f"{latest_slug}_{page.replace('.aspx','')}_{i}")
                df.to_excel(writer, sheet_name=sheet, index=False)

    print(f"Saved: {out_file.resolve()}")

if __name__ == "__main__":
    main()
