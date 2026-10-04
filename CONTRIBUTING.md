# Contributing

Thanks for your interest in Regor. Bug reports, ideas and pull requests are welcome.

## Getting started

```bash
git clone https://github.com/JubayerONROB/regor.git
cd regor
python -m venv .venv
.venv/bin/pip install -e ".[dev]"        # Windows: .venv\Scripts\pip install -e ".[dev]"
python -m pytest
python examples/demo_synthetic/run_demo.py
```

## Ground rules for changes

- **Keep the core domain-free.** Field-specific knowledge belongs in domain profiles
  (`regor/domains.py`) or a project's `domain.yaml`, not in engine logic.
- **Never weaken an integrity check silently.** If you relax a validation or audit rule,
  explain why in the pull request and update `docs/RESULT_VALIDATION.md` or
  `docs/HALLUCINATION_PREVENTION.md`.
- **Tests must not need the network, a GPU, paid services or credentials.** Use the mock
  Kaggle client and injected fetchers. Build token-shaped test strings at runtime.
- **Add a test** for every bug fix and every new check.
- Run `regor security scan .` before committing.

## Reporting bugs

Please include your OS, Python version, the command you ran and its full output.
Report security problems privately through GitHub's security advisory feature, not in
a public issue.
