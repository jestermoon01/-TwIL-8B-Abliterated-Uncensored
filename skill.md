
---
name: deploy-twil-8b
description: Deploy Guilherme34/TwIL-8B-Abliterated-Uncensored locally (Windows + RTX 5070 12 GB) with llama.cpp, expose an OpenAI-compatible API on the LAN, with a clean, modular, linted Python tooling layer. Use when asked to download, convert, quantize, serve, test or maintain this model.
---

# Skill: Deploy TwIL-8B-Abliterated-Uncensored locally

## 0. Context and constraints

- **Model:** `Guilherme34/TwIL-8B-Abliterated-Uncensored` on Hugging Face. Safetensors, F16, ~9B params, Granite-based (base `ibm-granite/granite-4.1-8b-base`). The model card is **empty**: do not assume a prompt format, license or benchmarks. Take the chat template from the repo's `tokenizer_config.json` / the GGUF metadata.
- **Hardware:** Windows, NVIDIA RTX 5070 (12 GB VRAM, Blackwell / sm_120). F16 weights are ~18 GB, so they **do not fit**: quantize.
- **Engine (primary):** `llama.cpp` / `llama-server`, Windows-native, prebuilt CUDA build (needs CUDA 12.8+ for Blackwell).
- **Engine (optional scale-up):** vLLM or SGLang in WSL2/Docker, only if >~5 concurrent users are needed. See section 9.
- **Goal:** an OpenAI-compatible HTTP API reachable on the **local network only**.
- **Rules for the agent:** never guess; run the verification step of each phase before moving on; pin versions; keep every command reproducible from the repo.

## 1. Phase 1: Preflight checks

Run and record the results:

```powershell
nvidia-smi                      # driver, CUDA version, free VRAM (expect ~12 GB)
python --version                # or: uv python list
uv --version
git --version
Get-PSDrive C                   # need ~50 GB free (F16 download + GGUF F16 + quant)
```

Stop and report if: driver does not support CUDA 12.8+, free VRAM is far below 12 GB (close other GPU apps), or disk is short.

## 2. Phase 2: Project layout (modular, src layout)

```
twil-deploy/
├── pyproject.toml
├── uv.lock
├── .python-version
├── .env.example            # never commit .env
├── .gitignore              # models/, .env, .venv/, *.gguf, __pycache__/
├── README.md
├── models/                 # HF snapshots + GGUF files (git-ignored)
├── bin/                    # llama.cpp binaries (git-ignored)
├── src/twil_deploy/
│   ├── __init__.py
│   ├── config.py           # typed settings (pydantic-settings)
│   ├── logging_setup.py    # one place to configure logging
│   ├── download.py         # HF download (pinned revision)
│   ├── convert.py          # HF -> GGUF F16 -> quantized GGUF
│   ├── server.py           # build args + launch/stop llama-server
│   ├── client.py           # thin OpenAI-compatible client
│   ├── healthcheck.py     # /health + smoke test generation
│   └── cli.py              # entry point: download | convert | serve | check
└── tests/
    ├── test_config.py
    ├── test_server_args.py # pure unit tests, no GPU needed
    └── test_client.py      # mocked HTTP (respx / httpx.MockTransport)
```

Principles:

- **One responsibility per module.** `server.py` builds the command line (pure function, unit-testable) separately from the code that spawns the process.
- **No hard-coded paths, ports or model names.** Everything goes through `config.py`, overridable by environment variables / `.env`.
- **Pure functions where possible**, side effects (subprocess, network, disk) isolated at the edges.
- **Type hints everywhere**; `from __future__ import annotations` not required on Python 3.12+.
- **No `print`** in library code: use `logging`. Only `cli.py` may print user-facing output.
- **Fail loudly with clear messages**: raise specific exceptions (`ModelNotFoundError`, `ServerStartError`), never swallow errors with bare `except`.

## 3. Phase 3: Python environment with uv + ruff

```powershell
uv init --package twil-deploy
cd twil-deploy
uv python pin 3.12
uv add pydantic-settings httpx openai huggingface_hub typer rich
uv add --dev ruff pytest pytest-cov respx mypy pre-commit
uv lock
```

Rules:

- Use **`uv`** for everything (`uv add`, `uv sync`, `uv run`). No bare `pip install`.
- **Commit `uv.lock`.** Pin exact versions of anything that touches the GPU stack or the API contract.
- Run tools via `uv run ruff ...`, `uv run pytest`, so the project env is always used.

### `pyproject.toml` (tooling section)

