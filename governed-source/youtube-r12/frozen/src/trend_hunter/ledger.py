from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .db import tx, connect
from .util import canonical_json_bytes, hash_bytes, json_dumps, new_id, utcnow, ensure_dir


@dataclass(frozen=True)
class ArtifactRef:
    identity_id: str
    state_id: str
    version: int
    raw_hash: str
    canonical_hash: str | None


class LedgerError(RuntimeError):
    pass


class GovernanceLedger:
    def __init__(self, db_path: str, storage_dir: str | None = None):
        self.db_path = db_path
        self.storage_dir = storage_dir or str(Path(db_path).with_suffix("")) + "_objects"
        ensure_dir(self.storage_dir)

    def _object_ref(self, algorithm: str, digest: str) -> str:
        return f"object://{algorithm}/{digest}"

    def resolve_storage_ref(self, storage_ref: str, *, expected_algorithm: str | None = None) -> Path:
        """Resolve a governed logical object reference against this ledger's configured object-store root.

        Packaged states must be relocatable: content descriptors therefore persist logical/content-addressed
        references, never environment-specific absolute build paths. Legacy relative refs are accepted only
        when they resolve inside the configured object-store root; absolute paths are rejected.
        """
        if storage_ref.startswith("object://"):
            try:
                _, rest = storage_ref.split("object://", 1)
                algorithm, digest = rest.split("/", 1)
            except ValueError as exc:
                raise LedgerError(f"Invalid object storage reference: {storage_ref}") from exc
            if expected_algorithm and algorithm != expected_algorithm:
                raise LedgerError(f"Storage reference algorithm mismatch: {algorithm} != {expected_algorithm}")
            if algorithm != "sha256":
                raise LedgerError(f"Unsupported object storage algorithm: {algorithm}")
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
                raise LedgerError(f"Invalid content digest in storage reference: {storage_ref}")
            candidate = Path(self.storage_dir) / digest[:2] / digest
        else:
            p = Path(storage_ref)
            if p.is_absolute():
                raise LedgerError(f"Environment-specific absolute storage reference is not relocatable: {storage_ref}")
            candidate = Path(self.storage_dir) / p

        root = Path(self.storage_dir).resolve()
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise LedgerError(f"Storage reference escapes configured object store: {storage_ref}") from exc
        return resolved

    def _store_bytes(self, data: bytes, digest: str) -> str:
        sub = Path(self.storage_dir) / digest[:2]
        sub.mkdir(parents=True, exist_ok=True)
        path = sub / digest
        if not path.exists():
            path.write_bytes(data)
        return self._object_ref("sha256", digest)

    def create_canonicalization_profile(self, profile_key: str, version: int, rules: dict[str, Any]) -> str:
        pid = new_id("canon")
        with tx(self.db_path) as conn:
            conn.execute(
                "INSERT INTO canonicalization_profile(id,profile_key,version,rules_json,created_at) VALUES(?,?,?,?,?)",
                (pid, profile_key, version, json_dumps(rules), utcnow()),
            )
        return pid

    def get_or_create_identity(self, kind: str, natural_key: str | None = None, metadata: dict[str, Any] | None = None) -> str:
        with tx(self.db_path) as conn:
            if natural_key is not None:
                row = conn.execute(
                    "SELECT id FROM artifact_identity WHERE kind=? AND natural_key=?", (kind, natural_key)
                ).fetchone()
                if row:
                    return row["id"]
            iid = new_id("aid")
            conn.execute(
                "INSERT INTO artifact_identity(id,kind,natural_key,metadata_json,created_at) VALUES(?,?,?,?,?)",
                (iid, kind, natural_key, json_dumps(metadata or {}), utcnow()),
            )
            return iid

    def claim_youtube_private_authorization_once(self, authorization_state_id: str) -> None:
        """Durable fail-closed one-use authorization claim before any YouTube side effect.

        The existing append-only artifact_identity unique(kind,natural_key) index
        provides the cross-thread/process arbitration; no schema migration needed.
        """
        if not authorization_state_id:
            raise LedgerError("YouTube publication authorization is required")
        with tx(self.db_path) as conn:
            # Migration-safe: legacy attempts, proofs and executions already consume
            # authorization, even if their one-use claim predates this candidate.
            previous = conn.execute(
                """SELECT 1 FROM artifact_state
                   WHERE state_type IN ('YOUTUBE_PUBLICATION_ATTEMPT',
                                        'YOUTUBE_PUBLICATION_PROOF',
                                        'PUBLICATION_EXECUTION')
                     AND json_valid(payload_json)
                     AND json_extract(payload_json, '$.authorization_state_id')=?
                   LIMIT 1""",
                (authorization_state_id,),
            ).fetchone()
            if previous:
                raise LedgerError("YouTube authorization already consumed or requires manual reconciliation")
            try:
                conn.execute(
                    """INSERT INTO artifact_identity
                       (id,kind,natural_key,metadata_json,created_at)
                       VALUES(?,?,?,?,?)""",
                    (new_id("aid"), "YOUTUBE_PRIVATE_UPLOAD_ONCE",
                     authorization_state_id, '{}', utcnow()),
                )
            except sqlite3.IntegrityError as exc:
                raise LedgerError(
                    "YouTube authorization already claimed; automatic replay is forbidden"
                ) from exc

    def assert_youtube_private_authorization_available(self, authorization_state_id: str) -> None:
        """Early read-only replay preflight (the atomic claim remains authoritative)."""
        with connect(self.db_path) as conn:
            claimed = conn.execute(
                "SELECT 1 FROM artifact_identity WHERE kind='YOUTUBE_PRIVATE_UPLOAD_ONCE' AND natural_key=?",
                (authorization_state_id,),
            ).fetchone()
            previous = conn.execute(
                """SELECT 1 FROM artifact_state
                   WHERE state_type IN ('YOUTUBE_PUBLICATION_ATTEMPT',
                                        'YOUTUBE_PUBLICATION_PROOF','PUBLICATION_EXECUTION')
                     AND json_valid(payload_json)
                     AND json_extract(payload_json, '$.authorization_state_id')=?
                   LIMIT 1""",
                (authorization_state_id,),
            ).fetchone()
        if claimed or previous:
            raise LedgerError("YouTube authorization already used or requires manual reconciliation")

    def claim_youtube_private_provider_once(self, publication_attempt_state_id: str) -> None:
        """Atomically admit exactly one provider upload per READY attempt.

        Committed before external upload. Crash/UNKNOWN is a permanent automatic HOLD.
        """
        with tx(self.db_path) as conn:
            attempt = conn.execute(
                """SELECT identity_id,payload_json FROM artifact_state
                   WHERE id=? AND state_type='YOUTUBE_PUBLICATION_ATTEMPT'""",
                (publication_attempt_state_id,),
            ).fetchone()
            if not attempt:
                raise LedgerError("Unknown YouTube publication attempt")
            payload = json.loads(attempt["payload_json"])
            if payload.get("status") != "READY_PRIVATE_UPLOAD":
                raise LedgerError("YouTube provider claim requires READY_PRIVATE_UPLOAD")
            latest = conn.execute(
                "SELECT id FROM artifact_state WHERE identity_id=? ORDER BY version DESC LIMIT 1",
                (attempt["identity_id"],),
            ).fetchone()
            if not latest or latest["id"] != publication_attempt_state_id:
                raise LedgerError("YouTube publication attempt stale/superseded")
            auth_id = str(payload.get("authorization_state_id") or "")
            claim = conn.execute(
                """SELECT 1 FROM artifact_identity
                   WHERE kind='YOUTUBE_PRIVATE_UPLOAD_ONCE' AND natural_key=?""",
                (auth_id,),
            ).fetchone()
            if not claim:
                raise LedgerError("YouTube provider attempt lacks durable authorization claim")
            try:
                conn.execute(
                    """INSERT INTO artifact_identity
                       (id,kind,natural_key,metadata_json,created_at) VALUES(?,?,?,?,?)""",
                    (new_id("aid"), "YOUTUBE_PRIVATE_PROVIDER_ONCE",
                     publication_attempt_state_id, '{}', utcnow()),
                )
            except sqlite3.IntegrityError as exc:
                raise LedgerError("YouTube provider attempt already claimed; automatic retry forbidden") from exc

    def create_state(
        self,
        identity_id: str,
        state_type: str,
        payload: dict[str, Any],
        *,
        raw_bytes: bytes | None = None,
        canonicalization_profile_id: str | None = None,
        status: str = "COMMITTED",
        effective_from: str | None = None,
        effective_to: str | None = None,
        source_asserted_at: str | None = None,
        observed_at: str | None = None,
        supersedes_state_id: str | None = None,
    ) -> ArtifactRef:
        canonical_bytes = canonical_json_bytes(payload)
        if raw_bytes is None:
            raw_bytes = canonical_bytes
        raw_hash = hash_bytes(raw_bytes)
        canonical_hash = hash_bytes(canonical_bytes)
        raw_ref = self._store_bytes(raw_bytes, raw_hash)
        canonical_ref = self._store_bytes(canonical_bytes, canonical_hash)
        descriptor_id = new_id("cd")
        state_id = new_id("ast")
        now = utcnow()
        with tx(self.db_path) as conn:
            if not conn.execute("SELECT 1 FROM artifact_identity WHERE id=?", (identity_id,)).fetchone():
                raise LedgerError(f"Unknown artifact identity: {identity_id}")
            row = conn.execute("SELECT COALESCE(MAX(version),0)+1 AS v FROM artifact_state WHERE identity_id=?", (identity_id,)).fetchone()
            version = int(row["v"])
            conn.execute(
                """INSERT INTO content_descriptor(
                    id,raw_hash_algorithm,raw_hash,raw_size_bytes,raw_storage_ref,
                    canonical_hash_algorithm,canonical_hash,canonicalization_profile_id,canonical_storage_ref,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (descriptor_id, "sha256", raw_hash, len(raw_bytes), raw_ref, "sha256", canonical_hash,
                 canonicalization_profile_id, canonical_ref, now),
            )
            conn.execute(
                """INSERT INTO artifact_state(
                    id,identity_id,version,state_type,content_descriptor_id,payload_json,status,
                    recorded_at,committed_at,effective_from,effective_to,source_asserted_at,observed_at,supersedes_state_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (state_id, identity_id, version, state_type, descriptor_id, json_dumps(payload), status,
                 now, now, effective_from, effective_to, source_asserted_at, observed_at, supersedes_state_id),
            )
        return ArtifactRef(identity_id, state_id, version, raw_hash, canonical_hash)

    def get_state(self, state_id: str) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                """SELECT s.*, d.raw_hash,d.raw_hash_algorithm,d.raw_storage_ref,d.canonical_hash,
                          d.canonical_hash_algorithm,d.canonical_storage_ref,d.canonicalization_profile_id,
                          i.kind,i.natural_key
                   FROM artifact_state s
                   JOIN content_descriptor d ON d.id=s.content_descriptor_id
                   JOIN artifact_identity i ON i.id=s.identity_id
                   WHERE s.id=?""", (state_id,)
            ).fetchone()
            if not row:
                raise LedgerError(f"Unknown state: {state_id}")
            d = dict(row)
            d["payload"] = json.loads(d.pop("payload_json"))
            return d

    def get_latest_state_by_natural_key(
        self,
        kind: str,
        natural_key: str,
    ) -> dict[str, Any] | None:
        """Return the newest state for an existing governed identity without creating it."""
        kind = str(kind or "").strip()
        natural_key = str(natural_key or "").strip()
        if not kind or not natural_key:
            raise LedgerError("kind and natural_key are required")

        with connect(self.db_path) as conn:
            identity = conn.execute(
                "SELECT id FROM artifact_identity WHERE kind=? AND natural_key=?",
                (kind, natural_key),
            ).fetchone()
            if not identity:
                return None

            row = conn.execute(
                "SELECT id FROM artifact_state WHERE identity_id=? "
                "ORDER BY version DESC LIMIT 1",
                (identity["id"],),
            ).fetchone()

        if not row:
            return None
        return self.get_state(row["id"])

    def subject_identity_for_state(self, state_id: str) -> str:
        """Return the governed semantic subject identity, not merely the record artifact identity."""
        st = self.get_state(state_id)
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT subject_identity_id FROM domain_record WHERE artifact_state_id=?", (state_id,)).fetchone()
            if row and row["subject_identity_id"]:
                return row["subject_identity_id"]
        return st["identity_id"]

    def add_provenance(self, from_state_id: str, to_state_id: str, edge_type: str, *, materially_consumed: bool = True, metadata: dict[str, Any] | None = None) -> str:
        eid = new_id("prov")
        with tx(self.db_path) as conn:
            conn.execute(
                "INSERT INTO provenance_edge(id,from_state_id,to_state_id,edge_type,materially_consumed,metadata_json,created_at) VALUES(?,?,?,?,?,?,?)",
                (eid, from_state_id, to_state_id, edge_type, int(materially_consumed), json_dumps(metadata or {}), utcnow()),
            )
        return eid

    def create_contract(self, contract_key: str, version: int, payload: dict[str, Any], *, status: str = "ACTIVE", effective_from: str | None = None, effective_to: str | None = None) -> str:
        identity = self.get_or_create_identity("GOVERNANCE_CONTRACT", contract_key)
        state = self.create_state(identity, "GOVERNANCE_CONTRACT_VERSION", payload, effective_from=effective_from, effective_to=effective_to)
        cid = new_id("gcv")
        with tx(self.db_path) as conn:
            conn.execute(
                "INSERT INTO governance_contract_version(id,contract_key,version,artifact_state_id,status,effective_from,effective_to,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (cid, contract_key, version, state.state_id, status, effective_from, effective_to, utcnow()),
            )
        return cid

    def get_contract_version(self, contract_key: str, version: int) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                """SELECT g.*, s.content_descriptor_id, d.raw_hash, d.canonical_hash
                   FROM governance_contract_version g
                   JOIN artifact_state s ON s.id=g.artifact_state_id
                   JOIN content_descriptor d ON d.id=s.content_descriptor_id
                   WHERE g.contract_key=? AND g.version=?""",
                (contract_key, version),
            ).fetchone()
            if not row:
                raise LedgerError(f"Unknown governance contract version: {contract_key}@V{version}")
            return dict(row)

    def bind_contract_reference(self, parent_contract_version_id: str, reference_role: str, child_contract_version_id: str) -> None:
        with tx(self.db_path) as conn:
            child = conn.execute(
                """SELECT g.artifact_state_id,d.raw_hash,d.canonical_hash
                   FROM governance_contract_version g
                   JOIN artifact_state s ON s.id=g.artifact_state_id
                   JOIN content_descriptor d ON d.id=s.content_descriptor_id
                   WHERE g.id=?""",
                (child_contract_version_id,),
            ).fetchone()
            if not child:
                raise LedgerError(f"Unknown child contract version: {child_contract_version_id}")
            if not conn.execute("SELECT 1 FROM governance_contract_version WHERE id=?", (parent_contract_version_id,)).fetchone():
                raise LedgerError(f"Unknown parent contract version: {parent_contract_version_id}")
            existing = conn.execute(
                "SELECT * FROM governance_contract_reference WHERE parent_contract_version_id=? AND reference_role=? AND child_contract_version_id=?",
                (parent_contract_version_id, reference_role, child_contract_version_id),
            ).fetchone()
            if existing:
                if (existing["child_artifact_state_id"] != child["artifact_state_id"] or
                    existing["exact_raw_hash"] != child["raw_hash"] or
                    (existing["exact_canonical_hash"] or "") != (child["canonical_hash"] or "")):
                    raise LedgerError("Existing contract reference does not match exact pinned child state")
                return
            conn.execute(
                """INSERT INTO governance_contract_reference(
                       parent_contract_version_id,reference_role,child_contract_version_id,child_artifact_state_id,
                       exact_raw_hash,exact_canonical_hash,created_at
                   ) VALUES(?,?,?,?,?,?,?)""",
                (parent_contract_version_id, reference_role, child_contract_version_id, child["artifact_state_id"],
                 child["raw_hash"], child["canonical_hash"], utcnow()),
            )

    def create_methodology(self, methodology_key: str, version: int, payload: dict[str, Any], *, status: str = "FROZEN") -> str:
        identity = self.get_or_create_identity("METHODOLOGY", methodology_key)
        state = self.create_state(identity, "METHODOLOGY_VERSION", payload)
        mid = new_id("meth")
        with tx(self.db_path) as conn:
            conn.execute(
                "INSERT INTO methodology_version(id,methodology_key,version,artifact_state_id,status,created_at) VALUES(?,?,?,?,?,?)",
                (mid, methodology_key, version, state.state_id, status, utcnow()),
            )
        return mid

    def create_audit_corpus(self, methodology_version_id: str, item_state_ids: list[str], review_boundary: dict[str, Any]) -> str:
        # Corpus identity is over ordered immutable state ids + hashes, not mutable aliases.
        items: list[dict[str, str]] = []
        for sid in sorted(item_state_ids):
            st = self.get_state(sid)
            items.append({"state_id": sid, "raw_hash": st["raw_hash"], "canonical_hash": st["canonical_hash"]})
        corpus_hash = hash_bytes(canonical_json_bytes({"items": items, "boundary": review_boundary}))
        cid = new_id("corpus")
        with tx(self.db_path) as conn:
            conn.execute(
                """INSERT INTO audit_corpus_snapshot(
                    id,methodology_version_id,review_boundary_json,item_ids_json,item_count,corpus_hash_algorithm,corpus_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (cid, methodology_version_id, json_dumps(review_boundary), json_dumps(items), len(items), "sha256", corpus_hash, utcnow()),
            )
        return cid

    def create_normalization(self, source_state_id: str, normalized_payload: dict[str, Any], *, mapping_contract_id: str | None = None, assertion_state: str = "ASSERTED", rationale: dict[str, Any] | None = None) -> tuple[str, ArtifactRef]:
        self.get_state(source_state_id)
        identity = self.get_or_create_identity("NORMALIZED_REPRESENTATION", f"norm:{source_state_id}:{hash_bytes(canonical_json_bytes(normalized_payload))}")
        normalized = self.create_state(identity, "NORMALIZED_REPRESENTATION", normalized_payload)
        nid = new_id("norm")
        assertion_payload = {
            "normalization_assertion_id": nid,
            "source_state_id": source_state_id,
            "normalized_state_id": normalized.state_id,
            "mapping_contract_id": mapping_contract_id,
            "assertion_state": assertion_state,
            "rationale": rationale or {},
            "meaning_preserving_required": True,
            "provenance_preserving_required": True,
        }
        assertion_identity = self.get_or_create_identity("NORMALIZATION_ASSERTION", f"norm-assert:{nid}")
        assertion_artifact = self.create_state(assertion_identity, "NORMALIZATION_ASSERTION", assertion_payload)
        with tx(self.db_path) as conn:
            conn.execute(
                "INSERT INTO normalization_assertion(id,source_state_id,normalized_state_id,mapping_contract_id,assertion_state,rationale_json,created_at) VALUES(?,?,?,?,?,?,?)",
                (nid, source_state_id, normalized.state_id, mapping_contract_id, assertion_state, json_dumps(rationale or {}), utcnow()),
            )
            conn.execute(
                "INSERT INTO normalization_assertion_artifact(normalization_assertion_id,artifact_state_id,created_at) VALUES(?,?,?)",
                (nid, assertion_artifact.state_id, utcnow()),
            )
        self.add_provenance(source_state_id, normalized.state_id, "NORMALIZED_FROM", materially_consumed=True)
        self.add_provenance(source_state_id, assertion_artifact.state_id, "NORMALIZATION_ASSERTS_SOURCE", materially_consumed=True)
        self.add_provenance(normalized.state_id, assertion_artifact.state_id, "NORMALIZATION_ASSERTS_RESULT", materially_consumed=True)
        return nid, normalized

    def normalization_assertion_artifact_state(self, normalization_assertion_id: str) -> str:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT artifact_state_id FROM normalization_assertion_artifact WHERE normalization_assertion_id=?", (normalization_assertion_id,)).fetchone()
            if not row:
                raise LedgerError(f"No immutable artifact state for normalization assertion: {normalization_assertion_id}")
            return row["artifact_state_id"]

    def create_correspondence(self, left_state_id: str, right_state_id: str, relation: str, *, judgment_state: str = "DETERMINED", methodology_version_id: str | None = None, evidence: dict[str, Any] | None = None) -> str:
        self.get_state(left_state_id); self.get_state(right_state_id)
        cid = new_id("corr")
        payload = {
            "correspondence_judgment_id": cid,
            "left_state_id": left_state_id,
            "right_state_id": right_state_id,
            "relation": relation,
            "judgment_state": judgment_state,
            "methodology_version_id": methodology_version_id,
            "evidence": evidence or {},
        }
        identity = self.get_or_create_identity("CORRESPONDENCE_JUDGMENT", f"corr:{cid}")
        artifact = self.create_state(identity, "CORRESPONDENCE_JUDGMENT", payload)
        with tx(self.db_path) as conn:
            conn.execute(
                "INSERT INTO correspondence_judgment(id,left_state_id,right_state_id,relation,judgment_state,methodology_version_id,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (cid, left_state_id, right_state_id, relation, judgment_state, methodology_version_id, json_dumps(evidence or {}), utcnow()),
            )
            conn.execute(
                "INSERT INTO correspondence_judgment_artifact(correspondence_judgment_id,artifact_state_id,created_at) VALUES(?,?,?)",
                (cid, artifact.state_id, utcnow()),
            )
        self.add_provenance(left_state_id, artifact.state_id, "CORRESPONDENCE_LEFT_INPUT", materially_consumed=True)
        self.add_provenance(right_state_id, artifact.state_id, "CORRESPONDENCE_RIGHT_INPUT", materially_consumed=True)
        return cid

    def correspondence_judgment_artifact_state(self, correspondence_judgment_id: str) -> str:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT artifact_state_id FROM correspondence_judgment_artifact WHERE correspondence_judgment_id=?", (correspondence_judgment_id,)).fetchone()
            if not row:
                raise LedgerError(f"No immutable artifact state for correspondence judgment: {correspondence_judgment_id}")
            return row["artifact_state_id"]

    def create_target(self, target_key: str, proposition_type: str, *, subject_identity_id: str | None = None, semantic_scope: dict[str, Any] | None = None, time_basis: dict[str, Any] | None = None, applicability: dict[str, Any] | None = None, authority_role: str | None = None) -> str:
        semantic_scope = semantic_scope or {}
        time_basis = time_basis or {}
        applicability = applicability or {}
        canonical_target = {
            "proposition_type": proposition_type,
            "subject_identity_id": subject_identity_id,
            "semantic_scope": semantic_scope,
            "time_basis": time_basis,
            "applicability": applicability,
            "authority_role": authority_role,
        }
        target_hash = hash_bytes(canonical_json_bytes(canonical_target))
        canonical_target_json = json_dumps(canonical_target)
        with tx(self.db_path) as conn:
            existing = conn.execute("SELECT * FROM adjudication_target WHERE target_key=?", (target_key,)).fetchone()
            if existing:
                tid = existing["id"]
                fp = conn.execute("SELECT * FROM adjudication_target_fingerprint WHERE target_id=?", (tid,)).fetchone()
                if fp:
                    if fp["target_hash"] != target_hash:
                        raise LedgerError("Adjudication target key reused for a semantically different governed target")
                else:
                    # Legacy target: validate its stored coordinates before adding the immutable fingerprint.
                    legacy = {
                        "proposition_type": existing["proposition_type"],
                        "subject_identity_id": existing["subject_identity_id"],
                        "semantic_scope": json.loads(existing["semantic_scope_json"]),
                        "time_basis": json.loads(existing["time_basis_json"]),
                        "applicability": json.loads(existing["applicability_json"]),
                        "authority_role": authority_role,
                    }
                    if hash_bytes(canonical_json_bytes(legacy)) != target_hash:
                        raise LedgerError("Legacy adjudication target key reused with incompatible coordinates")
                    conn.execute(
                        "INSERT INTO adjudication_target_fingerprint(target_id,authority_role,target_hash_algorithm,target_hash,canonical_target_json,created_at) VALUES(?,?,?,?,?,?)",
                        (tid, authority_role, "sha256", target_hash, canonical_target_json, utcnow()),
                    )
                return tid
            tid = new_id("target")
            conn.execute(
                "INSERT INTO adjudication_target(id,target_key,proposition_type,subject_identity_id,semantic_scope_json,time_basis_json,applicability_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (tid, target_key, proposition_type, subject_identity_id, json_dumps(semantic_scope), json_dumps(time_basis), json_dumps(applicability), utcnow()),
            )
            conn.execute(
                "INSERT INTO adjudication_target_fingerprint(target_id,authority_role,target_hash_algorithm,target_hash,canonical_target_json,created_at) VALUES(?,?,?,?,?,?)",
                (tid, authority_role, "sha256", target_hash, canonical_target_json, utcnow()),
            )
        return tid

    def create_evidentiary_entitlement(self, record_state_id: str, target_id: str, *, entitlement_state: str, proposition_strength: str, methodology_version_id: str | None = None, basis: dict[str, Any] | None = None) -> tuple[str, ArtifactRef]:
        if entitlement_state not in {"ENTITLED", "NOT_ENTITLED", "UNRESOLVED"}:
            raise LedgerError("Invalid evidentiary entitlement state")
        self.get_state(record_state_id)
        payload = {
            "record_state_id": record_state_id,
            "target_id": target_id,
            "methodology_version_id": methodology_version_id,
            "entitlement_state": entitlement_state,
            "proposition_strength": proposition_strength,
            "basis": basis or {},
            "proposition_relative": True,
        }
        identity = self.get_or_create_identity("EVIDENTIARY_ENTITLEMENT", f"ent:{record_state_id}:{target_id}:{proposition_strength}:{hash_bytes(canonical_json_bytes(basis or {}))}")
        artifact = self.create_state(identity, "EVIDENTIARY_ENTITLEMENT", payload)
        eid = new_id("ent")
        with tx(self.db_path) as conn:
            conn.execute(
                """INSERT INTO evidentiary_entitlement(
                    id,record_state_id,target_id,methodology_version_id,entitlement_state,proposition_strength,basis_json,artifact_state_id,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (eid, record_state_id, target_id, methodology_version_id, entitlement_state, proposition_strength,
                 json_dumps(basis or {}), artifact.state_id, utcnow()),
            )
        self.add_provenance(record_state_id, artifact.state_id, "ENTITLEMENT_EVALUATES_RECORD", materially_consumed=True)
        return eid, artifact

    def create_adjudication(self, target_id: str, methodology_version_id: str, corpus_snapshot_id: str, decision_state: str, decision_payload: dict[str, Any], consumed_state_ids: list[tuple[str, str]], *, consumed_normalization_assertion_ids: list[str] | None = None, consumed_correspondence_judgment_ids: list[str] | None = None, consumed_entitlement_ids: list[str] | None = None, integrity_status: str = "VALID") -> str:
        # Every consumed item is converted to an exact immutable ArtifactState and its hashes are pinned.
        consumed: list[tuple[str, str]] = list(consumed_state_ids)
        for nid in consumed_normalization_assertion_ids or []:
            consumed.append((self.normalization_assertion_artifact_state(nid), "NORMALIZATION_ASSERTION"))
        for cid in consumed_correspondence_judgment_ids or []:
            consumed.append((self.correspondence_judgment_artifact_state(cid), "CORRESPONDENCE_JUDGMENT"))
        with connect(self.db_path) as conn:
            for eid in consumed_entitlement_ids or []:
                row = conn.execute("SELECT artifact_state_id,target_id,entitlement_state FROM evidentiary_entitlement WHERE id=?", (eid,)).fetchone()
                if not row:
                    raise LedgerError(f"Unknown evidentiary entitlement: {eid}")
                if row["target_id"] != target_id:
                    raise LedgerError("Evidentiary entitlement belongs to a different adjudication target")
                if row["entitlement_state"] != "ENTITLED":
                    raise LedgerError("Only ENTITLED proposition-relative evidence may be consumed as proof")
                consumed.append((row["artifact_state_id"], "EVIDENTIARY_ENTITLEMENT"))
        # De-duplicate exact role/state pairs while preserving order.
        dedup: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for pair in consumed:
            if pair not in seen:
                seen.add(pair); dedup.append(pair)
        aid = new_id("adj")
        now = utcnow()
        with tx(self.db_path) as conn:
            if not conn.execute("SELECT 1 FROM adjudication_target WHERE id=?", (target_id,)).fetchone():
                raise LedgerError("Unknown adjudication target")
            prior = conn.execute(
                "SELECT current_adjudication_id FROM current_view_projection WHERE projection_key=?",
                (f"adjudication:{target_id}",),
            ).fetchone()
            prior_id = prior["current_adjudication_id"] if prior else None
            conn.execute(
                "INSERT INTO adjudication(id,target_id,methodology_version_id,corpus_snapshot_id,decision_state,decision_payload_json,integrity_status,recorded_at,committed_at,prior_current_adjudication_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (aid, target_id, methodology_version_id, corpus_snapshot_id, decision_state, json_dumps(decision_payload), integrity_status, now, now, prior_id),
            )
            for sid, role in dedup:
                row = conn.execute(
                    """SELECT d.raw_hash,d.canonical_hash FROM artifact_state s JOIN content_descriptor d ON d.id=s.content_descriptor_id WHERE s.id=?""",
                    (sid,),
                ).fetchone()
                if not row:
                    raise LedgerError(f"Unknown consumed artifact state: {sid}")
                conn.execute(
                    "INSERT INTO adjudication_consumed_artifact(adjudication_id,artifact_state_id,consumption_role,exact_raw_hash,exact_canonical_hash) VALUES(?,?,?,?,?)",
                    (aid, sid, role, row["raw_hash"], row["canonical_hash"]),
                )
            # Current view is derived and keyed by the immutable governed adjudication target.
            conn.execute(
                """INSERT INTO current_view_projection(projection_key,target_type,target_id,current_adjudication_id,rebuilt_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(projection_key) DO UPDATE SET current_adjudication_id=excluded.current_adjudication_id, rebuilt_at=excluded.rebuilt_at""",
                (f"adjudication:{target_id}", "ADJUDICATION_TARGET", target_id, aid, now),
            )
        return aid

    def add_authority_grant(self, grantee_type: str, grantee_key: str, scope: dict[str, Any], *, can_delegate: bool, root_basis_state_id: str | None, effective_from: str, effective_to: str | None = None) -> str:
        gid = new_id("grant")
        with tx(self.db_path) as conn:
            conn.execute(
                "INSERT INTO governance_authority_grant(id,grantee_type,grantee_key,scope_json,can_delegate,root_basis_state_id,effective_from,effective_to,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (gid, grantee_type, grantee_key, json_dumps(scope), int(can_delegate), root_basis_state_id, effective_from, effective_to, utcnow()),
            )
        return gid

    @staticmethod
    def _scope_subset(child: Any, parent: Any) -> bool:
        if isinstance(parent, dict) and isinstance(child, dict):
            for k, v in child.items():
                if k not in parent:
                    return False
                if not GovernanceLedger._scope_subset(v, parent[k]):
                    return False
            return True
        if isinstance(parent, list) and isinstance(child, list):
            return set(map(json_dumps, child)).issubset(set(map(json_dumps, parent)))
        if parent == "*":
            return True
        return child == parent

    def add_delegation(self, delegator_grant_id: str, delegatee_grant_id: str, delegated_scope: dict[str, Any], *, effective_from: str, effective_to: str | None = None) -> str:
        with tx(self.db_path) as conn:
            delegator = conn.execute("SELECT * FROM governance_authority_grant WHERE id=?", (delegator_grant_id,)).fetchone()
            delegatee = conn.execute("SELECT * FROM governance_authority_grant WHERE id=?", (delegatee_grant_id,)).fetchone()
            if not delegator or not delegatee:
                raise LedgerError("Unknown grant")
            if not delegator["can_delegate"]:
                raise LedgerError("Delegator lacks authority to delegate")
            parent_scope = json.loads(delegator["scope_json"])
            child_scope = json.loads(delegatee["scope_json"])
            if not self._scope_subset(delegated_scope, parent_scope):
                raise LedgerError("Delegated scope exceeds delegator competence")
            if not self._scope_subset(delegated_scope, child_scope):
                raise LedgerError("Delegated scope exceeds delegatee declared scope")
            if not self._time_within(effective_from, effective_to, delegator["effective_from"], delegator["effective_to"]):
                raise LedgerError("Delegation effectivity exceeds delegator authority interval")
            if not self._time_within(effective_from, effective_to, delegatee["effective_from"], delegatee["effective_to"]):
                raise LedgerError("Delegation effectivity exceeds delegatee grant interval")
            # Cycle check in grant graph.
            graph: dict[str, list[str]] = {}
            for row in conn.execute("SELECT delegator_grant_id,delegatee_grant_id FROM delegation_edge"):
                graph.setdefault(row["delegator_grant_id"], []).append(row["delegatee_grant_id"])
            graph.setdefault(delegator_grant_id, []).append(delegatee_grant_id)
            stack = [delegatee_grant_id]
            seen = set()
            while stack:
                node = stack.pop()
                if node == delegator_grant_id:
                    raise LedgerError("Circular delegation is forbidden")
                if node in seen:
                    continue
                seen.add(node)
                stack.extend(graph.get(node, []))
            did = new_id("deleg")
            conn.execute(
                "INSERT INTO delegation_edge(id,delegator_grant_id,delegatee_grant_id,delegated_scope_json,effective_from,effective_to,created_at) VALUES(?,?,?,?,?,?,?)",
                (did, delegator_grant_id, delegatee_grant_id, json_dumps(delegated_scope), effective_from, effective_to, utcnow()),
            )
        return did

    @staticmethod
    def _time_within(child_from: str, child_to: str | None, parent_from: str, parent_to: str | None) -> bool:
        if child_from < parent_from:
            return False
        if parent_to is not None and (child_to is None or child_to > parent_to):
            return False
        return True

    def validate_competence_chain(self, grant_id: str, exact_scope: dict[str, Any], *, at_time: str) -> tuple[bool, str]:
        """Validate exact-scope competence through an acyclic, effectivity-bound chain to a root basis."""
        with connect(self.db_path) as conn:
            current = grant_id
            visited: set[str] = set()
            requested = exact_scope
            while True:
                if current in visited:
                    return False, "circular authority chain"
                visited.add(current)
                grant = conn.execute("SELECT * FROM governance_authority_grant WHERE id=?", (current,)).fetchone()
                if not grant:
                    return False, "unknown authority grant"
                if not (grant["effective_from"] <= at_time and (grant["effective_to"] is None or at_time < grant["effective_to"])):
                    return False, "authority grant not effective at requested time"
                if not self._scope_subset(requested, json.loads(grant["scope_json"])):
                    return False, "requested semantic scope exceeds grant competence"
                parent_edge = conn.execute(
                    "SELECT * FROM delegation_edge WHERE delegatee_grant_id=? AND effective_from<=? AND (effective_to IS NULL OR ?<effective_to) ORDER BY created_at DESC LIMIT 1",
                    (current, at_time, at_time),
                ).fetchone()
                if parent_edge:
                    if not self._scope_subset(requested, json.loads(parent_edge["delegated_scope_json"])):
                        return False, "requested semantic scope exceeds delegated scope"
                    current = parent_edge["delegator_grant_id"]
                    continue
                if grant["root_basis_state_id"]:
                    try:
                        self.get_state(grant["root_basis_state_id"])
                    except LedgerError:
                        return False, "root governance basis is not verifiable"
                    return True, "competence chain reaches immutable root governance basis"
                return False, "authority chain has no independently verifiable root basis"

    def create_governance_event(self, event_type: str, target_type: str, target_id: str, actor_or_process: str, *, authority_grant_id: str | None, exact_scope: dict[str, Any], effective_at: str | None, payload: dict[str, Any] | None = None) -> str:
        if authority_grant_id is not None:
            ok, reason = self.validate_competence_chain(authority_grant_id, exact_scope, at_time=effective_at or utcnow())
            if not ok:
                raise LedgerError(f"Governance event lacks competent authority: {reason}")
        gid = new_id("gevt")
        now = utcnow()
        with tx(self.db_path) as conn:
            conn.execute(
                "INSERT INTO governance_event(id,event_type,target_type,target_id,actor_or_process,authority_grant_id,payload_json,recorded_at,committed_at,effective_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (gid, event_type, target_type, target_id, actor_or_process, authority_grant_id, json_dumps({"exact_scope": exact_scope, **(payload or {})}), now, now, effective_at),
            )
        return gid

    def create_effectivity_binding(self, target_type: str, target_id: str, rule_type: str, *, trigger: dict[str, Any], effective_from: str | None, effective_to: str | None = None, governance_event_id: str | None = None) -> str:
        eid = new_id("eff")
        with tx(self.db_path) as conn:
            conn.execute(
                "INSERT INTO effectivity_binding(id,target_type,target_id,rule_type,trigger_json,effective_from,effective_to,governance_event_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (eid, target_type, target_id, rule_type, json_dumps(trigger), effective_from, effective_to, governance_event_id, utcnow()),
            )
        return eid

    def get_dependency_policy(self, policy_key: str, version: int = 1) -> str:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT id FROM dependency_change_policy WHERE policy_key=? AND version=?", (policy_key, version)).fetchone()
            if not row:
                raise LedgerError(f"Unknown dependency change policy: {policy_key}@V{version}")
            return row["id"]

    def create_dependency_policy(self, policy_key: str, version: int, effect: str, materiality_rule: dict[str, Any], affected_semantics: dict[str, Any], *, effective_from: str) -> str:
        pid = new_id("dcp")
        with tx(self.db_path) as conn:
            conn.execute(
                "INSERT INTO dependency_change_policy(id,policy_key,version,effect,materiality_rule_json,affected_semantics_json,effective_from,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (pid, policy_key, version, effect, json_dumps(materiality_rule), json_dumps(affected_semantics), effective_from, utcnow()),
            )
        return pid

    def bind_dependency(self, downstream_state_id: str, upstream_state_id: str, dependency_type: str, change_policy_id: str, materiality_basis: dict[str, Any] | None = None) -> str:
        did = new_id("dep")
        with tx(self.db_path) as conn:
            conn.execute(
                "INSERT INTO dependency_binding(id,downstream_state_id,upstream_state_id,dependency_type,change_policy_id,materiality_basis_json,created_at) VALUES(?,?,?,?,?,?,?)",
                (did, downstream_state_id, upstream_state_id, dependency_type, change_policy_id, json_dumps(materiality_basis or {}), utcnow()),
            )
        return did

    def record_domain(self, stage: str, owner_authority: str, payload: dict[str, Any], *, natural_key: str | None = None, subject_identity_id: str | None = None, scope: dict[str, Any] | None = None, record_state: str = "ESTABLISHED", effective_from: str | None = None, observed_at: str | None = None, upstream_states: Iterable[tuple[str, str]] = ()) -> ArtifactRef:
        identity = self.get_or_create_identity(stage, natural_key)
        state = self.create_state(identity, stage, payload, effective_from=effective_from, observed_at=observed_at)
        with tx(self.db_path) as conn:
            conn.execute(
                "INSERT INTO domain_record(artifact_state_id,stage,owner_authority,subject_identity_id,scope_json,record_state) VALUES(?,?,?,?,?,?)",
                (state.state_id, stage, owner_authority, subject_identity_id, json_dumps(scope or {}), record_state),
            )
        for upstream_id, edge_type in upstream_states:
            self.add_provenance(upstream_id, state.state_id, edge_type, materially_consumed=True)
        return state

    def verify_storage(self) -> list[str]:
        errors: list[str] = []
        with connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM content_descriptor").fetchall()
            for r in rows:
                try:
                    raw_path = self.resolve_storage_ref(r["raw_storage_ref"], expected_algorithm=r["raw_hash_algorithm"])
                except LedgerError as exc:
                    errors.append(f"invalid raw storage ref {r['id']}: {exc}")
                    raw_path = None
                if raw_path is not None:
                    if not raw_path.exists():
                        errors.append(f"missing raw object {r['id']}")
                    else:
                        actual = hash_bytes(raw_path.read_bytes(), r["raw_hash_algorithm"])
                        if actual != r["raw_hash"]:
                            errors.append(f"raw hash mismatch {r['id']}")

                cp = r["canonical_storage_ref"]
                if cp:
                    try:
                        canonical_path = self.resolve_storage_ref(cp, expected_algorithm=r["canonical_hash_algorithm"])
                    except LedgerError as exc:
                        errors.append(f"invalid canonical storage ref {r['id']}: {exc}")
                        canonical_path = None
                    if canonical_path is not None:
                        if not canonical_path.exists():
                            errors.append(f"missing canonical object {r['id']}")
                        else:
                            actual = hash_bytes(canonical_path.read_bytes(), r["canonical_hash_algorithm"])
                            if actual != r["canonical_hash"]:
                                errors.append(f"canonical hash mismatch {r['id']}")
        return errors

    def integrity_check(self) -> dict[str, Any]:
        issues = self.verify_storage()
        with connect(self.db_path) as conn:
            fk = conn.execute("PRAGMA foreign_key_check").fetchall()
            for row in fk:
                issues.append(f"foreign key issue: {tuple(row)}")
            orphan_current = conn.execute(
                """SELECT p.projection_key FROM current_view_projection p
                   LEFT JOIN adjudication a ON a.id=p.current_adjudication_id
                   WHERE p.current_adjudication_id IS NOT NULL AND a.id IS NULL"""
            ).fetchall()
            issues.extend([f"orphan current view: {r['projection_key']}" for r in orphan_current])

            # Exact adjudication-consumption hashes must still match the immutable descriptor.
            bad_consumption = conn.execute(
                """SELECT c.adjudication_id,c.artifact_state_id
                   FROM adjudication_consumed_artifact c
                   JOIN artifact_state s ON s.id=c.artifact_state_id
                   JOIN content_descriptor d ON d.id=s.content_descriptor_id
                   WHERE c.exact_raw_hash<>d.raw_hash
                      OR COALESCE(c.exact_canonical_hash,'')<>COALESCE(d.canonical_hash,'')"""
            ).fetchall()
            issues.extend([f"adjudication consumed-hash mismatch: {r['adjudication_id']}:{r['artifact_state_id']}" for r in bad_consumption])

            # Current adjudication view may only point at an adjudication for the same target.
            wrong_target = conn.execute(
                """SELECT p.projection_key,p.target_id,a.target_id AS adjudication_target
                   FROM current_view_projection p
                   JOIN adjudication a ON a.id=p.current_adjudication_id
                   WHERE p.target_type='ADJUDICATION_TARGET' AND p.target_id<>a.target_id"""
            ).fetchall()
            issues.extend([f"current-view target mismatch: {r['projection_key']}" for r in wrong_target])

            # Publication execution requires an exact authorized human state in provenance.
            pub_without_auth = conn.execute(
                """SELECT d.artifact_state_id
                   FROM domain_record d
                   WHERE d.stage='PUBLICATION_EXECUTION'
                     AND NOT EXISTS (
                       SELECT 1 FROM provenance_edge p
                       JOIN artifact_state a ON a.id=p.from_state_id
                       WHERE p.to_state_id=d.artifact_state_id
                         AND p.edge_type='EXECUTION_AUTHORIZATION'
                         AND a.state_type='HUMAN_AUTHORIZATION'
                         AND json_extract(a.payload_json,'$.decision')='AUTHORIZED'
                     )"""
            ).fetchall()
            issues.extend([f"publication execution missing human authorization: {r['artifact_state_id']}" for r in pub_without_auth])

            # ACTIVE monetization must preserve all three governing gates in exact-state provenance.
            active_without_gates = conn.execute(
                """SELECT m.artifact_state_id
                   FROM monetization_activation_record m
                   WHERE m.activation_state='ACTIVE'
                     AND (
                       NOT EXISTS (SELECT 1 FROM provenance_edge p JOIN artifact_state s ON s.id=p.from_state_id WHERE p.to_state_id=m.artifact_state_id AND s.state_type='HUMAN_AUTHORIZATION' AND json_extract(s.payload_json,'$.decision')='AUTHORIZED')
                       OR NOT EXISTS (SELECT 1 FROM provenance_edge p JOIN artifact_state s ON s.id=p.from_state_id WHERE p.to_state_id=m.artifact_state_id AND s.state_type='COMPLIANCE_ASSESSMENT' AND json_extract(s.payload_json,'$.gate_decision') IN ('PASS','WARNING'))
                       OR NOT EXISTS (SELECT 1 FROM provenance_edge p JOIN artifact_state s ON s.id=p.from_state_id WHERE p.to_state_id=m.artifact_state_id AND s.state_type='ELIGIBILITY_ASSESSMENT' AND json_extract(s.payload_json,'$.outcome')='ELIGIBLE')
                     )"""
            ).fetchall()
            issues.extend([f"active monetization missing governing gates: {r['artifact_state_id']}" for r in active_without_gates])

            # Authenticated material operations must preserve the exact governed operator-binding provenance.
            authenticated_material_without_binding = conn.execute(
                """SELECT d.artifact_state_id,d.stage
                   FROM domain_record d
                   JOIN artifact_state s ON s.id=d.artifact_state_id
                   WHERE d.stage IN ('HUMAN_AUTHORIZATION','HUMAN_COMMERCIAL_AUTHORIZATION','MONETIZATION_ACTIVATION','PUBLICATION_EXECUTION','REALIZED_ECONOMIC_OUTCOME')
                     AND (
                       json_extract(s.payload_json,'$.identity_assurance.authenticated')=1
                       OR json_extract(s.payload_json,'$.execution_actor_authorization.authenticated')=1
                     )
                     AND NOT EXISTS (
                       SELECT 1 FROM provenance_edge p
                       JOIN artifact_state b ON b.id=p.from_state_id
                       WHERE p.to_state_id=d.artifact_state_id
                         AND p.edge_type='AUTHORIZED_OPERATOR_BINDING'
                         AND b.state_type='OPERATOR_IDENTITY_BINDING'
                     )"""
            ).fetchall()
            issues.extend([f"authenticated material operation missing operator-binding provenance: {r['stage']}:{r['artifact_state_id']}" for r in authenticated_material_without_binding])

            # Authenticated publication execution must consume the exact channel binding authorized by the human decision.
            authenticated_publication_bad_channel = conn.execute(
                """SELECT d.artifact_state_id
                   FROM domain_record d
                   JOIN artifact_state s ON s.id=d.artifact_state_id
                   WHERE d.stage='PUBLICATION_EXECUTION'
                     AND json_extract(s.payload_json,'$.execution_actor_authorization.authenticated')=1
                     AND (
                       json_extract(s.payload_json,'$.channel_binding_state_id') IS NULL
                       OR NOT EXISTS (
                         SELECT 1 FROM provenance_edge p
                         JOIN artifact_state c ON c.id=p.from_state_id
                         WHERE p.to_state_id=d.artifact_state_id
                           AND p.edge_type='EXECUTION_EXACT_CHANNEL_BINDING'
                           AND c.state_type='LIVE_CHANNEL_BINDING'
                           AND c.id=json_extract(s.payload_json,'$.channel_binding_state_id')
                       )
                     )"""
            ).fetchall()
            issues.extend([f"authenticated publication missing exact channel-state provenance: {r['artifact_state_id']}" for r in authenticated_publication_bad_channel])

            # Every normalization/correspondence judgment created under V2 must have an immutable artifact state.
            missing_norm_artifact = conn.execute(
                """SELECT n.id FROM normalization_assertion n
                   LEFT JOIN normalization_assertion_artifact a ON a.normalization_assertion_id=n.id
                   WHERE a.artifact_state_id IS NULL"""
            ).fetchall()
            issues.extend([f"normalization assertion missing immutable artifact state: {r['id']}" for r in missing_norm_artifact])
            missing_corr_artifact = conn.execute(
                """SELECT c.id FROM correspondence_judgment c
                   LEFT JOIN correspondence_judgment_artifact a ON a.correspondence_judgment_id=c.id
                   WHERE a.artifact_state_id IS NULL"""
            ).fetchall()
            issues.extend([f"correspondence judgment missing immutable artifact state: {r['id']}" for r in missing_corr_artifact])

            # Exact contract references must still resolve to the same immutable child artifact state/hashes.
            bad_contract_ref = conn.execute(
                """SELECT r.parent_contract_version_id,r.reference_role
                   FROM governance_contract_reference r
                   JOIN governance_contract_version g ON g.id=r.child_contract_version_id
                   JOIN artifact_state s ON s.id=g.artifact_state_id
                   JOIN content_descriptor d ON d.id=s.content_descriptor_id
                   WHERE r.child_artifact_state_id<>g.artifact_state_id
                      OR r.exact_raw_hash<>d.raw_hash
                      OR COALESCE(r.exact_canonical_hash,'')<>COALESCE(d.canonical_hash,'')"""
            ).fetchall()
            issues.extend([f"contract-reference pin mismatch: {r['parent_contract_version_id']}:{r['reference_role']}" for r in bad_contract_ref])

            # Current target projections require immutable target fingerprints.
            missing_target_fp = conn.execute(
                """SELECT t.id FROM adjudication_target t
                   LEFT JOIN adjudication_target_fingerprint f ON f.target_id=t.id
                   WHERE f.target_id IS NULL"""
            ).fetchall()
            issues.extend([f"adjudication target missing fingerprint: {r['id']}" for r in missing_target_fp])

            counts = {r["name"]: r["n"] for r in conn.execute(
                """SELECT 'artifact_identity' name, count(*) n FROM artifact_identity
                   UNION ALL SELECT 'artifact_state', count(*) FROM artifact_state
                   UNION ALL SELECT 'provenance_edge', count(*) FROM provenance_edge
                   UNION ALL SELECT 'adjudication', count(*) FROM adjudication
                   UNION ALL SELECT 'domain_record', count(*) FROM domain_record"""
            )}
        return {"ok": not issues, "issues": issues, "counts": counts}
