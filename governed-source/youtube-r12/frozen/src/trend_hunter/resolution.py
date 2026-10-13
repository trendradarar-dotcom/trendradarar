from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from .ledger import GovernanceLedger, LedgerError


def normalize_surface(text: str) -> str:
    text=unicodedata.normalize("NFKC",text).casefold()
    text=re.sub(r"[^\w\s]"," ",text,flags=re.UNICODE)
    text=re.sub(r"\s+"," ",text).strip()
    return text


@dataclass(frozen=True)
class SurfaceResolution:
    left_normalization_id: str
    right_normalization_id: str
    correspondence_id: str
    relation: str
    state: str


class ConservativeSurfaceResolver:
    """Meaning-preserving conservative resolver.

    Exact normalized surface equality can establish surface correspondence.
    Cross-language semantic equivalence is never guessed by this component.
    """
    def __init__(self, ledger: GovernanceLedger, methodology_version_id: str | None = None):
        self.ledger=ledger; self.methodology_version_id=methodology_version_id

    def compare_source_titles(self,left_state_id: str,right_state_id: str) -> SurfaceResolution:
        l=self.ledger.get_state(left_state_id); r=self.ledger.get_state(right_state_id)
        if l["state_type"]!="SOURCE_RECORD" or r["state_type"]!="SOURCE_RECORD":
            raise LedgerError("resolver expects SOURCE_RECORD states")
        lp=l["payload"].get("payload",{}); rp=r["payload"].get("payload",{})
        lt=lp.get("title"); rt=rp.get("title")
        if not lt or not rt:
            relation="UNRESOLVED"; state="UNRESOLVED"
            lnorm=""; rnorm=""
        else:
            lnorm=normalize_surface(str(lt)); rnorm=normalize_surface(str(rt))
            llang=lp.get("language"); rlang=rp.get("language")
            if lnorm==rnorm and lnorm:
                relation="SAME_NORMALIZED_SURFACE"; state="DETERMINED"
            elif llang and rlang and llang!=rlang:
                relation="CROSS_LANGUAGE_SEMANTIC_CORRESPONDENCE_UNRESOLVED"; state="UNRESOLVED"
            else:
                relation="NO_EXACT_SURFACE_CORRESPONDENCE"; state="DETERMINED"
        ln_id,ln=self.ledger.create_normalization(left_state_id,{"field":"title","normalized_surface":lnorm,"normalizer":"NFKC_CASEFOLD_WORDSPACE_V1"})
        rn_id,rn=self.ledger.create_normalization(right_state_id,{"field":"title","normalized_surface":rnorm,"normalizer":"NFKC_CASEFOLD_WORDSPACE_V1"})
        corr=self.ledger.create_correspondence(ln.state_id,rn.state_id,relation,judgment_state=state,methodology_version_id=self.methodology_version_id,evidence={"meaning_strengthening_forbidden":True})
        return SurfaceResolution(ln_id,rn_id,corr,relation,state)