```toml
[tool.ruff]
line-length = 100
target-version = "py312"
src = ["src", "tests"]

[tool.ruff.lint]
select = [
  "E", "F", "W",   # pycodestyle, pyflakes
  "I",             # isort
  "B",             # bugbear
  "UP",            # pyupgrade
  "SIM",           # simplify
  "C4",            # comprehensions
  "PTH",           # pathlib over os.path
  "RET", "ARG",    # return / unused args
  "S",             # bandit-style security checks
  "T20",           # no stray print()
  "PL",            # pylint rules
  "RUF",
]
ignore = ["PLR0913"]  # allow functions with many keyword params in CLIs

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101", "PLR2004"]   # asserts and magic numbers OK in tests
"src/twil_deploy/cli.py" = ["T20"] # CLI may print

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
strict = true
python_version = "3.12"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

### Quality gate (run before every commit and after every code change)

```powershell
uv run ruff check --fix .
uv run ruff format .
uv run mypy src
uv run pytest
```

Optionally install `pre-commit` with ruff hooks so the gate runs automatically.

## 4. Phase 4: Configuration (`config.py`)

Use `pydantic-settings` so every value is typed, documented and overridable:

```python
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TWIL_")

    hf_repo: str = "Guilherme34/TwIL-8B-Abliterated-Uncensored"
    hf_revision: str = "main"  # PIN to a commit hash once validated
    models_dir: Path = Path("models")
    llama_bin_dir: Path = Path("bin")

    quant: str = "Q5_K_M"  # fallback: Q4_K_M if VRAM is tight
    ctx_size: int = 8192
    n_gpu_layers: int = 99  # offload everything
    host: str = "0.0.0.0"  # LAN exposure
    port: int = 8080
    api_key: str  # REQUIRED, no default
    parallel: int = 2  # concurrent slots
```

`.env.example`:

```
TWIL_API_KEY=change-me-to-a-long-random-string
TWIL_QUANT=Q5_K_M
TWIL_CTX_SIZE=8192
TWIL_PORT=8080
```

## 5. Phase 5: Get the weights

1. **First, look for an existing GGUF.** The model page lists 3 quantizations. Check them (`https://huggingface.co/models?other=base_model:quantized:Guilherme34/TwIL-8B-Abliterated-Uncensored`). If a trusted GGUF (Q4_K_M or Q5_K_M) exists, download only that file and skip to Phase 7. Prefer quantizers you can verify.
2. **Otherwise download the safetensors snapshot** (pin the revision):

```powershell
uv run hf download Guilherme34/TwIL-8B-Abliterated-Uncensored `
  --revision main `
  --local-dir models/TwIL-8B-hf
```

Implement this in `download.py` with `huggingface_hub.snapshot_download(...)` (resumable), logging the resolved commit hash. Record that hash in the README for reproducibility.

**Verify:** `config.json`, `tokenizer.json`/`tokenizer_config.json` and all `*.safetensors` shards are present; total size ≈ 18 GB.

## 6. Phase 6: Install llama.cpp (Windows, CUDA)

1. Download the latest **Windows CUDA 12.x** release zip from the `ggml-org/llama.cpp` GitHub releases (use the CUDA 12.8+ build for the RTX 5070). Extract into `bin/`.
2. Make sure the matching CUDA runtime DLLs zip (`cudart-llama-bin-win-cuda-...`) is extracted in the same folder if the release ships it separately.
3. Verify:

```powershell
.\bin\llama-server.exe --version
.\bin\llama-server.exe --help | Select-String "flash"
```

**If no usable Blackwell build exists** or the binary fails to see the GPU, build from source (CUDA Toolkit 12.8+, Visual Studio Build Tools, CMake):

```powershell
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120
cmake --build build --config Release -j
```

Keep a clone of llama.cpp (for `convert_hf_to_gguf.py`) at a **pinned tag/commit**, and install its Python requirements into a **separate** uv environment (do not pollute the project env):

```powershell
uv venv .venv-convert
uv pip install --python .venv-convert -r llama.cpp/requirements/requirements-convert_hf_to_gguf.txt
```

## 7. Phase 7: Convert and quantize (skip if you downloaded a GGUF)

```powershell
# HF safetensors -> GGUF F16
.venv-convert\Scripts\python llama.cpp\convert_hf_to_gguf.py models\TwIL-8B-hf `
  --outfile models\twil-8b-f16.gguf --outtype f16

