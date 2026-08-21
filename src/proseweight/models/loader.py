"""Model abstraction + loader (absorbs the predecessor's ``get_model``).

Torch/transformers are imported lazily so the deterministic core and its tests
never require the model runtime. One model is kept in memory at a time (a large
checkpoint is a large checkpoint).
"""

from __future__ import annotations

_cache: dict = {}


def get_model(model_id: str, revision: str = "unpinned"):  # pragma: no cover - needs weights
    """Load a causal-LM + tokenizer with eager attention and bf16-on-CUDA.

    bf16 (not fp16) on GPU: Qwen2.5's large attention logits overflow fp16's
    range and softmax to NaN; bf16 has fp32's exponent range, so no overflow.
    """
    if model_id in _cache:
        return _cache[model_id]
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as e:
        raise RuntimeError(
            "Model loading needs the runtime extra: pip install 'proseweight[runtime]'"
        ) from e

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float32
    else:
        dtype = torch.float32
    tok = AutoTokenizer.from_pretrained(model_id, revision=revision)
    model = AutoModelForCausalLM.from_pretrained(
        model_id, revision=revision, dtype=dtype, attn_implementation="eager"
    ).to(device)
    model.eval()
    _cache.clear()  # one model in memory at a time
    _cache[model_id] = (tok, model, device)
    return _cache[model_id]
