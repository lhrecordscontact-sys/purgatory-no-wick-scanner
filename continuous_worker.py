"""Persistent research scheduler. PAPER/RESEARCH ONLY. Requires an always-on host.

POLL: every 60 seconds during RTH (paper scan uses its own market-hours guard).
RESEARCH: every 30 minutes during RTH; once after the close.
Runs are sequential; no overlapping data jobs or broker orders.
"""
import logging
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

def run_research():
    log.info("Starting historical research cycle")
    try:
        p = subprocess.run([sys.executable, "research_cycle.py"], timeout=RESEARCH_TIMEOUT, check=False)
        log.info("Research cycle exit code=%s", p.returncode)
    except subprocess.TimeoutExpired:
        log.error("Research cycle timed out")

def main():
    # Run one research cycle immediately on process start, including nights/weekends.
    # Subsequent cycles follow the normal market-hours schedule.
    startup_now = datetime.now(NY)
    run_research()
    last_research_slot = (startup_now.date().isoformat(),
                          (startup_now.hour * 60 + startup_now.minute) // RESEARCH_INTERVAL)
    last_close_day = startup_now.date() if startup_now.time() >= clocktime(16, 5) else None
    while True:
        now = datetime.now(NY)
        if market_day(now):
            if clocktime(9, 30) <= now.time() < clocktime(16, 0):
                try:
                    scan_once()
                except Exception:
                    log.exception("Paper scan failed")
                # Clock slots prevent research on every restart of the loop.
                slot = (now.date().isoformat(), (now.hour * 60 + now.minute) // RESEARCH_INTERVAL)
                if slot != last_research_slot:
                    last_research_slot = slot
                    run_research()
            elif now.time() >= clocktime(16, 5) and last_close_day != now.date():
                last_close_day = now.date()
                run_research()
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
