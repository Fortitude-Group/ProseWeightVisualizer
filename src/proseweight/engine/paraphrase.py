"""Paraphrase generation + intent-preservation gate (FR-008, research.md R2).

Generation reuses the local Qwen model with rotating rewrite strategies (lazy,
needs the runtime). The intent gates are what keep a paraphrase honest:
  - a cheap negation/modal backstop (pure Python, tested here), which catches the
    classic silent drift a prompt-linter must not tolerate in its own generator
    (e.g. "never" softened to "rarely"), and
  - a bidirectional NLI check (model-based, lazy).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

STRATEGIES = (
    "reorder clauses",
    "swap active/passive voice",
    "synonym substitution",
    "imperative to conditional phrasing",
    "expand or contract sentence length",
)

_NEGATIONS = re.compile(r"\b(never|not|no|without|don'?t|doesn'?t|cannot|can'?t|won'?t)\b", re.I)
_MODALS = re.compile(r"\b(must|should|shall|may|always|required|forbidden|optional)\b", re.I)


def _counts(text: str) -> tuple[int, int]:
    return (len(_NEGATIONS.findall(text)), len(_MODALS.findall(text)))


@dataclass
class IntentCheck:
    preserved: bool
    reason: str


def intent_preserved_backstop(original: str, paraphrase: str) -> IntentCheck:
    """Flag a paraphrase that changed the count of negations or obligation modals.

    This is the cheap, near-zero-cost catch for the most common real failure:
    a rewrite that quietly drops or softens a "never"/"must". A mismatch does not
    prove the intent changed, but it is exactly the case that needs a human look.
    """
    o_neg, o_mod = _counts(original)
    p_neg, p_mod = _counts(paraphrase)
    if o_neg != p_neg:
        return IntentCheck(False, f"negation count changed ({o_neg} -> {p_neg})")
    if o_mod != p_mod:
        return IntentCheck(False, f"obligation-modal count changed ({o_mod} -> {p_mod})")
    return IntentCheck(True, "negation/modal counts preserved")


@dataclass
class Paraphrase:
    k: int
    strategy: str
    text: str
    seed: int
    validation_failed: bool


def generate_paraphrases(instruction: str, k: int, seed: int, model=None) -> list[Paraphrase]:  # pragma: no cover
    """Generate ``k`` paraphrases with rotating strategies. Needs the local model."""
    if model is None:
        raise RuntimeError(
            "paraphrase generation needs the local model runtime "
            "(pip install 'proseweight[runtime]')"
        )
    out: list[Paraphrase] = []
    for i in range(k):
        strategy = STRATEGIES[i % len(STRATEGIES)]
        # model.rewrite(instruction, strategy, seed=seed+i) -> text  (runtime detail)
        text = model.rewrite(instruction, strategy, seed=seed + i)
        check = intent_preserved_backstop(instruction, text)
        out.append(Paraphrase(i, strategy, text, seed + i, not check.preserved))
    return out
