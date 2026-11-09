# TwIL local deployment

The authenticated OpenAI-compatible server is running on port **8080**.
Local endpoint: `http://127.0.0.1:8080/v1`.
The listener is bound to `127.0.0.1`; access is limited to this PC.
Model alias: `twil-8b`. The API key is stored only in the ignored `.env` file.

## Verified results

- Q5_K_M artifact downloaded and SHA-256 verified.
- Embedded 9,013-character Jinja template inspected directly from the GGUF.
- CUDA 13.3 engine detects the RTX 5070; logs confirm **41/41 layers offloaded**.
- Health, authenticated chat and streaming pass; requests without a key return 401.
- Twelve consecutive requests return coherent greetings, arithmetic and instruction-following responses.
- Total GPU memory stayed around 7.4 GiB with a 4 MiB span in the latest run.
- A 128-token response measured **91.97 generated tokens/second**. It ended at the configured token limit; this is a short local measurement, not a broad benchmark.
- Start, stop and restart commands were exercised successfully.
- Ruff check/format, strict mypy and **9 tests pass**.

Detailed results: [reports/acceptance.json](reports/acceptance.json).
The model's embedded template enables thinking by default. Initial short requests
could exhaust their token budget before producing visible answer text. The server
now supplies the template's supported `enable_thinking=false` option by default.
Set `TWIL_ENABLE_THINKING=true` to enable it and allow a sufficient generation budget.

## Local access only

The user chose to keep this deployment local to this PC. The server is bound to
`127.0.0.1:8080`, verified after restart. Ethernet remains Public and no firewall
rule was created. No administrator action or LAN setup is needed.

The optional `scripts/enable-lan.ps1` script is retained for a future explicitly
requested LAN deployment; it is not part of the current setup. Enabling LAN later
would also require changing `TWIL_HOST` and restarting the server.

## Commands

### HTML chat interface

Open **http://127.0.0.1:8081** in your browser. The interface is running locally
and authenticates to the model automatically; no key needs to be pasted into the
page. It supports streamed answers, stop, new conversation, copy, response-length
selection and temperature control. Conversations are kept in page memory only.

