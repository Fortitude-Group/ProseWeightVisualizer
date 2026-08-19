# Prose Weight Visualiser

Two prompts enter, one browser tab shows where the model *looks*.

Enter two adversarial prompts (e.g. a vivid, forceful directive vs. a beige, polite
one), pick a local open-weights model, and see each prompt rendered as a token
**attention heatmap**: warmer = more attention received from the model's generated
tokens (averaged over layers, heads, and generation steps).

> **Caveat:** attention shows where the model *looks*, not what it *obeys*. Behavioural
> influence is measured by A/B output testing, not by staring at attention. This is the
> anatomy demo.

## What it shows

- **Two views**, switchable via tabs:
  - **Text heatmap** — the prompt rendered as prose with each content token shaded by
    the attention it received.
  - **Attention dots** — an animated SVG where each content token is a dot whose area
    grows as generation proceeds (area = attention received); hover a dot for its value.
- **Content-only scoring** — the chat scaffolding (system preamble, role markers,
  `<|im_*|>` tokens, the first-token attention sink, structural newlines) is dimmed and
  excluded, so the comparison reflects *your* prompts, not the wrapper.
- **A-vs-B scoreboard** — two comparable metrics with a winner on each:
  - *content attention share* — % of the model's attention that landed on the prompt's
    content (a total; a longer/richer prompt can hold more), and
  - *per content token* — that share divided by length, isolating per-word intensity.

## Requirements

- Python 3.10+
- A CUDA GPU is recommended (models load in **bfloat16**); CPU works but is slow.

```bash
pip install torch transformers gradio accelerate
```

## Run

```bash
python prose_weight_visualiser.py
```

Then open **http://127.0.0.1:7860** and click **Fight**.

The first run downloads the selected model's weights from the Hugging Face Hub (a few
hundred MB for the 0.5B default), cached under your HF cache directory. Bundled model
choices include `Qwen/Qwen2.5-0.5B-Instruct`, `Qwen/Qwen2.5-1.5B-Instruct`,
`meta-llama/Llama-3.2-1B-Instruct`, and `gpt2`; you can also type any other Hugging Face
model id into the dropdown.

## How it works

The app runs greedy generation with `output_attentions=True`, then for each generated
step averages the last query row's attention over all layers and heads to get a
per-prompt-token score, and averages those across steps. Scores are normalised against
the mean of the **content** tokens only. Models are loaded with `bfloat16` on GPU
(not `float16`) because Qwen2.5's large attention logits overflow fp16's range and
`softmax` them into `NaN`, which corrupts the whole forward pass; bf16 has fp32's
exponent range and is stable.

## Notes

- Runs entirely locally — no data leaves your machine.
- Everything is in the single file `prose_weight_visualiser.py`.