# F16 -> Q5_K_M  (use Q4_K_M if memory is tight)
.\bin\llama-quantize.exe models\twil-8b-f16.gguf models\twil-8b-Q5_K_M.gguf Q5_K_M
```

Quant guidance for 12 GB VRAM (8-9B model):

| Quant | Approx. size | Notes |
|---|---|---|
| Q4_K_M | ~5.5 GB | Safest, most context headroom |
| Q5_K_M | ~6.5 GB | **Default**: good quality/size balance |
| Q6_K | ~7.5 GB | Better quality, still fits with moderate ctx |
| Q8_0 | ~9.5 GB | Near-lossless; little room for KV cache |

**If conversion fails** with an "unsupported architecture" error: update llama.cpp to the latest release and retry; if it still fails, stop and report the exact error. Do not improvise a manual conversion.

**Verify:** the quantized file exists, loads (Phase 8) and generates coherent text. Delete the F16 GGUF only after validation (keep the HF snapshot until then).

## 8. Phase 8: Serve (LAN, authenticated)

```powershell
.\bin\llama-server.exe `
  -m models\twil-8b-Q5_K_M.gguf `
  --host 0.0.0.0 --port 8080 `
  -ngl 99 `
  -c 8192 `
  --parallel 2 `
  --jinja `
  --api-key $env:TWIL_API_KEY `
  --alias twil-8b
```

Notes:

- Flag names change between llama.cpp versions. **Always check `llama-server --help`** for the installed version (e.g. flash attention is `-fa` / `--flash-attn`, enable it if supported; KV-cache quantization via `--cache-type-k/--cache-type-v` can free VRAM at some quality cost).
- `--jinja` uses the chat template embedded in the GGUF. If outputs look malformed, inspect the template and compare with the repo's `tokenizer_config.json`.
- **Context is shared across slots:** total `-c` is split among `--parallel` slots. With `-c 8192 --parallel 2`, each request gets ~4096 tokens. Raise `-c` if needed (watch VRAM).
- Build the argument list in `server.py` as a pure function returning `list[str]`, unit-tested; launch with `subprocess.Popen` using a list (never `shell=True`), log stdout/stderr to a file under `logs/`.

### Verify VRAM and GPU offload

```powershell
nvidia-smi            # expect ~7-10 GB used by llama-server
```

In the server log, confirm all layers were offloaded to CUDA. If VRAM is exhausted: lower `-c`, use Q4_K_M, or quantize the KV cache.

### Expose on the LAN safely

```powershell
# Allow inbound ONLY on the Private network profile
New-NetFirewallRule -DisplayName "llama-server 8080" -Direction Inbound `
  -Protocol TCP -LocalPort 8080 -Action Allow -Profile Private

ipconfig              # note the IPv4 address, e.g. 192.168.x.y
```

Security rules (important, this model is **uncensored**: it has no built-in refusal behaviour):

- **LAN only.** Never port-forward on the router, never expose to the public internet.
- **Always set `--api-key`.** Keep it in `.env`, never in the repo or in logs.
- Optionally restrict the firewall rule to specific client IPs (`-RemoteAddress`).
- Tell users on the network what the model is. Apply your own moderation/policy layer if third parties will use it.

## 9. Phase 9: Verify (smoke tests)

From another machine on the LAN (replace IP and key):

```powershell
curl http://192.168.x.y:8080/health

curl http://192.168.x.y:8080/v1/chat/completions `
  -H "Authorization: Bearer $env:TWIL_API_KEY" `
  -H "Content-Type: application/json" `
  -d '{"model":"twil-8b","messages":[{"role":"user","content":"Say hello in one sentence."}],"max_tokens":64}'
```

Python client (`client.py`), standard OpenAI SDK pointed at the local server:

```python
from openai import OpenAI

