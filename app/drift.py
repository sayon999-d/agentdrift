"""Drift decision logic shared by API routes (DB + memory paths)."""

from __future__ import annotations

import json
from typing import Any

from app.config import get_settings
from app.embeddings import get_embedding_service


def flatten_text(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, sort_keys=True, default=str)
    except Exception:
        return str(payload)


def decide_drift(
    *,
    prior: dict | None,
    current: dict,
    threshold: float | None = None,
) -> dict:
    """Compare prior vs current execution dicts. Returns detection fields (no ids)."""
    settings = get_settings()
    thr = threshold if threshold is not None else settings.DRIFT_SIMILARITY_THRESHOLD
    svc = get_embedding_service()

    cur_text = flatten_text(current.get("input_payload")) + "\n" + flatten_text(current.get("output_payload"))
    cur_emb = current.get("payload_embedding") or svc.embed_payload(
        current.get("input_payload"), current.get("output_payload")
    )

    if prior is None:
        return {
            "kind": "no_drift",
            "similarity": 1.0,
            "threshold": thr,
            "evidence": {"reason": "first execution in session"},
            "embedding": cur_emb,
        }

    prior_text = flatten_text(prior.get("input_payload")) + "\n" + flatten_text(prior.get("output_payload"))
    prior_emb = prior.get("payload_embedding") or svc.embed_payload(
        prior.get("input_payload"), prior.get("output_payload")
    )
    similarity = svc.cosine(prior_emb, cur_emb)

    evidence: dict[str, Any] = {
        "similarity": round(similarity, 4),
        "threshold": thr,
        "prior_sequence": prior.get("sequence"),
        "current_sequence": current.get("sequence"),
    }

    # 1) hard state change always wins
    ph, ch = prior.get("state_hash"), current.get("state_hash")
    if ph is not None and ch is not None and ph != ch:
        evidence.update({"reason": "state_hash changed", "prior_state_hash": ph, "current_state_hash": ch})
        return {"kind": "state_drift", "similarity": similarity, "threshold": thr,
                "evidence": evidence, "embedding": cur_emb}

    # 2) output schema change (key sets differ)
    try:
        pk = set((prior.get("output_payload") or {}).keys()) if isinstance(prior.get("output_payload"), dict) else set()
        ck = set((current.get("output_payload") or {}).keys()) if isinstance(current.get("output_payload"), dict) else set()
        if pk and ck and pk != ck:
            evidence.update({"reason": "output schema keys changed",
                             "added": sorted(ck - pk), "removed": sorted(pk - ck)})
            # schema change + low similarity -> still semantic; keep schema_drift explicit
            if similarity >= thr:
                return {"kind": "schema_drift", "similarity": similarity, "threshold": thr,
                        "evidence": evidence, "embedding": cur_emb}
    except Exception:
        pass

    # 3) NLI contradiction on output text
    contra = svc.nli_contradiction(flatten_text(prior.get("output_payload"))[:2000],
                                   flatten_text(current.get("output_payload"))[:2000])
    evidence["contradiction_score"] = round(float(contra), 4)
    if contra >= 0.7:
        evidence["reason"] = "NLI contradiction between consecutive outputs"
        return {"kind": "logical_drift", "similarity": similarity, "threshold": thr,
                "evidence": evidence, "embedding": cur_emb}

    # 4) semantic similarity threshold
    if similarity < thr:
        evidence["reason"] = f"cosine similarity {similarity:.4f} < threshold {thr}"
        return {"kind": "semantic_drift", "similarity": similarity, "threshold": thr,
                "evidence": evidence, "embedding": cur_emb}

    evidence["reason"] = "within threshold"
    return {"kind": "no_drift", "similarity": similarity, "threshold": thr,
            "evidence": evidence, "embedding": cur_emb}
