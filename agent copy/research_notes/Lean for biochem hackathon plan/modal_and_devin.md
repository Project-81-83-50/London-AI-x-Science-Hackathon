# Modal and Devin for a 24–48h Hackathon (Best Use of Modal / Best Use of Devin)

Research date: 2026-10-01. Every factual claim carries a URL. Where I could not verify something
against a primary source, it appears under **Gaps** rather than being asserted.

A standing caveat for the whole document: Modal's SDK has renamed a lot of surface area during the
0.7x → 1.0 transition, and Devin's docs are explicitly self-deprecating about currency ("In some
cases Devin may not function exactly as referenced, or documentation may be out of date" —
[docs.devin.ai](https://docs.devin.ai/)). Treat every API name below as "verify by running
`modal --version` and checking the linked page the morning of the hackathon."

---

## Modal: current (2026) programming model and exact decorator/API names

### Takeaway
The current model is: one `modal.App`, functions declared with `@app.function(...)`, classes with
`@app.cls(...)`, environments built declaratively with `modal.Image`, and fan-out via
`Function.map()` / `.starmap()` / `.spawn()`. Several names changed in the 1.0 cycle — most
relevantly `@modal.web_endpoint` → `@modal.fastapi_endpoint`, `allow_concurrent_inputs=N` →
`@modal.concurrent(max_inputs=N)`, `keep_warm`/`concurrency_limit`/`container_idle_timeout` →
`min_containers`/`max_containers`/`scaledown_window`, `modal.Mount` → `Image.add_local_*`,
`.lookup()` → `.from_name()`, and `modal.gpu.H100()` → the string `"H100"`.

### Cited Findings

**Core constructs (confirmed on the live docs landing page)**
- `@app.function`, `modal.App`, `modal.Image` are the current core constructs; the docs landing page shows `modal.Image.debian_slim()`, GPU selection as a string (`gpu="h100"`), and `uv_pip_install` as a package-install method — [Modal docs guide](https://modal.com/docs/guide)
- Modal pitches itself as "zero configuration" with "everything defined in code rather than YAML", per-second billing, and autoscaling across multiple clouds; Python is primary, with JS/TS and Go SDKs for *calling* functions and managing resources (not for defining them) — [Modal docs guide](https://modal.com/docs/guide)
- Headline capabilities named by Modal itself: "Run low latency inference with sub-second cold starts", "Scale out batch jobs to run massively in parallel", GPU training/fine-tuning, "Isolated Sandboxes for executing AI-generated code", and GPU-backed collaborative Notebooks — [Modal docs guide](https://modal.com/docs/guide)

**The 1.0 rename table (this is the single most important page to read before writing code)** — all from [Modal 1.0 migration guide](https://modal.com/docs/guide/modal-1-0-migration):

| Concern | Old | New | Introduced | Enforced |
|---|---|---|---|---|
| Local files into image | `Image.copy_local_dir`, `Image.copy_local_file` | `Image.add_local_dir`, `Image.add_local_file` | v0.72.11 | — |
| Mounts | `modal.Mount` + `mount=` param | `Image.add_local_*` | v0.72.4 | v1.0.0 |
| Dockerfile context | `context_mount=` | inferred automatically (param removed) | v0.72.4 | v1.0.0 |
| Build step | `@modal.build` | `modal.Volume` or `Image.run_function` | v0.72.17 | — |
| Local Python deps | implicit "automounting" | explicit `Image.add_local_python_source` | v0.73.11 | v1.0.0 |
| Autoscaling | `keep_warm`, `concurrency_limit`, `container_idle_timeout` | `min_containers`, `max_containers`, `scaledown_window` | v0.73.76 | — |
| Web endpoint | `@modal.web_endpoint` | `@modal.fastapi_endpoint` | v0.73.89 | — |
| Input concurrency | `allow_concurrent_inputs=N` | `@modal.concurrent(max_inputs=N)` | v0.73.148 | — |
| Object lookup | `.lookup()` | `.from_name()` (+ `.hydrate()` when needed) | v0.72.56 | — |
| Class constructors | custom `__init__` | `modal.parameter` annotations + synthetic constructor | v0.74.0 | — |
| GPU spec | `modal.gpu.H100()`, `modal.gpu.A100(size="80GB")` | strings: `"H100"`, `"A100-80GB"`, `"H100:8"` | v0.73.31 | — |
| CLI module invocation | file path | explicit `-m` flag for module mode | v0.73.58 | — |

- The migration guide notes most deprecations do not break until a later v1.x minor release, so old code may still run but emit warnings — [Modal 1.0 migration guide](https://modal.com/docs/guide/modal-1-0-migration)
- `modal.web_endpoint` was renamed to `modal.fastapi_endpoint` specifically "to make the implicit dependency on FastAPI more clear"; semantics are otherwise identical, so it is a pure name substitution — [modal.fastapi_endpoint reference](https://modal.com/docs/sdk/py/latest/modal.fastapi_endpoint) / [modal.web_endpoint reference](https://modal.com/docs/reference/modal.web_endpoint)

**Images** — all from [Modal Images guide](https://modal.com/docs/guide/images):
- `modal.Image.debian_slim(python_version="3.13")` is the default base; Python defaults to matching your local version
- `uv_pip_install` is recommended over `pip_install` (faster), and the docs recommend hard version pins (`"torch==2.8.0"`) for reproducibility
- `apt_install("git", "curl")` for system packages; `run_commands(...)` to "execute shell commands during image building for tasks like cloning repositories or building from source"; `env(...)` for env vars (string values only); `workdir`; `from_registry`; `dockerfile_commands`
- `add_local_dir` / `add_local_file` default to loading files **at container startup** (fast redeploys); pass `copy=True` to bake them into a build layer so later build steps can use them
- `run_function` runs arbitrary Python as a build step and accepts volumes, secrets and GPU — the canonical way to pre-download model weights into the image
- `image.imports()` context manager imports packages in the image environment globally for several functions, and is what enables memory snapshots for faster cold starts

**Fan-out** — from [Modal scale-out guide](https://modal.com/docs/guide/scale):
- `Function.map()` is the recommended primitive: "If your code is running the same function repeatedly with different independent inputs (e.g., a grid search), the easiest way to increase performance is to run those function calls in parallel using Modal's `Function.map()` method"
- `.map()` results preserve input ordering; by default an exception aborts the map, but `return_exceptions=True` makes failures come back as ordinary result items
- `.starmap()` spreads tuples across multiple function arguments, mirroring `itertools.starmap`
- Hard platform limit: **4,000 concurrent containers per Function**; additional limits depend on plan tier. `max_containers` caps a specific Function.

**Dicts and Queues** — from [Modal Dicts and Queues guide](https://modal.com/docs/guide/dicts-and-queues):
- `modal.Dict.ephemeral()` and `modal.Queue.ephemeral()` create storage that lives only for the run: `with modal.Dict.ephemeral() as d, modal.Queue.ephemeral() as q:`
- Queue ops: `put()`, `put_many()`, `get_many(count, timeout)`. Dict ops are dict-like: `d["stop"] = True`, `if "stop" in d:`
- The documented worked example is a distributed web crawler using a Queue as the job queue and a Dict as a shared stop-flag, processing "about 100,000 URLs per minute"

**Secrets** — from [Modal Secrets guide](https://modal.com/docs/guide/secrets):
- Three programmatic constructors: `Secret.from_dict({"KEY": "value"})`, `Secret.from_dotenv()` (needs `python-dotenv`), `Secret.from_name("secret-keys")` for dashboard-created secrets
- CLI: `modal secret create database-secret PGHOST=uri PGPORT=5432`, with `modal secret list` / `modal secret delete`; you can pass through a shell var as `PGPASSWORD="$PGPASSWORD"`
- Injected per-function: `@app.function(secrets=[modal.Secret.from_name("secret-keys")])`, then read via `os.environ["MY_PASSWORD"]`
- Limits/gotchas: keys ≤ 16,384 chars, values ≤ 32,768 chars; key names are letters/digits/underscores and cannot start with a digit; when multiple Secrets are listed, "key-values from later `modal.Secret` objects in the list will overwrite earlier key-values in the case of a clash"; use Volumes for oversized values

**Volumes** — from [Modal Volumes guide](https://modal.com/docs/guide/volumes):
- `modal.Volume.from_name(name, create_if_missing=True)`; `version=2` selects v2 Volumes
- Mounted as `@app.function(volumes={"/data": vol})`, giving "a fully-featured filesystem interface"
- Writes are persisted by **background commits every few seconds and at shutdown**; explicit `.commit()` is available. Other containers do not see new writes until `.reload()`, and "while a reload is in progress the Volume will appear empty to the container" that called it
- Performance: best under 50,000 files (v1 hard limit 500,000 inodes), up to ~2.5 GB/s, ≤5 concurrent commits recommended on v1; "last write wins in case of concurrent modification". v2 supports unlimited files and hundreds of concurrent writers
- Guidance on Volume vs Image: Volumes for runtime-selected models/data; Image when baking a single model in at build time
- CLI: `modal volume create|put|get|ls|cp|rm`

**Web endpoints** — from [Modal Web Functions guide](https://modal.com/docs/guide/webhooks):
- `@modal.fastapi_endpoint()` — simplest; accepts `method="POST"`, query params and typed args via FastAPI
- `@modal.asgi_app()` — the function returns an ASGI app (FastAPI, FastHTML, Starlette); supports the ASGI lifespan protocol; pair with `@modal.concurrent(max_inputs=100)`
- `@modal.wsgi_app()` — returns a WSGI app (Django, Flask); "concurrent inputs will be run on separate threads"
- `@modal.web_server(port)` — for non-ASGI/WSGI servers and subprocess-launched servers; **the app must bind `0.0.0.0`, not localhost**; supports WebSockets
- URL shape: `https://workspace--function-name-environment.modal.run` — [Web Function URLs](https://modal.com/docs/guide/webhook-urls)
- Proxy-token auth exists via `Modal-Key` / `Modal-Secret` headers — [Modal Web Functions guide](https://modal.com/docs/guide/webhooks)

**GPU selection** — from [Modal GPU guide](https://modal.com/docs/guide/gpu):
- `@app.function(gpu="A100")`; available types listed as T4, L4, A10, L40S, A100, A100-40GB, A100-80GB, RTX-PRO-6000, H100, H100!, H200, B200, B200+, B300
- Multi-GPU via `:n`, e.g. `gpu="H100:8"`. "Currently B300, B200, H200, H100, A100, L4, T4 and L40S instances support up to 8 GPUs (up to 2,304 GB GPU RAM), and A10 instances support up to 4 GPUs"
- Fallback lists are supported and tried in order: `gpu=["H100", "A100-40GB:2"]`
- **"Using a GPU requires having a valid payment method on file"** — worth handling before the event starts

### Inferences
- For a hackathon, the safest API subset is the one that has already settled: `modal.App`, `@app.function`, `@app.cls` with `modal.parameter`, `Image.debian_slim().uv_pip_install(...)`, `Function.map(..., return_exceptions=True)`, `modal.Volume.from_name(create_if_missing=True)`, `modal.Secret.from_name`, `@modal.fastapi_endpoint`/`@modal.asgi_app`, `gpu="T4"`-style strings. All of these are the *new* names and so will not emit deprecation noise during a demo.
- `return_exceptions=True` on `.map()` is effectively mandatory for this project: a fan-out of thousands of LLM-generated protocols through a checker will have individual failures, and the default behavior (abort the whole map) would kill a live demo.
- `Image.add_local_python_source` now being explicit is the single most likely cause of a "works locally, `ModuleNotFoundError` remotely" surprise, since automounting was removed in the 1.0 cycle.

### Gaps
- I could not load `https://modal.com/docs/reference/modal.App` (the fetch returned empty content), so I have not verified the exact keyword-argument signatures of `@app.function` / `@app.cls` against the reference page. The migration guide and individual guides above are consistent, but the full signature list is unconfirmed.
- The scale-out page I fetched did not document `.spawn()`, `.spawn_map()`, or `.for_each()`. Modal does have `.spawn()` (fire-and-forget returning a `FunctionCall` handle) but **I did not verify its current name/signature from a primary source**, so treat it as unconfirmed and check [modal.Function reference](https://modal.com/docs/reference/modal.Function) before relying on it.
- Scheduled functions: I did not fetch the cron/schedule page. The expected form is `@app.function(schedule=modal.Period(...))` or `modal.Cron(...)`, but **this is unverified** — see [Modal docs guide](https://modal.com/docs/guide) and look for the "Scheduling" section.

---

## Modal: free credits, limits, cold starts, container lifecycle for a live demo

### Takeaway
The free Starter plan gives $30/month of credits with a hard cap of 100 containers and 10
concurrent GPUs — generous for a checker fan-out, tight for GPU fan-out. Containers boot in about
one second, but *your* initialization (global scope + `@modal.enter`) is what actually determines
demo latency, and the fix is `min_containers` plus memory snapshots.

### Cited Findings

**Plans and limits** — all from [Modal pricing](https://modal.com/pricing):
- **Starter**: "$0 + compute / month" with "**$30 / month free credits**", up to 3 workspace seats, **limits: 100 containers, 10 GPU concurrency**, 1 TiB/month free egress
- **Team**: "$250 + compute / month" with "$100 / month free credits", unlimited seats, limits 5,000 containers and 50 GPU concurrency, 10 TiB/month free egress
- **Enterprise**: custom, 100 TiB/month free egress
- Per-second compute prices: CPU "$0.0000131 / core / sec" (a physical core = 2 vCPU equivalent); memory "$0.00000222 / GiB / sec"; Volumes "$0.09 / GiB / mo" with 1 TiB free; egress "$0.04 / GiB"
- GPU per-second: B300 $0.001972, H100 SXM5 $0.001097, A100-80GB $0.000694, L4 $0.000222, **T4 $0.000164**
- "Only pay for what you use" — no idle charges — but note the **default idle timeout is 60 seconds and is billed** — [Modal pricing](https://modal.com/pricing)

**Hackathon credits (precedent, not a guarantee for your event)**
- At the Lux Capital / Modal / Cognition / AWS / Ramp "AI Agent & Infra Hackathon", the **Best Use of Modal** track was described as "Any project that leverages Modal's serverless compute platform", with prizes of $25,000 / $10,000 / $1,000 in Modal credits, and **"Accepted participants receive $500 in Modal credits"** — [AI Agent & Infra Hackathon (Devpost)](https://ai-agent-infra.devpost.com/)
- That same event's Cognition track was "Best Agent Hack" — "Any project building an agent or a custom MCP client or server" — with prizes including a year of Devin Team, plus "Access to Devin Core Plan + 3 months Windsurf Pro" for participants — [AI Agent & Infra Hackathon (Devpost)](https://ai-agent-infra.devpost.com/)
- **Caveat: that event is dated August 12–14, 2025, so it is not your hackathon.** It is useful only as evidence of the typical shape of a Modal/Cognition sponsor track and credit amount.
- Other datapoints on the size of Modal hackathon awards: Hack the North 2026 lists a "Cognition: Best Use of Devin" prize of $5,000 in Devin credits — [Hack the North 2026 (Devpost)](https://hackthenorth2026.devpost.com/); HackIllinois 2026's Best AI Inference award is "$2,000 in cash plus $5,000 in Modal Credits per person" — [HackIllinois 2026 (Devpost)](https://hackillinois-2026.devpost.com/); Modal also runs a startup credits program — [Modal startups](https://modal.com/startups)

**Cold starts and container lifecycle** — all from [Modal cold start guide](https://modal.com/docs/guide/cold-start):
- Definition: latency comes from two sources — "(1) inputs may spend more time waiting in a queue for a container to become ready or 'warm'" and "(2) when an input is handled by the container that just started, there may be extra work that only needs to be done on the first invocation"
- "**Containers boot in about one second.**" But boot includes running module global scope and `modal.enter` methods, "which can add seconds to minutes depending on workload"
- `min_containers` "puts a floor on the the number of containers so that the Function doesn't scale to zero" — this is the demo-day setting
- `buffer_containers` provisions extra idle containers during active periods, for bursty traffic "where the arrival of one input predicts the arrival of more inputs" — a good match for a fan-out demo
- `scaledown_window`: idle retention, configurable from **2 seconds to 20 minutes, default 60 seconds**
- **Memory snapshots** capture container memory after warm-up and reuse it on later boots, which "substantially reduce[s] cold start latency penalties and warm up period duration"
- `@modal.enter` methods run during warm-up, and "no inputs will be routed to containers that have yet to complete this initialization"
- Load independent resources (e.g. several models) concurrently rather than sequentially; move model downloads and setup into the Image or a Volume so they happen before first invocation
- Modal's pricing page independently states containers "spin up/down in 1-2 seconds" — [Modal pricing](https://modal.com/pricing)

**`modal run` vs `modal serve` vs `modal deploy`** — all from [Modal managing deployments guide](https://modal.com/docs/guide/managing-deployments):
- `modal run` and `modal serve` are local-iteration tools that create **ephemeral Apps**, existing only for the dev cycle. The docs warn "Programmatically triggering lots of ephemeral App runs can clutter your web and CLI interfaces"
- `modal deploy` creates a **persistent** deployment; deployed Apps group repeated executions for observability, and functions "execute much faster since they're persistent and reused, not created on-demand by calls"
- Scheduled and web functions on a deployed App "continue operating independently from your local work"
- Redeploying increments the App version; if nothing in the config changed, "the deployment becomes a no-op, and the App version will not increment"
- **Rollback to a previous version is a Team/Enterprise feature** — not available on Starter

**Image build caching** — from [Modal Images guide](https://modal.com/docs/guide/images):
- Images are cached **per layer** (per method call). Unchanged layers are reused. "Breaking the cache on a single layer will cause cascading rebuilds for all subsequent layers" — so put volatile steps last
- Force a rebuild with `force_build=True` on a specific method, or `MODAL_FORCE_BUILD=1` for all images; `MODAL_IGNORE_CACHE=1` rebuilds without poisoning the cache for later builds
- A workspace-level **"Image Builder Version"** setting controls OS/Python/dependency baselines; changing it triggers rebuilds, and Modal updates base images conservatively "to prevent cascading rebuilds"
- Local-vs-remote imports: import image-only packages **inside function bodies** to avoid local `ImportError`; and do not return remote-only objects (e.g. a `pandas.DataFrame`) to local code, because "deserialization will fail"

### Inferences
- Demo-day recipe implied by the docs: `modal deploy` (not `modal serve`) the demo app the night before, set `min_containers=1` on the user-facing endpoint and on the checker function, set a generous `scaledown_window`, and verify the Image hash is unchanged so no rebuild fires. The combination of (a) layer-cached images, (b) deployment being a no-op when config is unchanged, and (c) `min_containers` is what makes a demo deterministic.
- The Starter plan's **100-container cap** is the binding constraint on a "fan out thousands of protocols" story: you can still run thousands of *inputs*, Modal will just queue them across ≤100 containers. Budget this in the pitch — say "3,000 protocols across 100 parallel workers in N seconds" rather than implying 3,000 simultaneous containers. The Function-level hard limit is 4,000 containers ([scale-out guide](https://modal.com/docs/guide/scale)) but plan limits bite first.
- Cost sanity for the project: a CPU-only checker fan-out is extremely cheap at $0.0000131/core/sec — e.g. 3,000 checker runs × 2 s × 1 core ≈ $0.08. A T4 at $0.000164/s costs ~$0.59/hour, so an NLI/entailment model served on T4 for a whole 48-hour hackathon is well inside $30 of credits. GPU work will not be what exhausts the free tier; long-lived `min_containers` on a GPU function could be.
- `min_containers` on a GPU function plus a 10-GPU concurrency cap means: pick **one** GPU role (the entailment checker), not several.
- Because rollback is a paid feature, the practical safety net on Starter is keeping a known-good git tag and redeploying from it.

### Gaps
- I found no Modal page stating a specific hackathon-wide credit grant for *your* event. The $500/participant figure is from the August 2025 Lux/Modal event only. Check your event's own sponsor page.
- I did not verify whether memory snapshots (`enable_memory_snapshot=True`, `@modal.enter(snap=True)`) are available on the Starter plan, nor the exact current parameter names — the cold-start guide describes the feature but the fetched excerpt did not give the flag names. Verify at [Modal cold start guide](https://modal.com/docs/guide/cold-start) / the memory-snapshot page.
- No primary source found for whether `modal serve`'s hot reload has limitations with `@app.cls` or with Sandboxes.

---

## Modal: which parts of this system are the best fit, and what reads as a genuine use

### Takeaway
The strongest, most defensible Modal story for this project is the **deterministic checker as a
massively parallel pure function** (`.map()` over thousands of candidate protocols) plus a
**prebuilt Image containing the heavy formal toolchain** — because both are things Modal is
uniquely good at and that a laptop genuinely cannot do. `modal.Sandbox` for LLM-generated code and
a Modal-hosted endpoint for the demo UI are well-supported secondary uses. Serving a small
open-weights model on GPU for the entailment role is the piece that justifies the GPU.

### Cited Findings

**Modal's own framing of the matching use cases**
- Modal explicitly lists "Scale out batch jobs to run massively in parallel" and "Isolated Sandboxes for executing AI-generated code" among its headline capabilities — [Modal docs guide](https://modal.com/docs/guide)
- `Function.map()` is documented as the recommended way to parallelize "the same function repeatedly with different independent inputs (e.g., a grid search)" — exactly the shape of "N generated protocols through one checker" — [Modal scale-out guide](https://modal.com/docs/guide/scale)

**Sandbox for untrusted / LLM-generated code** — all from [Modal Sandbox guide](https://modal.com/docs/guide/sandbox):
- Sandboxes are described as "Secure containers for executing untrusted user or agent code"
- API: `Sandbox.create()` (requires an `App`, returns a Sandbox with a unique `object_id`); `sandbox.exec(*args, timeout=...)` returns a `ContainerProcess` with stdout/stderr and a return code; `sandbox.terminate(wait=True)` sends SIGKILL (exit code 137)
- Parameters: `timeout` (**default 5 minutes, max 24 hours**), `idle_timeout`, `runtime` (`"gvisor"` default with "strong isolation", or `"vm"` for a full Linux kernel — required for Docker/FUSE), `image`, `volumes`, `secrets`, `readiness_probe` (TCP or exec), `name`
- Lifecycle: Created → Scheduled → Started → Ready (optional) → Finished; `exec()` is usable from Started onward
- GPUs are available to Sandboxes under gVisor only
- Networking — from [Sandbox networking guide](https://modal.com/docs/guide/sandbox-networking): Sandboxes cannot accept inbound connections or reach Modal resources without explicit config; **all outbound connections to public IPs are allowed by default**. Lock down with `block_network=True` ("drops all outbound traffic"), `outbound_cidr_allowlist`, or `outbound_domain_allowlist` (TLS/443 only, supports `*.example.com`); these compose additively. Inbound restricted via `inbound_cidr_allowlist`. Expose a port with Sandbox Connect Tokens (recommended; the server receives an `X-Verified-User-Data` header with JSON metadata) or raw tunnels via `encrypted_ports` / `unencrypted_ports` + `Sandbox.tunnels()`, with `h2_ports` for HTTP/2. Custom domains are a paid-plan feature.

**Documented Modal examples in the relevant categories** — from [Modal examples](https://modal.com/docs/examples):
- Example categories include "Modal Sandboxes", "Parallel Processing", "Computational Biology", "Large Language Models", "Model Training", "Embeddings", "Reinforcement Learning"
- Sandbox/agent examples that exist: "Run a LangGraph agent's code in a secure GPU sandbox", "Build a stateful, sandboxed code interpreter", "Run Node.js, Ruby, and more in a Sandbox", "Deploy OpenCode agents" to execute coding tasks at scale, "Watch a computer-use agent work in real-time over VNC"
- Batch/queue examples: "Parallel processing of Parquet files on S3", "Document OCR job queue" using Modal as "an infinitely scalable job queue"
- Open-weights serving examples: Ministral 3, vLLM, DeepSeek-V4-Flash, Nemotron 3, SGLang, Flux
- Heavy non-Python binaries already demonstrated: **Blender** (3D rendering), **Datasette**, and protein-folding stacks **ESMFold2, Chai-1, Boltz-2**
- The "Run Node.js, Ruby, and more in a Sandbox" example is direct evidence that non-Python runtimes work inside Sandboxes — [Modal examples](https://modal.com/docs/examples)

**Installing heavy/non-Python toolchains in an Image** — mechanisms documented at [Modal Images guide](https://modal.com/docs/guide/images):
- `apt_install(...)` for Debian packages
- `run_commands(...)` explicitly for "tasks like cloning repositories or building from source"
- `from_registry(...)` to start from an existing Docker image
- `dockerfile_commands(...)` for raw Dockerfile lines
- `run_function(...)` to run arbitrary Python (with GPU/volumes/secrets) as a build step
- `env(...)` to set `PATH`-style variables so an installed toolchain is on the path at runtime

**Relevance of the Computational Biology examples**
- Modal maintains a Computational Biology example category including protein-folding frameworks ESMFold2, Chai-1 and Boltz-2 — [Modal examples](https://modal.com/docs/examples). For a wet-lab-protocol project these are the nearest-neighbor examples to crib Image patterns from.

### Inferences
- **Ranking of Modal components by "impressive per hour spent", for this specific system:**
  1. **`.map()` fan-out of the static checker** — highest payoff. The checker is deterministic, CPU-only, pure, and fast, so it maps perfectly; `return_exceptions=True` handles the long tail. This is the one claim judges can verify live ("watch 2,000 protocols validate in 20 seconds"), and it is a genuine capability jump over a laptop. It also doubles as the eval harness, so you get two story beats from one implementation.
  2. **A prebuilt Image carrying the formal toolchain (Lean 4 / elan + Mathlib or equivalent)** — high payoff *if* you build it first, because the whole value is that the multi-minute toolchain install happens once at image-build time and is then free on every invocation. This is the cleanest answer to "why Modal and not a laptop": heavy toolchain + thousands of parallel invocations is precisely the combination Modal sells.
  3. **`modal.Sandbox` for LLM-generated code** — medium payoff, low cost, and it is a story Modal itself leads with ("Isolated Sandboxes for executing AI-generated code", [docs guide](https://modal.com/docs/guide)). The `block_network=True` + `outbound_domain_allowlist` + short `timeout` combination is a concrete, demoable safety argument.
  4. **A Modal-hosted endpoint for the demo UI** (`@modal.asgi_app()` with FastAPI/FastHTML) — low effort, removes all deploy friction, and gives you a public URL to put on a slide.
  5. **One small open-weights model on GPU for the entailment/NLI role** — this is what turns "we used Modal for CPU jobs" into "we used Modal for the full stack", at a cost of well under a dollar. A T4 at $0.000164/s ([pricing](https://modal.com/pricing)) is the right size for an NLI model.
- **What would read as token use:** a single `@app.function` wrapper around an API call to a frontier model. Judges on a Modal track will have seen many of those. The differentiator is that your checker is *deterministic and embarrassingly parallel*, which is a real reason to want serverless fan-out rather than a stylistic one.
- Architecturally, the planner→compiler→checker→replan loop maps cleanly onto Modal primitives: a `modal.Queue` for candidate protocols, a `modal.Dict` for the shared stop/best-so-far state, `.map()` for the checker sweep, and a Volume for citation/provenance corpora and the Lean build cache. The documented crawler example (Queue + Dict + spawned autoscaling containers at ~100k URLs/min) is a direct template for that loop — [Dicts and Queues guide](https://modal.com/docs/guide/dicts-and-queues).
- Put the Lean/Mathlib **build cache in a Volume** rather than rebuilding per container; Volumes are documented for exactly this decoupling (and for checkpointing via background commits) — [Volumes guide](https://modal.com/docs/guide/volumes). Watch the 50,000-file performance guidance, since a Mathlib build tree can be large; v2 Volumes (`version=2`) are the documented answer for high file counts.

### Gaps
- **I found no documented Modal example that installs a Lean 4 toolchain.** A targeted search returned only general Lean installation material (elan via `curl -sSf https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh`, per [leanprover/lean4](https://github.com/leanprover/lean4) and the [Lean 4 site](https://lean4.dev/)), not a Modal-specific recipe. The closest Modal-documented precedents for heavy non-Python binaries are Blender and the protein-folding stacks in [Modal examples](https://modal.com/docs/examples), plus the "Run Node.js, Ruby, and more in a Sandbox" example. So: the mechanism is clearly supported (`apt_install` + `run_commands` + `env` to set PATH), but **nobody has published the exact Lean-on-Modal Image, so budget real time for getting it right and treat it as the riskiest build step.**
- I did not find published timings for how long a Mathlib-dependent Image takes to build on Modal. This is a material unknown for a 24–48h budget.
- I did not verify a Modal example specifically for "LLM-as-planner + open-weights verifier in one app", so the dual-model pattern is my inference from the primitives, not a cited pattern.

---

## Devin: what it is as of 2026 — product surface, pricing, Knowledge/Skills/Playbooks

### Takeaway
Devin is Cognition's autonomous software-engineering agent, available as a web app, CLI, desktop
app, Slack and Teams integrations, an API, IDE plugins and MCP. Its memory layer is in transition:
**Knowledge is deprecated in favor of repo-committed `SKILL.md` Skills**, while Playbooks remain
the reusable-prompt mechanism. Billing moved in 2026 to self-serve quota plans (Free/Pro/Max/Teams)
with ACU overages, alongside Enterprise ACU contracts.

### Cited Findings

**Product surface** — from [docs.devin.ai](https://docs.devin.ai/) and the docs index at [llms.txt](https://docs.devin.ai/llms.txt):
- Devin is "an autonomous AI software engineer that can write, run and test code"
- Documented surfaces: web/cloud sessions, **Devin CLI** (with handoff to cloud), **Devin Desktop**, **Slack integration**, **Microsoft Teams integration**, **API** (with OpenAPI specs across v1/v2/v3), **MCP** (both Devin-as-MCP-client via configurable MCP servers, and an official **Devin MCP Server** letting external tools manage sessions), and **IDE integrations for JetBrains, Zed and Xcode**
- Session tooling inside a session: **IDE, Browser, Shell, and Side Chat** — [llms.txt](https://docs.devin.ai/llms.txt)
- Other named features: **Ask Devin** (query your codebase and plan tasks with high-context sessions), **DeepWiki** ("Auto-generates architecture diagrams, documentation, and source links for every repo"), **Session Insights** (analyze completed sessions to improve prompts), **Dynamic Workflows** ("Orchestrate many Devin sessions with a deterministic Python script"), **Parallel Sessions**, **Stacked PRs** ("How Devin splits large changes into ordered, reviewable stacks of pull requests"), **Devin Review** with Auto-Fix — [llms.txt](https://docs.devin.ai/llms.txt), [Instructing Devin Effectively](https://docs.devin.ai/essential-guidelines/instructing-devin-effectively)

**Knowledge, Skills, Playbooks**
- **Knowledge** lets teams "Share tips, docs, and instructions Devin recalls across sessions, scoped to repos, your organization, or your enterprise" — [llms.txt](https://docs.devin.ai/llms.txt). Each item has a **Trigger Description** (the retrieval condition, e.g. "when deploying to staging"), **Content** (a handful of sentences), and an optional `!macro`. Created at Settings → Resources → Knowledge → Create. Best practice is "specific Knowledge that is targeted at one workflow", split into small focused items. Scopes: personal/organization, enterprise, and repo-pinned (none / specific repos / all repos) — [Knowledge product guide](https://docs.devin.ai/product-guides/knowledge)
- **Important currency flag: the Knowledge page states Knowledge "is a deprecated feature", being sunset in favor of Skills, with automatic migration underway** — [Knowledge product guide](https://docs.devin.ai/product-guides/knowledge)
- **Skills** are `SKILL.md` files committed to the repo at `.agents/skills/<skill-name>/SKILL.md` (five alternative paths also supported), following "the open Agent Skills standard". YAML frontmatter carries `name`, `description` (how Devin discovers the skill), `allowed-tools` (restricts Devin's capabilities for safety), plus Devin-specific `argument-hint` and `triggers`. The body is "Step-by-step instructions Devin is prompted to follow when the skill is invoked." Skills are discovered from indexed repos and cloned machines, activate automatically when relevant (unless `triggers: ["user"]`), and can be invoked explicitly as `@skills:skill-name` with arguments — [Skills product guide](https://docs.devin.ai/product-guides/skills)
- **Playbooks** are "reusable, shareable custom prompts for recurring tasks", created at Settings → Playbooks → Create playbook, attachable via a `!macro` (e.g. `!data-tutorial`), and confirmed by "a blue pill" appearing in the session. Enterprise tiers support org-level and enterprise-level playbooks. The docs' own division of labor: **Playbooks for repeatable step-by-step procedures tied to a specific task; Knowledge for persistent conventions, coding standards and deployment workflows that apply across sessions automatically** — [Creating Playbooks](https://docs.devin.ai/product-guides/creating-playbooks), [Instructing Devin Effectively](https://docs.devin.ai/essential-guidelines/instructing-devin-effectively)

**Recommended Playbook structure** — from [Creating Playbooks](https://docs.devin.ai/product-guides/creating-playbooks):
1. **Overview** — what Devin should accomplish, plus context
2. **Procedure** — imperative steps, one action per line, "Mutually Exclusive and Collectively Exhaustive", covering setup/execution/delivery, using action verbs, avoiding needless over-specificity
3. **Specifications** — postconditions: what should be true when done, and the expected deliverable format
4. **Advice and Pointers** — preferred approaches and corrections to Devin's default assumptions (step-specific advice goes as sub-bullets)
5. **Forbidden Actions** — what Devin must absolutely avoid
6. **What's Needed From User** — inputs outside Devin's control (tokens, files, credentials)
- Playbook best practices: start with a simple multi-step task; "**Run 2+ Devins in parallel with the same playbook to quickly identify possible errors**"; iterate from real session outcomes; be explicit about deliverables and success indicators; include specific commands/parameters (e.g. model names) to steer Devin down the efficient path; use version history and revert when an update underperforms
- The docs ship a worked example — an "R Data Science Tutorial" playbook — covering dataset requirements from the user, sequential steps (data download → notebook creation → model training), file-naming conventions, advice preventing redundant package reinstallation, and forbidden actions preventing file overwrites — [Creating Playbooks](https://docs.devin.ai/product-guides/creating-playbooks)

**ACUs and pricing**
- An ACU "reflects how much compute Devin consumed during the session" / "the amount of agent effort required to complete a given task", and scales with inference used and model selected — [ACU consumption docs (per search snippet)](https://docs.devin.ai/admin/billing/usage)
- For local agents (Cascade, Devin CLI, Devin Local), ACUs are derived from inference: model tokens converted at per-token rates. For cloud agents, code review and platform capabilities, ACUs "reflect a mix of tokens, compute, VMs, and other infrastructure costs" — [Devin billing docs](https://docs.devin.ai/admin/billing)
- Enterprise contracts are billed in ACUs at the rate set in the order form — [Devin billing docs](https://docs.devin.ai/admin/billing)
- Secondary (aggregator) sources report the 2026 self-serve structure as Free (~5 ACUs), Pro $20/mo (~150 ACUs), Max $100/mo (~700 ACUs), Teams $500+/mo (pooled), with overages at $2.25/ACU and "1 ACU ≈ 15 minutes of Devin actively working" — [Usagebar: Devin pricing and rate limits](https://usagebar.com/blog/devin-pricing-and-rate-limits). **These specific numbers are from a third-party aggregator, not Cognition, and conflict slightly with Devin's own docs, which mention sessions "converted to ACUs at $2 per ACU" on quota plans ([Devin billing docs](https://docs.devin.ai/admin/billing)). Verify against the live [pricing page](https://devin.ai/pricing) before quoting.**
- Devin's docs include an ACU-efficiency case study page, "Cut a Feature Prompt from 42 to 12 ACUs" — [docs.devin.ai](https://docs.devin.ai/use-cases/gallery/analyze-session-acu-efficiency) — which is itself evidence that prompt quality drives cost by ~3-4x

### Inferences
- The Knowledge→Skills migration is the biggest practical trap for a hackathon team following older tutorials. For a 24–48h project, **Skills (a `SKILL.md` committed to your repo) is the right mechanism** for durable conventions, because it is version-controlled with the code and survives session restarts, while a **Playbook** is the right mechanism for the repeated "reproduce this result" procedure you will run several times.
- The Playbook structure maps almost one-to-one onto a paper-reproduction task, and "Forbidden Actions" and "What's Needed From User" are the two sections that will save the most hours: they are where you put "do not attempt to retrain from scratch", "do not modify the reference implementation", and "the dataset is already at `data/raw/`, do not re-download".
- The "Run 2+ Devins in parallel with the same playbook" advice is the documented route to the parallelization the task asks about — it is framed as a *debugging* technique for the playbook, which conveniently also gives you redundancy on a reproduction attempt.
- ACU budgeting: if the third-party ~15-min-per-ACU figure is right, a Pro plan's ~150 ACUs is roughly 37 agent-hours — plenty for a hackathon, but a single unsupervised session that thrashes on environment setup can burn a visible fraction of it. The documented 42→12 ACU case study implies supervision pays for itself.

### Gaps
- `https://docs.devin.ai/product-guides/parallel-sessions`, `https://docs.devin.ai/essentials/best-practices` and several `/essentials/` and `/billing/` URLs returned **404** — the docs were reorganized (correct prefixes appear to be `/essential-guidelines/`, `/product-guides/`, `/admin/billing/`, `/use-cases/`). So I have the *existence* of Parallel Sessions and Dynamic Workflows from the docs index, but **not their contents**: I cannot state per-plan concurrent-session limits or the Dynamic Workflows API shape. Check [llms.txt](https://docs.devin.ai/llms.txt) for live URLs.
- I could not verify Devin's current SWE-bench-style score from Cognition directly; the only numbers I found are from third-party reviews (below).
- I did not verify the Devin API's exact endpoints for creating/polling sessions. [API overview](https://docs.devin.ai/) is the place to look; the docs index describes "304-page API documentation" plus OpenAPI specs.

---

## Devin: what it is genuinely good at vs bad at

### Takeaway
Cognition's own rule is the **three-hour rule** — "if a task would take you three hours or less,
Devin can most likely do it" — and the binding requirement is a *verifiable* success criterion.
Independent reviews converge on the same failure mode from the other direction: Devin degrades
badly on vague requirements and on tasks requiring understanding of a large interdependent codebase,
and always needs human review.

### Cited Findings

**Cognition's own guidance**
- "Devin can handle most tasks, excluding extremely difficult tasks. As a rule of thumb, if you can do it in three hours, Devin can most likely do it." — [docs.devin.ai](https://docs.devin.ai/)
- "if a task would take you three hours or less, Devin can most likely do it"; longer work "should be split into parallel sessions" — [When to Use Devin](https://docs.devin.ai/essential-guidelines/when-to-use-devin)
- Devin "excels at medium to hard complexity engineering tasks with clear success criteria". Ideal tasks have **verifiable outcomes** (passing tests, CI checks, matching patterns), **sufficient context** (examples, existing patterns, relevant files), and **well-defined scope with explicit end states** — [When to Use Devin](https://docs.devin.ai/essential-guidelines/when-to-use-devin)
- Poor fit: "Tasks lacking clear success criteria, minimal context, or ambiguous endpoints"; also "Very large projects without breakdown into focused sessions" — [When to Use Devin](https://docs.devin.ai/essential-guidelines/when-to-use-devin)
- Cognition's listed strengths: Linear/Jira ticket handling, code migrations and framework upgrades, parallel task management, bug reproduction and fixes, unit-test writing, building integrations and internal tools — [docs.devin.ai](https://docs.devin.ai/)
- For unfamiliar codebases the docs recommend providing "examples or patterns for Devin to follow" and scoping collaboratively first: "explore your codebase with Ask Devin's advanced code search, scope the approach, and let Devin auto-generate a high-context prompt" — [When to Use Devin](https://docs.devin.ai/essential-guidelines/when-to-use-devin)
- Cognition's own candor note: "In some cases Devin may not function exactly as referenced, or documentation may be out of date." — [docs.devin.ai](https://docs.devin.ai/)
- Marketing-side claim relevant to research tasks: Devin "can train and fine tune its own AI models by setting up fine tuning for a large language model given only a link to a research repository on GitHub" — [Cognition: Introducing Devin](https://cognition.com/blog/introducing-devin). **This is a vendor demo claim from the original launch post, not an independently verified result.**

**Independent reviews** — all via [Devin review 2026 aggregation of independent tests](https://www.idlen.io/blog/devin-ai-engineer-review-limits-2026/) and related reviews:
- Reported ~15% success rate on complex, ill-defined tasks, and a SWE-bench score of 13.86% ("about 1-in-7 real GitHub issues end-to-end") — [idlen.io Devin review](https://www.idlen.io/blog/devin-ai-engineer-review-limits-2026/)
- One independent test run reported Devin failing 14 of 20 tasks, succeeding 3, with 3 unclear — [idlen.io Devin review](https://www.idlen.io/blog/devin-ai-engineer-review-limits-2026/); see also [trickle.so Devin AI review](https://trickle.so/blog/devin-ai-review)
- "Devin handles isolated, clearly scoped tasks well but degrades significantly on anything requiring deep understanding of a large, interdependent codebase"; reviewers flag that "Devin working in a cloned copy cannot see the local state that causes many real-world bugs" — [idlen.io Devin review](https://www.idlen.io/blog/devin-ai-engineer-review-limits-2026/)
- Other reported weaknesses: performs poorly on vague requirements; "does not understand trade-offs the way experienced engineers do"; characterized as "a fast, tireless junior engineer who never asks clarifying questions and never tells you when it's out of its depth"; produces "working but verbose, poorly-structured code" that "introduces patterns that fail code review"; "human review is always required" — [idlen.io Devin review](https://www.idlen.io/blog/devin-ai-engineer-review-limits-2026/), [ai-coding-flow Devin review 2026](https://ai-coding-flow.com/blog/devin-review-2026/)
- **Caveat on these numbers:** these are secondary/aggregator reviews with small, non-standardized task sets and sometimes undated test runs. The SWE-bench 13.86% figure in particular dates from Devin's original 2024 evaluation era and is almost certainly stale for 2026 models. Treat as directional, not current.

### Inferences
- The single most actionable consequence: **you must manufacture a verifiable success criterion for the reproduction before you start the Devin session.** Devin's documented sweet spot is "task with a test that passes or fails"; a reproduction task framed as "get this paper working" has no such criterion, but "produce `repro/check.py` that asserts the reported metric is within ±X of the paper's Table 2 value, and make it exit 0" does. This reframing is the whole ballgame.
- The "cloned copy cannot see local state" criticism is actually *helpful* here: paper reproduction is a from-scratch-environment task, so there is no hidden local state to miss. Reproduction is unusually well-matched to Devin's isolation model compared to debugging a production system.
- The "never tells you when it's out of its depth" observation argues for short checkpoints: give Devin a 20–30 minute first milestone (environment builds, reference code runs at all) and inspect before letting it continue.

### Gaps
- I found no Cognition-published guidance specifically about *research* or *paper-reproduction* tasks. [When to Use Devin](https://docs.devin.ai/essential-guidelines/when-to-use-devin) does not address research tasks; the emphasis on verifiable endpoints implies open-ended research is a poor fit, but that is my inference, not a cited statement.
- The independent-review numbers above are all from secondary sources. I did not find a rigorous, dated, independent 2026 benchmark of Devin from a primary evaluator.

---

## Devin: best practices for a paper-reproduction task

### Takeaway
Cognition's prompting advice reduces to four rules that happen to be exactly what a reproduction
task needs: be maximally specific, supply the context and the patterns to follow, define success as
a machine-checkable condition, and break the work into checkpointed sub-tasks each with its own
session. Encode the repeated procedure in a Playbook with Overview / Procedure / Specifications /
Advice / Forbidden Actions / What's Needed From User, and run two Devins on the same Playbook to
surface errors fast.

### Cited Findings

All from [Instructing Devin Effectively](https://docs.devin.ai/essential-guidelines/instructing-devin-effectively) unless noted:
- "**Be as specific as possible**" — make decisive calls rather than leaving open-ended choices; vague directives like "improve performance" should become targeted requests with measurable targets
- **Context and references:** supply domain knowledge via documentation links, code examples to emulate, and specific file names; share Figma designs for visual work; point Devin at the relevant API docs
- **Success criteria:** define completion explicitly. Avoid "make sure it works"; specify expected outputs, HTTP status codes, or design-compliance measures. Per the search-surfaced doc text: "Defines 'success' as emitting a specific event upon 80% usage. Devin knows exactly what to achieve."
- **Task breakdown:** "Split tasks into verifiable sub-tasks, and start one Devin session for each sub-task. Define what success looks like for each sub-task and optionally set checkpoints within each sub-task." "Breaking down complex tasks into smaller checkpoints helps Devin stay focused and reduces errors."
- **Self-testing:** instruct Devin to test its own work using the session's shell, IDE and browser before submitting — "Run npm test", verify endpoint responses, capture screenshots at multiple widths
- **Feedback loops:** "Frequent feedback (both from you and from tests/checks/linters) ensures Devin corrects mistakes effectively." Maintain build validations, lint checks and static analysis; Devin Review with Auto-Fix creates a continuous loop without manual intervention
- **Common mistakes:** "Vague instructions can lead Devin to implement solutions that don't align with your actual needs. Avoid statements that require Devin to make significant design or implementation decisions without guidance."
- **Scoping before implementing:** use **Ask Devin** to explore the codebase with advanced code search, scope the approach, and have it auto-generate a high-context prompt — [When to Use Devin](https://docs.devin.ai/essential-guidelines/when-to-use-devin)
- **Playbook sections to use** (full detail in the section above): Overview, Procedure (imperative, MECE steps), Specifications (postconditions + deliverable format), Advice and Pointers, Forbidden Actions, What's Needed From User — [Creating Playbooks](https://docs.devin.ai/product-guides/creating-playbooks)
- **Parallelization:** "Run 2+ Devins in parallel with the same playbook to quickly identify possible errors" — [Creating Playbooks](https://docs.devin.ai/product-guides/creating-playbooks). Longer-than-three-hour work "should be split into parallel sessions" — [When to Use Devin](https://docs.devin.ai/essential-guidelines/when-to-use-devin). Dedicated **Parallel Sessions** and **Dynamic Workflows** ("Orchestrate many Devin sessions with a deterministic Python script") features exist — [llms.txt](https://docs.devin.ai/llms.txt)
- **Session review:** **Session Insights** analyzes completed sessions to improve future prompts — [llms.txt](https://docs.devin.ai/llms.txt) — and the docs' own case study shows a prompt rewrite cutting a task from 42 to 12 ACUs — [docs.devin.ai](https://docs.devin.ai/use-cases/gallery/analyze-session-acu-efficiency)
- **Large changes:** Stacked PRs let Devin split a large change into "ordered, reviewable stacks of pull requests" — [llms.txt](https://docs.devin.ai/llms.txt) — useful if the reproduction plus the extension is one big diff
- **MCP:** Devin can be connected to external tools via MCP servers, and there is an official Devin MCP Server letting external tools manage Devin sessions — [llms.txt](https://docs.devin.ai/llms.txt)

### Inferences
Concrete Playbook skeleton for the reproduction, derived from the documented section list:
- **Overview** — "Reproduce Result R from paper P (arXiv ID, DOI). The deliverable is a repo where `make repro` prints the reproduced value and `python repro/check.py` exits 0 when it is within tolerance T of the published value V."
- **Procedure** — imperative, MECE: (1) read `paper/paper.pdf` and `paper/CLAIM.md`; (2) clone the reference repo at the pinned commit into `vendor/`; (3) create the environment with the pinned versions in `env/requirements.txt`; (4) run the reference entry point on the provided small input at `data/`; (5) write `repro/check.py` asserting the tolerance; (6) record the observed value and environment in `repro/RESULT.md`; (7) open a PR.
- **Specifications** — postconditions: `check.py` exits 0; `RESULT.md` contains observed value, tolerance, hardware, wall-clock; no network access needed at run time.
- **Advice and Pointers** — "the reference repo pins an old dependency; prefer pinning over upgrading"; "if a step exceeds 10 minutes, reduce the input size and say so in RESULT.md rather than waiting".
- **Forbidden Actions** — "Do not retrain any model from scratch. Do not re-download datasets; use `data/`. Do not modify `vendor/`. Do not change the published value in `CLAIM.md` to match your output. Do not substitute a different metric."
- **What's Needed From User** — paper PDF path, pinned reference commit, dataset location, API keys if any, the exact published value and the agreed tolerance.
That last Forbidden Action ("do not change the claim to match the output") is the one I would not omit: it is the reproduction-specific analogue of the docs' own "forbidden actions preventing file overwrites" example and guards against the agent closing the loop the wrong way.
- Supply the paper **in the repo**, not just as a link: a PDF plus a hand-written `CLAIM.md` that states the single number being reproduced, its location in the paper (table/figure/section), and the tolerance. This satisfies the docs' "provide domain knowledge via documentation links, code examples to emulate, and specific file names" requirement in the most Devin-legible way.
- Also commit a `SKILL.md` ([Skills product guide](https://docs.devin.ai/product-guides/skills)) for the durable conventions — how to build the env, where results go, the `allowed-tools` restriction — so that every session, including ones you start later for the "go further" phase, inherits them without re-prompting.
- Parallelization plan for 24–48h: session A reproduces, session B independently reproduces with the same Playbook (the documented error-surfacing trick, which here doubles as an independent replication), session C builds the extension harness against the `check.py` interface while A/B are still running. The interface contract (`check.py` exit code) is what lets C start before A finishes.
- Supervise at checkpoints, not continuously: the docs' "optionally set checkpoints within each sub-task" plus independent reviewers' "never tells you when it's out of its depth" together imply a cadence of ~20–30 minutes of inspection.

### Gaps
- I could not fetch the Parallel Sessions or Dynamic Workflows pages (404 on the URLs I tried), so I have no documented per-plan cap on concurrent sessions and no code sample for the Dynamic Workflows Python orchestration API. This matters if you want to script >2 sessions.
- No Cognition-published Playbook example specifically for paper reproduction. The nearest published example is the "R Data Science Tutorial" playbook ([Creating Playbooks](https://docs.devin.ai/product-guides/creating-playbooks)), which is structurally similar (dataset in, notebook + trained model out) and is the best template to copy.

---

## Published accounts of agents reproducing papers, and what makes a target tractable

### Takeaway
There is a substantial 2024–2026 benchmark literature on agents reproducing papers and it is
uniformly sobering: best-reported scores cluster at **21–37%** depending on how much is handed to
the agent, versus **41.4%** for ML PhDs given 48 hours on PaperBench. The practical lesson for a
hackathon is that tractability is bought by *handing the agent the code, the data, and a single
numeric claim with a tolerance* — which is exactly the difference between CORE-Bench (code+data
provided) and PaperBench (from scratch).

### Cited Findings

**PaperBench (OpenAI)** — [arXiv:2504.01848](https://arxiv.org/abs/2504.01848) / [PaperBench PDF](https://cdn.openai.com/papers/22265bac-3191-44e5-b057-7aaacd8e90cd/paperbench.pdf):
- Agents must replicate **20 ICML 2024 Spotlight and Oral papers** from scratch, requiring them to "understand paper contributions, develop a codebase, and successfully execute experiments"
- Graded against hierarchical rubrics co-developed with the original paper authors, decomposing into **8,316 individually gradable tasks**
- Best agent in the paper: **Claude 3.5 Sonnet (New) with open-source scaffolding at 21.0%** average replication score
- "models do not yet outperform the human baseline"
- Secondary reporting gives **o1 with an enhanced prompt at 24.4%**, against a **human ML PhD baseline of 41.4% over 48 hours** — [blog.pebblous.ai analysis](https://blog.pebblous.ai/blog/paper-code-reproducibility/en/); see also [emergentmind PaperBench topic page](https://www.emergentmind.com/topics/paperbench-benchmark). **The 24.4% and 41.4% figures come from secondary summaries, not from the abstract I fetched — verify in the PDF before quoting.**
- Evaluation code is open-sourced

**CORE-Bench (Princeton)** — [arXiv:2409.11363](https://arxiv.org/abs/2409.11363):
- **270 tasks from 90 scientific papers** across computer science, social science and medicine
- The task is to reproduce study results "**using the provided code and data**" — i.e. code and data are handed over, and reproduction is still the question
- Three difficulty tiers; the best agent reached only **21% accuracy on the hardest tasks**
- Baselines: AutoGPT (general) and CORE-Agent (task-specific), each on GPT-4o or GPT-4o-mini
- The framing is that computational reproducibility "remains surprisingly challenging" despite provided artifacts, implicating environment configuration, dependency management and data accessibility

**ResearchCodeBench** — [arXiv:2506.02314](https://arxiv.org/pdf/2506.02314) / [project site](https://researchcodebench.github.io/) / [NeurIPS 2025 Datasets & Benchmarks proceedings](https://proceedings.neurips.cc/paper_files/paper/2025/file/cd0d0a873cc3e601c76f46dccc3d4c5f-Paper-Datasets_and_Benchmarks_Track.pdf):
- **212 coding challenges** drawn from top 2024–2025 ML papers (NeurIPS, ICLR, CVPR, arXiv), covering generative modeling, vision, theory and RL; 30+ proprietary and open-source LLMs evaluated
- "Even the best models correctly implement less than 40% of the code"; **Gemini-2.5-Pro-Preview best at 37.3%**, O3 (High) 32.3%, O4-mini (High) 30.8%
- Grading is on whether the code actually runs — no LLM judge — per [blog.pebblous.ai](https://blog.pebblous.ai/blog/paper-code-reproducibility/en/)

**MLE-bench (OpenAI)** — [arXiv:2410.07095](https://arxiv.org/pdf/2410.07095):
- **75 Kaggle ML-engineering competitions**, testing training models, preparing datasets, running experiments
- Best setup in the original paper: **o1-preview with AIDE scaffolding reaching at least Kaggle bronze in 16.9%** of competitions
- Later reported results: **MLE-STAR with Gemini-2.0 at 43.9% medal rate; AIRA with MCTS/evolutionary methods at 47.7%** — [emergentmind MLE-bench topic page](https://www.emergentmind.com/topics/mle-bench). **These later figures are from a secondary aggregator; verify against the original MLE-STAR / AIRA papers.**
- Documented limitations: reconstructed test splits and graders make human comparisons approximate; the benchmark omits problem formulation, data selection and metric design; and it is expensive to reproduce — [emergentmind MLE-bench topic page](https://www.emergentmind.com/topics/mle-bench)

**Cross-benchmark comparison as reported by a third party** — [blog.pebblous.ai: "Released Paper Code: AI Agents Ran It, and Half of It Failed"](https://blog.pebblous.ai/blog/paper-code-reproducibility/en/):
- Top reproduction rates: ResearchCodeBench 37.3% (Gemini-2.5-Pro), PaperBench 24.4% (o1 + enhanced prompt), CORE-Bench hardest tier 22.2%
- Note the slight conflict with the CORE-Bench abstract's own "21%" figure for the hardest tasks ([arXiv:2409.11363](https://arxiv.org/abs/2409.11363)) — the 22.2% is from the aggregator. Prefer the primary number.

**Newer benchmarks in this space (existence confirmed, results not verified by me)**
- **RECLAIM: Can Agents Reproduce the Claims of Machine Learning Papers?** — [arXiv:2609.28850](https://arxiv.org/html/2609.28850v1)
- **NatureBench: Can Coding Agents Match the Published SOTA of Nature-Family Papers?** — [arXiv:2606.24530](https://arxiv.org/pdf/2606.24530)
- **PaperRepro: Automated Computational Reproducibility Assessment for Social Science Papers** — [arXiv:2603.00058](https://arxiv.org/pdf/2603.00058)
- **SA-Bench: Evaluating Semantic Alignment in LLM-Based Paper Reproduction** — [arXiv:2608.24252](https://arxiv.org/pdf/2608.24252)
- **TruthInsightBench** (scientific discovery agents) — [arXiv:2609.05079](https://arxiv.org/pdf/2609.05079)
- The paper-reproduction and ML-research-loop benchmark families are sometimes grouped as PaperBench (reproduce a target paper, rubric-scored) vs MLE-bench / MLAgentBench / MLGym (embed agents in ML experimentation loops) — [arXiv:2609.05079](https://arxiv.org/pdf/2609.05079)

### Inferences
- **The tractability gradient is the single most useful finding.** Ordered easiest to hardest by what the agent is given: ResearchCodeBench (implement a described function, code context provided) ≈ 37% → CORE-Bench (code and data provided, reproduce the number) ≈ 21% hardest tier → PaperBench (from scratch, full codebase + experiments) ≈ 21–24%. For a hackathon you want to be as far toward the ResearchCodeBench/CORE-Bench end as possible: **pick a paper whose code and data you already have in hand, and reproduce one number, not a system.**
- The PaperBench human baseline (41.4% for ML PhDs in 48 hours) is a gift for the pitch: it quantifies that reproduction is hard *for people too*, in exactly your hackathon's time budget. It also sets an honest expectation — a single clean reproduction of one result is a genuinely respectable outcome, not a low bar.
- CORE-Bench's finding that agents score ~21% *even with code and data provided* implicates environment/dependency setup as the dominant failure mode. That is precisely what Devin's VM + shell is built for, and it is also an argument for pinning everything and for doing the environment build yourself before handing off if you are short on time.
- These benchmarks also give you a ready-made framing for the "go further" half: build a *reproduction harness* as the deliverable (the `check.py` + Playbook + Modal fan-out) rather than just a reproduction, and evaluate it on several targets. That turns a single anecdote into a small eval — which is the shape the whole benchmark literature says the field needs.

### Gaps
- **I found no published first-hand account of using Devin specifically for scientific paper reproduction**, with or without outcomes. A targeted search returned only Cognition's own launch-post claim about fine-tuning from a research repo link ([Cognition blog](https://cognition.com/blog/introducing-devin)) and generic reproducibility literature. If such a write-up exists I did not find it; the report should say this is an unoccupied niche, which is itself a reason the hackathon story could land.
- **SUPER benchmark: I could not find it.** Two searches surfaced no SUPER results. It exists in my background knowledge as a benchmark on setting up and executing tasks from research repositories, but **I have no URL for it and will not assert its contents or numbers.** The report should either omit SUPER or flag it as unverified.
- I did not verify the headline numbers for RECLAIM, NatureBench, PaperRepro or SA-Bench — only that the papers exist at the cited arXiv URLs. Several of these have 26xx arXiv IDs (2026), so they are the most current work in this area and worth a direct read if the report needs current numbers.
- Devin's own ACU cost for a reproduction-shaped task is undocumented as far as I could find.

---

## Practical framing: a convincing "reproduce, then go further" story, and the traps

### Takeaway
The convincing version is narrow and verifiable: one numeric claim, reproduced with a committed
`check.py` that exits 0, then pushed past with an extension that is measured by the *same* harness.
The traps are all variations of "the agent cannot finish in the time available": large training
runs, proprietary or gated data, and papers with no released code.

### Cited Findings
- Devin's documented sweet spot requires "verifiable outcomes (passing tests, CI checks, matching patterns)" and "well-defined scope with explicit end states"; tasks with "ambiguous endpoints" are poor fits — [When to Use Devin](https://docs.devin.ai/essential-guidelines/when-to-use-devin)
- The three-hour rule bounds a single session; longer work must be split into parallel sessions — [When to Use Devin](https://docs.devin.ai/essential-guidelines/when-to-use-devin)
- CORE-Bench provides code *and* data and still finds ~21% best-agent accuracy on its hardest tier, identifying environment configuration and dependency management as the obstacles — [arXiv:2409.11363](https://arxiv.org/abs/2409.11363)
- PaperBench's from-scratch setting (codebase + experiment execution) yields 21.0% for the best agent in-paper — [arXiv:2504.01848](https://arxiv.org/abs/2504.01848)
- MLE-bench's own stated limitations include that it "is expensive to reproduce" — [emergentmind MLE-bench](https://www.emergentmind.com/topics/mle-bench) — a direct warning about compute-heavy targets
- ResearchCodeBench, which asks for *implementation of a described contribution* rather than full replication, gets the highest scores (37.3%) of the three — [arXiv:2506.02314](https://arxiv.org/pdf/2506.02314)
- The precedent sponsor-track wording for Modal is maximally permissive — "Any project that leverages Modal's serverless compute platform" — so the track is won on quality of use, not on category fit — [AI Agent & Infra Hackathon (Devpost)](https://ai-agent-infra.devpost.com/)

### Inferences
- **Target-selection checklist** (derived from the tractability gradient above): the paper has released code at a pinnable commit; the key result is a *single number* in a table or figure; the data is public and small enough to download in minutes; the result runs on CPU or one small GPU in under ~10 minutes; and you can state a tolerance in advance. Each of these converts a PaperBench-hard task into a CORE-Bench- or ResearchCodeBench-shaped one.
- **Traps, ranked by how much hackathon time they destroy:**
  1. **Large training runs** — directly contradicts the three-hour rule and MLE-bench's "expensive to reproduce" warning; also burns Modal GPU credits and the 10-GPU concurrency cap.
  2. **Proprietary, gated or licensed data** — unfixable in 48 hours regardless of agent quality, and CORE-Bench names data accessibility as a reproduction obstacle.
  3. **No released code** — pushes you into the PaperBench from-scratch regime where the best reported score is ~21%.
  4. **A result that is a *system* rather than a number** — no machine-checkable success criterion, which is the exact failure mode Devin's docs warn about.
  5. **Stale dependencies with no pins** — the CORE-Bench finding says this is where agents actually die; mitigate by pinning in the Playbook's Advice section.
- **The "go further" move that reads best**, given the project: reproduce the paper's key number, then show that the same claim fails (or holds) under a *generalization* the paper did not test, measured by the same `check.py`. For a protocol-validation project the natural extensions are: run the reproduced checker over a much larger generated corpus than the paper used (Modal `.map()` makes this the cheap part), or show the paper's result is sensitive to a parameter it held fixed. Both reuse the harness, so the "further" step costs hours rather than days.
- **The joint story that wins both tracks simultaneously:** Devin reproduces the paper and emits a verifiable harness; Modal then runs that harness at a scale the paper did not — thousands of cases via `.map()`, with the heavy formal toolchain prebuilt in the Image. That makes Modal load-bearing rather than decorative (the fan-out is only possible because of it) and makes Devin's output a measured artifact rather than an anecdote. It also means a failure in one half still leaves a demo: the harness alone is a deliverable, and the fan-out alone is a deliverable.
- **Honesty is a scoring asset here.** Given published agent reproduction rates of 21–37% and a human PhD baseline of 41.4% in 48 hours, a presentation that says "we reproduced one result, here is the exact tolerance, here is what Devin got wrong on the first two attempts, here is the harness" is more credible than one claiming a full replication. The benchmark numbers give you the citation to justify the framing.

### Gaps
- I have no information about your actual hackathon's judging rubric. The only judging criterion I could read on the precedent Devpost event was "Technical Implementation", with the rest of the criteria incomplete on the page — [AI Agent & Infra Hackathon (Devpost)](https://ai-agent-infra.devpost.com/).
- I found no hackathon write-ups describing a "reproduce a paper with Devin" project, so I have no precedent for how judges have received this specific story shape.
- I could not verify the exact wording of your event's "Best use of Devin" challenge (pick a paper, reproduce a key result, push past it). The closest I found was Hack the North 2026's "Cognition: Best Use of Devin — the most interesting and technically impressive project built with Devin, $5,000 in Devin credits" ([Hack the North 2026](https://hackthenorth2026.devpost.com/)), which has no paper-reproduction framing. **The paper-reproduction framing in the assignment is therefore unconfirmed against any public page I could find.**

---

## Appendix: verification checklist for the morning of the hackathon

Because so much of the above is version-sensitive, these are the pages to re-check first:
- [Modal 1.0 migration guide](https://modal.com/docs/guide/modal-1-0-migration) — confirm no new renames landed
- [modal.Function reference](https://modal.com/docs/reference/modal.Function) — confirm `.map`, `.starmap`, `.spawn`, `.spawn_map` signatures (I could not verify spawn-family names)
- [Modal pricing](https://modal.com/pricing) — confirm Starter credits ($30/mo) and the 100-container / 10-GPU caps
- [Modal GPU guide](https://modal.com/docs/guide/gpu) — confirm GPU strings, and add a payment method before the event
- [Modal Images guide](https://modal.com/docs/guide/images) — confirm the Image Builder Version in workspace settings, then do not change it
- [docs.devin.ai/llms.txt](https://docs.devin.ai/llms.txt) — the live URL index; several `/essentials/` and `/billing/` paths 404'd for me, so resolve URLs from here
- [Devin Knowledge guide](https://docs.devin.ai/product-guides/knowledge) — confirm the Knowledge→Skills deprecation status before investing in either
- [Devin Skills guide](https://docs.devin.ai/product-guides/skills) — confirm the `.agents/skills/<name>/SKILL.md` path and frontmatter keys
- [Devin pricing](https://devin.ai/pricing) — confirm plan quotas and ACU overage rate (my numbers are from a third-party aggregator)
