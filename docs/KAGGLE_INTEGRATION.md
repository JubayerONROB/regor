# Kaggle integration

## Status

| Part | Status |
|---|---|
| Kernel packaging (script kernel, base64 bundle of declared code files + runtime + config) | implemented; mock-tested and **live-verified** |
| Secret scan of the unpacked bundle and metadata before push | implemented, tested |
| Push with retry policy (`max_retries`) | implemented; retry path mock-tested |
| Status polling, output download, terminal-state handling | implemented; mock-tested and **live-verified** |
| Runtime taken from the kernel's own status file, not time since push | implemented, **live-verified** |
| `CliKaggleClient` (official `kaggle` CLI via subprocess) | **live-verified** with CLI 1.7.4.5 (see below) |
| GPU kernels (`compute.device: gpu` → `enable_gpu`) | **live-verified**: the kernel reports which GPU it received |
| Accelerator *type* selection (`--accelerator`, CLI ≥ 2.0) | implemented; refuses with a clear error on older CLIs; **not live-tested** |
| Quota discovery | **not available** from the CLI; reported as "unknown" |
| Failure paths on live Kaggle (kernel error, cancellation) | mock-tested only |

### Live verification (2026-10-04)

A throwaway project ran one CPU and one GPU kernel (a seeded Monte Carlo estimate of pi,
no dataset) with `kaggle` CLI 1.7.4.5:

| Run | Kernel | Result |
|---|---|---|
| CPU | private script kernel, `enable_gpu: false` | COMPLETED / VALIDATED, 6 s, Linux on Kaggle |
| GPU | private script kernel, `enable_gpu: true`, no accelerator option | COMPLETED / VALIDATED, 10 s, **2× Tesla T4** reported by `nvidia-smi` |

Both runs were collected on the first poll, and their outputs validated against the
expected files and sample count. A check afterwards confirmed that the API key appears
in none of the run outputs. What GPU Kaggle assigns without an accelerator option
depends on the platform and can change, so the kernel records it as
`remote.gpu_assigned` in the run record.

Mock runs (`--mock-remote`) perform no computation. Their run records carry
`remote.mock: true` and **always validate as INVALID**, so they can never become
evidence.

## Configuration (project.yaml)

```yaml
execution:
  approval:
    required_for_backends: [kaggle]        # every Kaggle run needs a researcher approval
  kaggle:
    enabled: true
    credentials_env: REGOR_KAGGLE_CREDENTIALS  # env var holding the PATH to kaggle.json
    accelerator: null                       # e.g. a value your CLI version documents; null = platform default
    internet: false
    private: true
    dataset_sources: [owner/dataset-slug]   # mounted under /kaggle/input
    max_retries: 2
    poll_seconds: 60
```

The experiment spec stays backend-independent. The script reads `REGOR_DATA_DIR`
(`/kaggle/input` on Kaggle) or a path parameter.

## Credentials

1. Keep `kaggle.json` **outside** any repository (e.g. `%USERPROFILE%\.kaggle\`).
2. Set `REGOR_KAGGLE_CREDENTIALS` to its path, or rely on the CLI's own configuration.
3. The adapter reads the file only to build the **child process environment** for the
   `kaggle` command. It never writes credentials to the kernel, logs, run records or
   config files. Error text is redacted of 32-hex keys.

## Workflow

```bash
regor remote resources                     # what the CLI can report (often: unknown quota)
regor run EXP-001 --backend kaggle --dry-run
regor approve run EXP-001 --backend kaggle --runs 3 --by "Researcher Name"   # researcher only
regor run EXP-001 --backend kaggle         # packages, scans, pushes -> SUBMITTED
regor remote collect                       # poll once; download and validate finished runs
```

## Before the first real run

Check these against current Kaggle documentation and your account. Do not assume them:

- the account's phone verification (GPU access may require it)
- the current weekly GPU quota and per-session time limit
- which accelerators the API accepts and which CLI version supports selecting them
- that the CUDA build in the Kaggle image supports the assigned GPU. Have the script
  check for a *usable* GPU (run a small kernel), not just `cuda.is_available()`
- the dataset mount paths. Have the script search `REGOR_DATA_DIR` rather than hard-coding
  paths

Pushing a new version to an existing kernel slug replaces that slug's previous output,
so the adapter creates a unique slug per run.

## Limitations

- One kernel per run (per seed). There is no batching of seeds into one kernel yet.
- No remote cancellation command.
- `kernels status` parsing depends on CLI output format. A parse failure raises a clear
  error rather than guessing.
