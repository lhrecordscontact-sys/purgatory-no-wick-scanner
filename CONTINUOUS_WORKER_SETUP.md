# Continuous PURGATORY worker (research only)

Run `python continuous_worker.py` on an **always-on** host. The worker invokes
the existing paper-only scanner about once per minute during market hours and
runs historical research every 30 minutes plus once after the close.

**Not deployed:** The existing `render.yaml` is a free web service, not a
persistent background worker. A paid Render background worker or another
always-on machine/service is required; do not assume the free web service runs
this worker. No hosting purchase or deployment is performed by this commit.

**Data limitation:** The current `scanner.get_bars` and `research_cycle.bars`
use Yahoo Finance, which is not a licensed guaranteed real-time feed. The
existing paper scanner works on 4-minute bars and may take longer than 60
seconds to complete; the polling interval is a minimum, not guaranteed
1-minute market-wide coverage. Historical research uses 5-minute stock bars,
not options bid/ask prices. For reliable 1-minute U.S. stock scanning, replace
the data source with a licensed feed and verify its coverage, entitlements,
timestamp handling, and cost.

**Persistence limitation:** The worker's `paper.db` and `reports/` files
are local. Attach persistent storage or publish snapshots to durable storage
before deploying; an ephemeral container will lose state on restart. Keep
live brokerage credentials out of this service.

**Schedule:** 9:30 AM–4 PM America/New_York weekdays (does not check
exchange holidays); post-close research after 4:05 PM. The worker prevents
overlapping work within one process. Do not run multiple replicas without a
distributed lock.

**Testing:** Verify the worker can start and research jobs finish within
resource limits. Existing GitHub Actions research schedule is separate and
remains enabled until the worker is actually deployed and validated.