Assistant answers render Markdown with styled headings, emphasis, lists, quotes,
tables, links, inline code and fenced code blocks with copy buttons. Markdown-it
15.0.3 and DOMPurify 3.4.17 are bundled locally under `static/vendor/`; versions,
archive integrity values and asset SHA-256 hashes are recorded in `manifest.json`
alongside their licenses. Raw HTML is disabled and rendered HTML is sanitized.
Images are shown as alt text, keeping automatic external image requests out of
the conversation. Rendering follows the projects' guidance:
[markdown-it](https://github.com/markdown-it/markdown-it/blob/master/docs/safety.md),
[DOMPurify](https://github.com/cure53/DOMPurify).

To launch the interface again after closing it or restarting Windows:

```powershell
uv run twil-deploy ui
```

Keep the model server running as well. The UI command runs in the foreground;
Ctrl+C stops that interface process. `TWIL_UI_PORT` overrides its default port
8081. The currently started background instance has logs in `logs/ui.*.log` and
its process ID in `logs/ui.pid`.

The HTML assets are in `src/twil_deploy/static/index.html`. A loopback Python proxy
adds the API key on the server side, validates requests and streams the model's
response. It rejects foreign browser origins and unexpected Host headers.
Browser checks passed for chat, starting a new conversation, JavaScript errors,
and the desktop/mobile layouts. Proxy regression tests bring the suite to
**13 passing tests**.

Open PowerShell in this directory. uv is installed locally in `../tools/uv/`:

```powershell
$env:Path = (Resolve-Path ../tools/uv).Path + ';' + $env:Path
uv sync --locked
uv run twil-deploy serve
uv run twil-deploy check
uv run python scripts/acceptance.py
uv run twil-deploy stop
```

The server runs hidden in the background. Logs and its PID are in `logs/`.
Do not start another instance while one is running. Stop validates the recorded
PID's executable path before using Windows process termination. This stops the
server; draining active requests before termination is not implemented.
The key is passed through `LLAMA_API_KEY`, which was verified in engine help.

Total context 8192 is shared across two slots, giving about 4096 tokens per request.
All settings accept `TWIL_` overrides through `.env` or the environment. If selecting
a different quant, set the filename and its verified SHA-256 along with the quant.
The Python client caps prompt length and generated tokens, uses explicit timeouts,
bounded retries, and closes network resources.

## Deployment manifest

| Item | Pinned value / observed result |
| --- | --- |
| Requested source | `Guilherme34/TwIL-8B-Abliterated-Uncensored` |
| Source revision inspected | `ae1d15dd29fb068b67253ce739303a22f78b367a` |
| Architecture | `GraniteForCausalLM`, 40 transformer layers, F16 source |
| Source tokenizer template | Absent; GGUF contains an embedded template |
| Quantizer | `mradermacher/TwIL-8B-Abliterated-Uncensored-GGUF` |
| GGUF repository revision | `185406da788423cc0d0dc13f290fea87072904b2` |
| Artifact | `TwIL-8B-Abliterated-Uncensored.Q5_K_M.gguf` |
| Size | 6,253,887,808 bytes |
| SHA-256 | `fbec9bf51afe4419abd7c62fceac9126b557a1ae56af884b0c19b9264c13e08c` |
| Working engine | `b10000`, commit `47a39665e7081dc482feec169961acc09750a5c4`, CUDA 13.3 |
| Engine directory | `bin-b10000/` |
| Newer candidate | `b12110`, CUDA 13.4; version works after runtime update, device probe timed out; unused |
| GPU | NVIDIA RTX 5070, 12,227 MiB |
| Driver / reported CUDA support | 610.88 / 13.3 |
| Windows C++ runtime | Updated by user to 14.51.36247.0 |
| Python / uv | 3.12.16 / 0.13.7 |
| Git | 2.56.0.windows.4 |
| API / download packages | OpenAI 2.28.0, httpx 0.28.1, huggingface-hub 2.4.0 |
| Runtime flags | 99 GPU layers, context 8192, 2 slots, Jinja, flash attention on, thinking off, verbosity 4 |
| Validation date | 2026-11-09 |

The quantizer identifies the exact requested source model. Its metadata does not
establish the source commit used for conversion. No independent quality, license
or safety claims are inferred from the model name. Safetensors and GGUF are used;
no pickle checkpoints are loaded.

## Rebuild

`scripts/bootstrap.ps1` downloads pinned uv and engine archives, checks recorded
SHA-256 hashes, extracts them, synchronizes the lockfile and verifies the engine.
It does not install the system C++ runtime. The original runtime 14.36.32532.0
crashed in MSVCP140.dll; the user's runtime update resolved startup for b10000.

```powershell
./scripts/bootstrap.ps1
$env:Path = (Resolve-Path ../tools/uv).Path + ';' + $env:Path
uv run python -c "from pathlib import Path; import secrets; p=Path('.env'); assert not p.exists(), '.env already exists'; p.write_text('TWIL_API_KEY='+secrets.token_urlsafe(48)+'\n', encoding='utf-8')"
$env:HF_HUB_DISABLE_XET = '1'
uv run twil-deploy download
uv run twil-deploy serve
uv run twil-deploy check
```

Download is resumable and verifies the pinned upstream LFS digest. A `.sha256`
sidecar is written next to the model. Conversion is skipped because a matching
GGUF exists. The optional `convert` command requires a separately pinned llama.cpp
checkout and isolated conversion Python environment. It preserves intermediate
F16 weights and never invents an architecture conversion.

## Quality gate

```powershell
uv run ruff check --fix .
uv run ruff format .
uv run mypy src
uv run pytest
```

No model weights, binaries, logs, environments or local credentials are tracked.
The generated lockfile and deployment tooling are ready for version control;
no commit was created.
