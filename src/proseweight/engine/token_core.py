"""Token-level causal-influence core (absorbed from the predecessor).

Per-token influence by *intervention* rather than attention: knock a token out
(attention_mask=0) and measure how much the model's next-token distribution over
the generated continuation shifts vs the un-ablated baseline (mean KL). Bigger =
removing the token actually moved the output. The instruction-level engine
aggregates these token scores over each segment's span. Torch is imported lazily.
"""

from __future__ import annotations


def ablation_scores(model, full_ids, n_prompt: int, content_positions):  # pragma: no cover
    """Causal influence per prompt token via attention-mask knockout (mean KL)."""
    import torch

    with torch.no_grad():
        length = full_ids.shape[1]
        n_gen = length - n_prompt
        scores = torch.zeros(n_prompt, dtype=torch.float32)
        if n_gen < 1 or not content_positions:
            return scores
        device = full_ids.device
        pids = torch.arange(length, device=device).unsqueeze(0)
        pos = torch.arange(n_prompt - 1, length - 1, device=device)
        base_lp = torch.log_softmax(
            model(full_ids, position_ids=pids).logits[0][pos].float(), dim=-1
        )
        base_p = base_lp.exp()
        ones = torch.ones_like(full_ids)
        for j in content_positions:
            m = ones.clone()
            m[0, j] = 0
            abl_lp = torch.log_softmax(
                model(full_ids, attention_mask=m, position_ids=pids).logits[0][pos].float(),
                dim=-1,
            )
            kl = (base_p * (base_lp - abl_lp)).sum(-1).mean()
            scores[j] = max(kl.item(), 0.0)
        return scores


def aggregate_to_segments(token_scores, segments, token_spans) -> dict[str, float]:
    """Sum token-level scores over each segment's token span (attention pre-screen).

    ``token_spans`` maps token index -> char offset; a token belongs to a segment
    if its char offset falls within the segment's [start, end). Used only to RANK
    instructions for ablation priority, never as a verdict.
    """
    out: dict[str, float] = {}
    for seg in segments:
        total = 0.0
        for tok_idx, char_off in enumerate(token_spans):
            if seg.start_offset <= char_off < seg.end_offset and tok_idx < len(token_scores):
                total += float(token_scores[tok_idx])
        out[seg.id] = total
    return out
