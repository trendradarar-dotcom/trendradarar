from __future__ import annotations

import argparse
import inspect
import logging
import os
from pathlib import Path
import socket
import time
from urllib.error import HTTPError, URLError

from .bootstrap import bootstrap_governance
from .connectors.google_trends_live import DEFAULT_MARKETS, GoogleTrendsLiveConnector
from .connectors.youtube_trending_live import YouTubeTrendingLiveConnector
from .db import init_db
from .ingest import IngestionService
from .ledger import GovernanceLedger
from .signals import SignalNormalizationService
from .live_promotion import promote_source


ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "trend_hunter.db"
LOG_DIR = Path(os.environ.get("LOCALAPPDATA", str(ROOT))) / "TrendHunter"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "auto_collector.log"
LOCK_PORT = 39091

# The hunter is global. Saudi Arabia has no discovery privilege here.
MARKETS = tuple(DEFAULT_MARKETS)

# Keep API pressure modest while still covering the world continuously.
DEFAULT_INTERVAL_SECONDS = 90
DEFAULT_BATCH_SIZE = 6
YOUTUBE_RESULTS_PER_MARKET = 15
GDELT_SEEDS_PER_CYCLE = 1


def _logger() -> logging.Logger:
    log = logging.getLogger("trend_hunter.auto_collect")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(fh)
    return log


def _acquire_singleton() -> socket.socket | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", LOCK_PORT))
        sock.listen(1)
        return sock
    except OSError:
        sock.close()
        return None


def _make_ingestion() -> IngestionService:
    init_db(str(DB))
    ledger = GovernanceLedger(str(DB))
    bootstrap_governance(ledger)
    return IngestionService(ledger)


def _ingest(ingestion: IngestionService, items, source_name: str) -> int:
    if not items:
        return 0

    refs = ingestion.ingest(items, source_name)

    ledger = getattr(ingestion, "ledger", None)
    if ledger is None:
        ledger = GovernanceLedger(str(DB))

    normalizer = SignalNormalizationService(ledger)
    normalized = 0
    promoted = 0

    for ref in refs:
        state_id = getattr(ref, "state_id", None)
        if state_id is None and isinstance(ref, dict):
            state_id = ref.get("state_id")

        if not state_id:
            logging.getLogger("trend_hunter.auto_collect").warning(
                "signal_normalization_skipped=true reason=missing_source_state_id source=%s",
                source_name,
            )
            continue

        try:
            signal_ref = normalizer.from_source(str(state_id))
            normalized += 1
        except Exception as exc:
            logging.getLogger("trend_hunter.auto_collect").warning(
                "signal_normalization_failed=true source=%s source_state_id=%s error=%r",
                source_name,
                state_id,
                exc,
            )
            continue

        try:
            promote_source(
                ledger,
                source_state_id=str(state_id),
                signal_state_id=str(signal_ref.state_id),
                source_name=source_name,
            )
            promoted += 1
        except Exception as exc:
            logging.getLogger("trend_hunter.auto_collect").warning(
                "live_promotion_failed=true source=%s source_state_id=%s signal_state_id=%s error=%r",
                source_name,
                state_id,
                getattr(signal_ref, "state_id", None),
                exc,
            )

    logging.getLogger("trend_hunter.auto_collect").info(
        "source_ingested=%d signals_normalized=%d opportunities_promoted=%d source=%s",
        len(refs),
        normalized,
        promoted,
        source_name,
    )
    return len(refs)


def _collect_google(ingestion: IngestionService, market: str, log: logging.Logger):
    c = GoogleTrendsLiveConnector(market)
    try:
        items = c.fetch()
        count = _ingest(ingestion, items, c.name)
        log.info("provider=google_trends scope=GLOBAL market=%s fetched=%d ingested=%d", market, len(items), count)
        return items
    except HTTPError as exc:
        log.warning("provider=google_trends market=%s http_status=%s operator_action_required=false", market, getattr(exc, "code", None))
    except URLError as exc:
        log.warning("provider=google_trends market=%s network_error=%s operator_action_required=false", market, exc)
    except Exception:
        log.exception("provider=google_trends market=%s failure operator_action_required=false", market)
    return []


