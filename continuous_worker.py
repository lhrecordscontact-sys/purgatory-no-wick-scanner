"""Persistent research scheduler. PAPER/RESEARCH ONLY. Requires an always-on host.

POLL: every 60 seconds during RTH (paper scan uses its own market-hours guard).
RESEARCH: every 30 minutes during RTH; once after the close.
Runs are sequential; no overlapping data jobs or broker orders.
"""
import logging
import base64
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import os
import subprocess
import sys
import time
from datetime import datetime, time as clocktime
from zoneinfo import ZoneInfo

from paper_bot import scan_once

NY = ZoneInfo("America/New_York")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("purgatory-worker")
POLL_SECONDS = max(60, int(os.getenv("WORKER_POLL_SECONDS", "60")))
RESEARCH_INTERVAL = max(30, int(os.getenv("WORKER_RESEARCH_MINUTES", "30")))
RESEARCH_TIMEOUT = max(120, int(os.getenv("WORKER_RESEARCH_TIMEOUT_SECONDS", "1200")))

def market_day(now):
    return now.weekday() < 5

def publish_report():
    """Publish completed report to GitHub for the website (requires GITHUB_WRITE_TOKEN)."""
    token = os.getenv("GITHUB_WRITE_TOKEN", "")
    path = Path("reports/research_latest.json")
    if not token:
        log.warning("GITHUB_WRITE_TOKEN missing: report saved locally only, not visible on website")
        return
    if not path.is_file():
        log.warning("No research report file to publish")
        return
    url = "https://api.github.com/repos/lhrecordscontact-sys/purgatory-no-wick-scanner/contents/reports/research_latest.json"
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "User-Agent": "purgatory-research-worker", "Content-Type": "application/json"}
    try:
        try:
            with urlopen(Request(url, headers=headers), timeout=15) as response:
                sha = json.load(response).get("sha")
        except HTTPError as exc:
            if exc.code != 404:
                raise
            sha = None
        payload = {"message": "Publish latest completed PURGATORY research results", "content": base64.b64encode(path.read_bytes()).decode("ascii"), "branch": "main"}
        if sha:
            payload["sha"] = sha
        with urlopen(Request(url, data=json.dumps(payload).encode(), headers=headers, method="PUT"), timeout=25):
            log.info("Research report published to GitHub for website")
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        log.error("Research report publish failed: %s", exc)

def run_research():
    log.info("Starting historical research cycle")
    try:
        p = subprocess.run([sys.executable, "research_cycle.py"], timeout=RESEARCH_TIMEOUT, check=False)
        log.info("Research cycle exit code=%s", p.returncode)
        if p.returncode == 0:
            publish_report()
    except subprocess.TimeoutExpired:
        log.error("Research cycle timed out")

def main():
    # Begin immediately, then advance the full-US-universe research cursor
    # at most once per interval, including nights and weekends.
    run_research()
    last_research_slot = int(time.time() // (RESEARCH_INTERVAL * 60))
    while True:
        now = datetime.now(NY)
        if market_day(now) and clocktime(9, 30) <= now.time() < clocktime(16, 0):
            try:
                scan_once()
            except Exception:
                log.exception("Paper scan failed")
        slot = int(time.time() // (RESEARCH_INTERVAL * 60))
        if slot != last_research_slot:
            last_research_slot = slot
            run_research()
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
