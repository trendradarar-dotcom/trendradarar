from __future__ import annotations

import re
from typing import Any

from .ledger import GovernanceLedger, ArtifactRef, LedgerError


def _int_or_none(x: Any) -> int | None:
    try:
        return int(str(x))
    except Exception:
        return None


def parse_volume_bucket(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    raw=str(text).strip().upper().replace(",","")
    m=re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KMB])?\s*(\+)?",raw)
    if not m:
        return {"raw":text,"parse_state":"UNRESOLVED"}
    n=float(m.group(1)); unit=m.group(2); plus=bool(m.group(3))
    mult={None:1,"K":1_000,"M":1_000_000,"B":1_000_000_000}[unit]
    val=int(n*mult)
    return {
        "raw":text,
        "parse_state":"DETERMINED",
        "value_semantics":"LOWER_BOUND" if plus else "LITERAL_PARSED",
        "value":val,
        "open_upper_bound":plus,
    }


class SignalNormalizationService:
    def __init__(self, ledger: GovernanceLedger):
        self.ledger=ledger

    def from_source(self, source_state_id: str) -> ArtifactRef:
        src=self.ledger.get_state(source_state_id)
        if src["state_type"]!="SOURCE_RECORD":
            raise LedgerError("source_state_id must be SOURCE_RECORD")
        outer=src["payload"]
        p=outer.get("payload",{})
        connector=outer.get("connector") or outer.get("source_name")
        metrics=[]
        semantics=[]

        if connector=="youtube_data_api_v3":
            stats=p.get("statistics") or {}
            for key,name in [("viewCount","video_view_count"),("likeCount","video_like_count"),("commentCount","video_comment_count")]:
                val=_int_or_none(stats.get(key))
                if val is not None:
                    metrics.append({"metric":name,"value":val,"unit":"count","provider_literal":True})
            semantics.append("YouTube search membership/order is discovery only; no native trend popularity asserted")
        elif connector=="instagram_surface_snapshot":
            cols=p.get("source_columns") or {}

            def source_value(*names):
                wanted={x.lower().strip() for x in names}
                for k,v in cols.items():
                    if k and k.lower().strip() in wanted:
                        return v
                return None

            posts=_int_or_none(source_value("posts","post count","post_count"))
            views=_int_or_none(source_value("views","view count","view_count"))
            likes=_int_or_none(source_value("likes","like count","like_count"))

            if posts is not None:
                metrics.append({
                    "metric":"instagram_surface_posts",
                    "value":posts,
                    "unit":"count",
                    "provider_literal":True,
                })

            if views is not None:
                metrics.append({
                    "metric":"instagram_surface_views",
                    "value":views,
                    "unit":"count",
                    "provider_literal":True,
                })

            if likes is not None:
                metrics.append({
                    "metric":"instagram_surface_likes",
                    "value":likes,
                    "unit":"count",
                    "provider_literal":True,
                })

            semantics.append(
                "Instagram snapshot values are operator-captured provider-surface literals "
                "for the captured context; they are not a universal cross-platform trend score"
            )
            semantics.append(
                "Instagram post, view, and like counts remain source-surface observations "
                "and are not treated as equivalent cross-platform measures"
            )
            semantics.append(
                "Non-integer display values remain preserved in source_columns and are not "
                "numerically strengthened"
            )
        elif connector=="tiktok_creative_center_snapshot":
            cols=p.get("source_columns") or {}

            def source_value(*names):
                wanted={x.lower().strip() for x in names}
                for k,v in cols.items():
                    if k and k.lower().strip() in wanted:
                        return v
                return None

            rank=_int_or_none(source_value("rank"))
            posts=_int_or_none(source_value("posts","post count","post_count"))
            views=_int_or_none(source_value("views","view count","view_count"))

            if rank is not None:
                metrics.append({
                    "metric":"tiktok_creative_center_rank",
                    "value":rank,
                    "unit":"ordinal_position",
                    "provider_literal":True,
                })

            if posts is not None:
                metrics.append({
                    "metric":"tiktok_creative_center_posts",
                    "value":posts,
                    "unit":"count",
                    "provider_literal":True,
                })

            if views is not None:
                metrics.append({
                    "metric":"tiktok_creative_center_views",
                    "value":views,
                    "unit":"count",
                    "provider_literal":True,
                })

            semantics.append(
                "TikTok Creative Center snapshot values are provider-surface literals "
                "for the captured context; they are not a universal cross-platform trend score"
            )
            semantics.append(
                "TikTok Creative Center rank is an ordinal position within the captured "
                "surface/filter context, not a cardinal popularity value"
            )
            semantics.append(
                "Non-integer display values remain preserved in source_columns and are not "
                "numerically strengthened"
            )
        elif connector=="snapchat_spotlight_snapshot":
            cols=p.get("source_columns") or {}

            def source_value(*names):
                wanted={x.lower().strip() for x in names}
                for k,v in cols.items():
                    if k and k.lower().strip() in wanted:
                        return v
                return None

            rank=_int_or_none(source_value("rank","position"))
            views=_int_or_none(source_value("views","view count","viewcount"))

            if rank is not None:
                metrics.append({
                    "metric":"snapchat_spotlight_rank",
                    "value":rank,
                    "unit":"ordinal_position",
                    "provider_literal":True,
                })

            if views is not None:
                metrics.append({
                    "metric":"snapchat_spotlight_views",
                    "value":views,
                    "unit":"count",
                    "provider_literal":True,
                })

            semantics.append(
                "Snapchat Spotlight snapshot values are operator-captured provider-surface "
                "literals for the captured context; they are not a universal cross-platform "
                "trend score"
            )
            semantics.append(
                "Snapchat Spotlight rank is an ordinal position within the captured "
                "surface/filter context, not a cardinal popularity value"
            )
            semantics.append(
                "Snapchat Spotlight view counts remain source-surface observations and "
                "are not treated as equivalent cross-platform measures"
            )
            semantics.append(
                "Non-integer display values remain preserved in source_columns and are "
                "not numerically strengthened"
            )
        elif connector=="google_trends_trending_now_export":
            cols=p.get("source_columns") or {}
            volume=None
            for k,v in cols.items():
                if k and k.lower().strip() in {"search volume","volume","searches"}:
                    volume=parse_volume_bucket(v); break
            if volume:
                metrics.append({"metric":"google_trends_export_search_volume","value":volume,"unit":"source_bucket_semantics"})
            semantics.append("Export columns are preserved; parsed buckets do not become exact values beyond their source semantics")
        elif connector=="gdelt_doc_2":
            metrics.append({"metric":"gdelt_article_list_membership","value":1,"unit":"returned_item_membership","provider_literal":True})
            semantics.append("Article list membership is not independent evidence count, origin, truth, or trend popularity")
        else:
            # Generic source: no invented metrics.
            semantics.append("No connector-specific metric mapping available; no metric invented")

        return self.ledger.record_domain(
            "SIGNAL", "Signal Authority",
            {
                "source_state_id":source_state_id,
                "connector":connector,
                "metrics":metrics,
                "metric_semantics":semantics,
                "unknown_fields_not_inferred":True,
            },
            natural_key=f"signal:{source_state_id}",
            scope={k:p.get(k) for k in ("language","region","platform") if p.get(k) is not None},
            record_state="OBSERVED" if metrics else "NO_ASSERTABLE_METRIC",
            observed_at=src.get("observed_at"),
            upstream_states=[(source_state_id,"SIGNAL_FROM_SOURCE")],
        )