def _collect_youtube(ingestion: IngestionService, market: str, log: logging.Logger) -> int:
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not key:
        log.warning("provider=youtube market=%s credential_missing=true operator_action_required=false", market)
        return 0
    c = YouTubeTrendingLiveConnector(key, market, max_results=YOUTUBE_RESULTS_PER_MARKET)
    try:
        items = c.fetch()
        count = _ingest(ingestion, items, c.name)
        log.info("provider=youtube scope=GLOBAL market=%s fetched=%d ingested=%d", market, len(items), count)
        return count
    except HTTPError as exc:
        log.warning("provider=youtube market=%s http_status=%s operator_action_required=false", market, getattr(exc, "code", None))
    except URLError as exc:
        log.warning("provider=youtube market=%s network_error=%s operator_action_required=false", market, exc)
    except Exception:
        log.exception("provider=youtube market=%s failure operator_action_required=false", market)
    return 0


def _make_gdelt(query: str):
    from .connectors.gdelt import GDELTConnector

    sig = inspect.signature(GDELTConnector)
    names = set(sig.parameters)
    if "query" in names:
        return GDELTConnector(query=query)
    if "q" in names:
        return GDELTConnector(q=query)
    return GDELTConnector(query)


def _collect_gdelt(ingestion: IngestionService, query: str, log: logging.Logger) -> int:
    q = str(query or "").strip()
    if not q:
        return 0
    try:
        c = _make_gdelt(q)
        items = c.fetch()
        count = _ingest(ingestion, items, c.name)
        log.info("provider=gdelt scope=GLOBAL query=%r fetched=%d ingested=%d", q[:120], len(items), count)
        return count
    except Exception as exc:
        text = str(exc)
        if "429" in text or "RATE" in text.upper() or "THROTTL" in text.upper():
            log.warning("provider=gdelt status=RATE_LIMITED query=%r operator_action_required=false", q[:120])
        else:
            log.exception("provider=gdelt failure query=%r operator_action_required=false", q[:120])
        return 0


def _title(item) -> str:
    try:
        return str((item.payload or {}).get("title") or "").strip()
    except Exception:
        return ""


def collect_once(markets: list[str]) -> dict[str, int]:
    log = _logger()
    ingestion = _make_ingestion()
    google_records = 0
    youtube_records = 0
    gdelt_records = 0
    seeds: list[str] = []

    for market in markets:
        google_items = _collect_google(ingestion, market, log)
        google_records += len(google_items)
        youtube_records += _collect_youtube(ingestion, market, log)
        for item in google_items[:2]:
            title = _title(item)
            if title:
                seeds.append(title)
        time.sleep(0.15)

    for q in seeds[:max(1, min(GDELT_SEEDS_PER_CYCLE, len(seeds)))]:
        gdelt_records += _collect_gdelt(ingestion, q, log)

    return {
        "markets_requested": len(markets),
        "google_trends_records": google_records,
        "youtube_records": youtube_records,
        "gdelt_records": gdelt_records,
    }


def run_forever(*, interval_seconds: int = DEFAULT_INTERVAL_SECONDS, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
    log = _logger()
    lock = _acquire_singleton()
    if lock is None:
        log.info("collector_already_running=true")
        return

    markets = list(MARKETS)
    ingestion = _make_ingestion()
    cursor = 0
    log.info(
        "collector_started=true scope=GLOBAL_MULTI_MARKET markets=%d interval_seconds=%d batch_size=%d operator_country_selection=false",
        len(markets), interval_seconds, batch_size,
    )
    try:
        while True:
            batch = [markets[(cursor + i) % len(markets)] for i in range(batch_size)]
            cursor = (cursor + batch_size) % len(markets)

            seeds: list[str] = []
            for market in batch:
                google_items = _collect_google(ingestion, market, log)
                _collect_youtube(ingestion, market, log)
                for item in google_items[:2]:
                    title = _title(item)
                    if title:
                        seeds.append(title)
                time.sleep(0.15)

            if seeds:
                _collect_gdelt(ingestion, seeds[0], log)

            time.sleep(max(30, int(interval_seconds)))
    finally:
        lock.close()


def main() -> int:
    p = argparse.ArgumentParser(prog="python -m trend_hunter.auto_collect")
    p.add_argument("--once", action="store_true")
    p.add_argument("--markets", default="")
    p.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS)
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    args = p.parse_args()

    markets = [x.strip().upper() for x in args.markets.split(",") if x.strip()] or list(MARKETS)

    if args.once:
        print(collect_once(markets))
        return 0

    run_forever(
        interval_seconds=max(30, args.interval_seconds),
        batch_size=max(1, min(args.batch_size, len(MARKETS))),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())