"""Embedding service: sentence-transformers (384-d) with deterministic hash fallback.

- Primary: `all-MiniLM-L6-v2` (384 dims), lazy-loaded, thread offloaded.
- Fallback: hashing-trick embedding (token hash -> 384-d, L2 normalized) so the
  daemon works offline / without torch. Cosine similarity remains meaningful
  (identical texts -> 1.0, unrelated -> ~0).
- NLI: optional cross-encoder; disabled by default (NLI_ENABLED=false).
  When disabled, a lightweight heuristic flags contradiction via negation flip.
"""

from __future__ import annotations

import hashlib
import logging
import re

import numpy as np

from app.config import get_settings

log = logging.getLogger("agentdrift.embeddings")

_WORD_RE = re.compile(r"[a-z0-9]+")
NEGATIONS = {"not", "no", "never", "n't", "cannot", "can't", "won't", "don't", "isn't"}


class EmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.dim = self.settings.EMBEDDING_DIM
        self._model = None
        self._model_tried = False
        self._nli = None
        self._nli_tried = False

    @property
    def backend(self) -> str:
        if self._model is not None:
            return str(self.settings.EMBEDDING_MODEL)
        return "hash-fallback"

    def _load_model(self):
        if self._model_tried:
            return self._model
        self._model_tried = True
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.settings.EMBEDDING_MODEL)
            log.info("Loaded embedding model %s", self.settings.EMBEDDING_MODEL)
        except Exception as exc:  # offline / no torch -> fallback
            log.warning("Embedding model unavailable, using hash fallback: %s", exc)
            self._model = None
        return self._model

    # -- public API -----------------------------------------------------
    def embed_text(self, text: str) -> list[float]:
        text = (text or "")[:8000]
        model = self._load_model()
        if model is not None:
            try:
                vec = model.encode([text], normalize_embeddings=True)[0]
                return [float(x) for x in vec]
            except Exception as exc:
                log.warning("encode failed, hash fallback: %s", exc)
        return self.hash_embed(text, self.dim)

    def embed_payload(self, *payloads: object) -> list[float]:
        import json

        parts: list[str] = []
        for p in payloads:
            if p is None:
                continue
            if isinstance(p, str):
                parts.append(p)
            else:
                try:
                    parts.append(json.dumps(p, sort_keys=True, default=str))
                except Exception:
                    parts.append(str(p))
        return self.embed_text("\n".join(parts))

    @staticmethod
    def hash_embed(text: str, dim: int = 384) -> list[float]:
        vec = np.zeros(dim, dtype=np.float64)
        for token in _WORD_RE.findall(text.lower()):
            h = int(hashlib.sha256(token.encode()).hexdigest(), 16)
            vec[h % dim] += 1.0
            vec[(h >> 16) % dim] += 0.5
        norm = float(np.linalg.norm(vec))
        if norm < 1e-12:
            return [0.0] * dim
        return (vec / norm).tolist()

    @staticmethod
    def cosine(a: list[float] | np.ndarray, b: list[float] | np.ndarray) -> float:
        va = np.asarray(a, dtype=np.float64)
        vb = np.asarray(b, dtype=np.float64)
        denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
        if denom < 1e-12:
            return 1.0 if float(np.linalg.norm(va - vb)) < 1e-12 else 0.0
        return float(np.dot(va, vb) / denom)

    # -- NLI -------------------------------------------------------------
    def nli_contradiction(self, premise: str, hypothesis: str) -> float:
        """Return P(contradiction) in [0,1]. Heuristic unless NLI_ENABLED."""
        if not self.settings.NLI_ENABLED:
            return heuristic_contradiction(premise, hypothesis)
        try:
            return self._cross_encoder_nli(premise, hypothesis)
        except Exception as exc:
            log.warning("NLI model failed, heuristic fallback: %s", exc)
            return heuristic_contradiction(premise, hypothesis)

    def _cross_encoder_nli(self, premise: str, hypothesis: str) -> float:
        if not self._nli_tried:
            self._nli_tried = True
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            tok = AutoTokenizer.from_pretrained(self.settings.NLI_MODEL)
            mdl = AutoModelForSequenceClassification.from_pretrained(self.settings.NLI_MODEL)
            mdl.eval()
            self._nli = (tok, mdl, torch)
        tok, mdl, torch = self._nli
        inputs = tok(premise[:512], hypothesis[:512], return_tensors="pt", truncation=True)
        with torch.no_grad():
            logits = mdl(**inputs).logits[0]
            probs = torch.softmax(logits, dim=-1).tolist()
        # deberta-v3-small NLI label order: contradiction, entailment, neutral (check config at runtime)
        labels = [s.lower() for s in getattr(mdl.config, "id2label", {}).values()] or []
        if "contradiction" in labels:
            return float(probs[labels.index("contradiction")])
        return float(probs[0])  # best-effort


def heuristic_contradiction(premise: str, hypothesis: str) -> float:
    """Cheap negation-flip heuristic: same content words but negation differs -> 0.85."""
    pa = set(_WORD_RE.findall(premise.lower())) if premise else set()
    ha = set(_WORD_RE.findall(hypothesis.lower())) if hypothesis else set()
    if not pa or not ha:
        return 0.0
    content_p, content_h = pa - NEGATIONS, ha - NEGATIONS
    if not content_p or not content_h:
        return 0.0
    overlap = len(content_p & content_h) / max(1, len(content_p | content_h))
    neg_flip = bool(pa & NEGATIONS) != bool(ha & NEGATIONS)
    if neg_flip and overlap > 0.4:
        return 0.85
    return 0.0


_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _service
    if _service is None:
        _service = EmbeddingService()
    return _service
