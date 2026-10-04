# Kaggle integration

## Status

| Part | Status |
|---|---|
| Kernel packaging (script kernel, base64 bundle of declared code files + runtime + config) | implemented, tested (mock) |
| Secret scan of the unpacked bundle and metadata before push | implemented, tested |
| Push with retry policy (`max_retries`) | implemented, tested (mock) |
| Status polling, output download, terminal-state handling | implemented, tested (mock) |
| Runtime taken from the kernel's own status file, not time since push | implemented, tested (mock) |
| `CliKaggleClient` (official `kaggle` CLI via subprocess) | implemented; **not exercised against live Kaggle** in this repo |
| Accelerator selection (`--accelerator`, CLI ≥ 2.0) | implemented; refuses with a clear error on older CLIs; not live-tested |
| Quota and GPU availability discovery | **not available** from the CLI; reported as "unknown" |

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
    credentials_env: RP_KAGGLE_CREDENTIALS  # env var holding the PATH to kaggle.json
    accelerator: null                       # e.g. a value your CLI version documents; null = platform default
    internet: false
    private: true
    dataset_sources: [owner/dataset-slug]   # mounted under /kaggle/input
    max_retries: 2
    poll_seconds: 60
```

The experiment spec stays backend-independent. The script reads `RP_DATA_DIR`
(`/kaggle/input` on Kaggle) or a path parameter.

## Credentials

1. Keep `kaggle.json` **outside** any repository (e.g. `%USERPROFILE%\.kaggle\`).
2. Set `RP_KAGGLE_CREDENTIALS` to its path, or rely on the CLI's own configuration.
3. The adapter reads the file only to build the **child process environment** for the
   `kaggle` command. It never writes credentials to the kernel, logs, run records or
   config files. Error text is redacted of 32-hex keys.

## Workflow

```bash
research remote resources                     # what the CLI can report (often: unknown quota)
research run EXP-001 --backend kaggle --dry-run
research approve run EXP-001 --backend kaggle --runs 3 --by "Researcher Name"   # researcher only
research run EXP-001 --backend kaggle         # packages, scans, pushes -> SUBMITTED
research remote collect                       # poll once; download and validate finished runs
```

## Before the first real run

Check these against current Kaggle documentation and your account. Do not assume them:

- the account's phone verification (GPU access may require it)
- the current weekly GPU quota and per-session time limit
- which accelerators the API accepts and which CLI version supports selecting them
- that the CUDA build in the Kaggle image supports the assigned GPU. Have the script
  check for a *usable* GPU (run a small kernel), not just `cuda.is_available()`
- the dataset mount paths. Have the script search `RP_DATA_DIR` rather than hard-coding
  paths

Pushing a new version to an existing kernel slug replaces that slug's previous output,
so the adapter creates a unique slug per run.

## Limitations

- One kernel per run (per seed). There is no batching of seeds into one kernel yet.
- No remote cancellation command.
- `kernels status` parsing depends on CLI output format. A parse failure raises a clear
  error rather than guessing.