client = OpenAI(base_url="http://192.168.x.y:8080/v1", api_key="<TWIL_API_KEY>")
resp = client.chat.completions.create(
    model="twil-8b",
    messages=[{"role": "user", "content": "Say hello in one sentence."}],
    max_tokens=64,
    stream=False,
)
print(resp.choices[0].message.content)
```

Acceptance checklist:

- [ ] `/health` returns OK
- [ ] Chat completion returns coherent text (no garbage tokens, no endless repetition)
- [ ] Streaming (`stream=True`) works
- [ ] Request without API key is rejected (401)
- [ ] Reachable from another LAN device; not reachable from outside the network
- [ ] VRAM stays stable after 10+ consecutive requests
- [ ] Tokens/second measured and recorded (`llama-bench`, or server timing in the response)

## 10. Best practices: LLM deployment

- **Reproducibility:** pin the HF commit hash, llama.cpp tag, CUDA/driver versions, and the quant type. Record them in the README ("Deployment manifest").
- **Treat weights as artifacts:** keep them out of git; store checksums (`Get-FileHash`) next to the files.
- **Supply-chain caution:** third-party fine-tunes and GGUF conversions are unverified. Prefer safetensors/GGUF (no pickle). Never load `.bin`/pickle files from unknown sources.
- **Config over code:** all tunables (ctx, quant, ports, slots) in settings/env.
- **Observability:** structured logs (request id, latency, tokens), log rotation, a `/health` probe, and a script that records tokens/s and VRAM after each change.
- **Graceful lifecycle:** start/stop through `cli.py` (PID file or process handle), restart on failure with a bounded retry (no tight crash loops). On Windows, optionally wrap in a Scheduled Task or NSSM service.
- **Resource limits:** cap `max_tokens` and request size on the client side; keep `--parallel` modest on a laptop (thermal throttling, shared VRAM).
- **Laptop specifics:** plug in AC power, set the "High performance" power plan, ensure the dGPU is used (not the Intel iGPU), monitor temperatures.
- **Evaluate before trusting:** build a small fixed prompt set (`tests/prompts.jsonl`) and compare outputs across quants (Q4 vs Q5 vs Q6) before choosing the default.
- **Change one thing at a time**, re-run the acceptance checklist after each change.
- **Backups:** keep the working GGUF + `.env.example` + manifest so the setup can be rebuilt in minutes.

## 11. Best practices: Python code

- **Modularity:** small modules, one purpose each (see layout). Import direction: `cli -> server/download/convert/client -> config/logging_setup`. No circular imports.
- **Typing:** full annotations, `mypy --strict` clean. Use `pathlib.Path`, `dataclass`/pydantic models instead of dicts of unknown shape, `Enum`/`Literal` for fixed choices.
- **Ruff is the single source of lint + format** (no black/isort/flake8 alongside it). The quality gate in section 3 must pass before declaring any task done.
- **Subprocess safety:** argument lists, no `shell=True`, explicit `timeout`, check return codes, capture and log stderr.
- **HTTP clients:** `httpx`/`openai` with explicit timeouts, bounded retries with backoff, and context managers for cleanup.
- **Secrets:** read from env/`.env` through `config.py`; never log them; mask them in error messages.
- **Errors:** specific exception types, actionable messages ("what failed, why, what to try").
- **Tests:** unit-test pure logic (arg building, config parsing, quant selection); mock HTTP for the client; keep GPU-dependent checks in a separate `smoke` marker (`pytest -m smoke`) so CI/laptop runs stay fast.
- **Docstrings** on public functions (what/why, not how); comments only for non-obvious decisions.
- **Git hygiene:** small commits, conventional messages, `.gitignore` covering models, binaries, `.env`, `.venv*`, logs.
- **Dependencies:** minimal; every `uv add` justified; run `uv lock --upgrade-package <pkg>` deliberately, never blindly upgrade everything.

## 12. Optional: scale-up with vLLM / SGLang (only if needed)

Use only if you need many concurrent users or heavy prefix sharing.

- Run inside **WSL2 (Ubuntu) with NVIDIA GPU support** or Docker Desktop with the WSL2 backend.
- You need a **quantized HF-format checkpoint (AWQ/GPTQ/FP8)** that fits 12 GB; GGUF is not the normal path for these engines. Verify that a quant of this exact model exists, or quantize it yourself.
- Verify engine support for the Granite architecture **and** for Blackwell (sm_120) in the engine's release notes before investing time.
- Expose the same OpenAI-compatible API on another port so clients only change `base_url`.
- Compare against the llama.cpp baseline (latency, tokens/s, concurrent users) before switching.

## 13. Troubleshooting quick table

| Symptom | Likely cause | Action |
|---|---|---|
| `unsupported architecture` on convert | llama.cpp too old | Update llama.cpp, retry; else stop and report |
| CUDA out of memory | ctx/quant too large | Lower `-c`, use Q4_K_M, quantize KV cache, close GPU apps |
| Runs on CPU, slow | CPU-only build or `-ngl 0` | Use the CUDA build, check `-ngl 99`, check log for CUDA device |
| `no kernel image` / CUDA arch error | Build lacks sm_120 | Use CUDA 12.8+ build or compile with `-DCMAKE_CUDA_ARCHITECTURES=120` |
| Garbled or looping output | Wrong chat template / bad quant | Use `--jinja`, check template, try a higher quant |
| Not reachable from LAN | Firewall / wrong host | `--host 0.0.0.0`, add Private-profile firewall rule, check IP |
| 401 Unauthorized | Missing/wrong key | Send `Authorization: Bearer <key>` |
| Slow under load | Too many slots / context | Lower `--parallel`, or move to vLLM/SGLang (section 12) |

## 14. Definition of done

1. Server starts from one command (`uv run twil-deploy serve`) and stops cleanly.
2. Acceptance checklist (section 9) fully ticked.
3. Quality gate (ruff check, ruff format, mypy, pytest) passes.
4. README contains the deployment manifest (versions, hashes, quant, flags) and the exact commands to rebuild.
5. `.env` and model files are not in git; the API key is not exposed anywhere.