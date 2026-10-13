import json
import subprocess
import sys

import pytest

from trend_hunter.bootstrap import bootstrap_governance
from trend_hunter.db import init_db
from trend_hunter.ingest import IngestionService
from trend_hunter.ledger import GovernanceLedger
from trend_hunter.signals import SignalNormalizationService
from trend_hunter.connectors.tiktok_creative_center_snapshot import TikTokCreativeCenterSnapshotConnector
from trend_hunter.connectors.instagram_surface_snapshot import InstagramSurfaceSnapshotConnector
from trend_hunter.connectors.snapchat_spotlight_snapshot import SnapchatSpotlightSnapshotConnector


CASES = [
    (
        "tiktok",
        TikTokCreativeCenterSnapshotConnector,
        "Hashtag,Rank,Posts,Views\nAI,1,1200,500000\n",
        "tiktok_creative_center_snapshot",
        "ingest-tiktok-snapshot",
        {
            "tiktok_creative_center_rank": 1,
            "tiktok_creative_center_posts": 1200,
            "tiktok_creative_center_views": 500000,
        },
    ),
    (
        "instagram",
        InstagramSurfaceSnapshotConnector,
        "Hashtag,Posts,Views,Likes\nAI,850,320000,24000\n",
        "instagram_surface_snapshot",
        "ingest-instagram-snapshot",
        {
            "instagram_surface_posts": 850,
            "instagram_surface_views": 320000,
            "instagram_surface_likes": 24000,
        },
    ),
    (
        "snapchat",
        SnapchatSpotlightSnapshotConnector,
        "Topic,Rank,Views\nAI,1,500000\n",
        "snapchat_spotlight_snapshot",
        "ingest-snapchat-snapshot",
        {
            "snapchat_spotlight_rank": 1,
            "snapchat_spotlight_views": 500000,
        },
    ),]


@pytest.mark.parametrize(
    "platform,connector_cls,csv_text,connector_name,cli_cmd,expected",
    CASES,
)
def test_social_snapshot_to_signal(
    tmp_path,
    platform,
    connector_cls,
    csv_text,
    connector_name,
    cli_cmd,
    expected,
):
    csv_path = tmp_path / f"{platform}.csv"
    csv_path.write_text(csv_text, encoding="utf-8")

    connector = connector_cls(
        str(csv_path),
        region="SA",
        language="ar",
    )
    items = connector.fetch()

    assert len(items) == 1
    assert items[0].source_name == connector_name
    assert items[0].payload["platform"] == platform
    assert items[0].payload["region"] == "SA"
    assert items[0].payload["language"] == "ar"
    assert items[0].payload["origin_not_asserted"] is True
    assert items[0].payload["manual_snapshot"] is True

    db = tmp_path / f"{platform}.db"
    init_db(str(db))
    ledger = GovernanceLedger(str(db))
    bootstrap_governance(ledger)

    refs = IngestionService(ledger).ingest(
        items,
        connector.name,
    )
    assert len(refs) == 1

    source = ledger.get_state(refs[0].state_id)
    assert source["state_type"] == "SOURCE_RECORD"
    assert source["payload"]["connector"] == connector_name

    signal_ref = SignalNormalizationService(ledger).from_source(
        refs[0].state_id
    )
    signal = ledger.get_state(signal_ref.state_id)

    assert signal["state_type"] == "SIGNAL"

    metrics = {
        m["metric"]: m
        for m in signal["payload"]["metrics"]
    }

    for metric_name, expected_value in expected.items():
        assert metrics[metric_name]["value"] == expected_value
        assert metrics[metric_name]["provider_literal"] is True


@pytest.mark.parametrize(
    "platform,connector_cls,csv_text,connector_name,cli_cmd,expected",
    CASES,
)
def test_social_snapshot_cli(
    tmp_path,
    platform,
    connector_cls,
    csv_text,
    connector_name,
    cli_cmd,
    expected,
):
    csv_path = tmp_path / f"{platform}_cli.csv"
    csv_path.write_text(csv_text, encoding="utf-8")

    db = tmp_path / f"{platform}_cli.db"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "trend_hunter.cli",
            cli_cmd,
            str(csv_path),
            "--db",
            str(db),
            "--region",
            "SA",
            "--language",
            "ar",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )

    data = json.loads(result.stdout)

    assert len(data) == 1
    assert data[0]["version"] == 1
    assert data[0]["raw_hash"]
    assert data[0]["canonical_hash"]

    state = GovernanceLedger(str(db)).get_state(
        data[0]["state_id"]
    )

    assert state["state_type"] == "SOURCE_RECORD"
    assert state["payload"]["connector"] == connector_name