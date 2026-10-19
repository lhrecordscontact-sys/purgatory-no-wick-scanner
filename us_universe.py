"""Broad US-listed ticker discovery with explicit coverage and fail-closed reporting."""
import csv
import io
from urllib.request import Request, urlopen

SOURCES = (
    ("nasdaq", "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"),
    ("other", "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"),
)
def universe():
    tickers=set()
    errors={}
    for name,url in SOURCES:
        try:
            req=Request(url,headers={"User-Agent":"Mozilla/5.0 PURGATORY research"})
            with urlopen(req,timeout=18) as response:
                data=response.read(2_000_000).decode("utf-8-sig")
            rows=csv.DictReader(io.StringIO(data),delimiter="|")
            for row in rows:
                symbol=(row.get("Symbol") or row.get("ACT Symbol") or "").strip()
                test=(row.get("Test Issue") or "N").strip()
                etf=(row.get("ETF") or "N").strip()
                # Include listed common shares and ETFs, exclude obvious nonstandard tickers.
                if test!="N" or etf not in ("Y","N"): continue
                if symbol and symbol.isascii() and symbol.replace(".","").isalpha() and len(symbol)<=5:
                    tickers.add(symbol.replace(".","-"))
        except Exception as exc:
            errors[name]=type(exc).__name__
    return sorted(tickers),errors
