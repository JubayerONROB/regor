# Security and safe operation

## Secrets

- Credentials never live in a repository. Kaggle: a `kaggle.json` outside the repo,
  referenced by `$REGOR_KAGGLE_CREDENTIALS`, or the CLI's own configuration. GitHub: `gh`
  keyring or Git Credential Manager.
- The Kaggle adapter passes credentials only through the `kaggle` child-process
  environment. It never writes them to kernels, run records, logs or configs, and
  redacts 32-hex keys from error text.
- `.gitignore` (repo and every new project) excludes `pat.txt`, `*.pat`, `.env`,
  `kaggle*.json`, `.kaggle/`, `*credentials*.json`, keys and certificates.
- `regor security scan [PATH]` reports **file, line and rule only, never the
  matched text**. Rules: GitHub tokens (classic and fine-grained), `sk-` style API keys,
  AWS access keys, Google API keys, Slack and Hugging Face tokens, private-key blocks,
  Kaggle `"key"` fields, generic `password/token/secret = "..."` assignments, and
  sensitive filenames. `.env.example` is allowed. A reviewed test fixture line can opt
  out with the comment `regor-allow-secret`.
- Every Kaggle bundle is scanned (unpacked, so base64 cannot hide anything) before
  push. A finding aborts the push.

## Before every commit

```bash
regor security scan .
git status
git diff --cached --stat          # inspect the full staging area
git add <explicit paths>          # never blanket-add in repos with data or credentials
```

If anything sensitive is staged: unstage it, fix `.gitignore`, and if it was ever
committed, rotate the credential. History rewriting does not un-leak a pushed secret.

## Consequential operations need a named human

| Operation | Control |
|---|---|
| Remote, GPU or long runs | single-use approval bound to the config hash (`regor approve`) |
| Approving or rejecting proposals | `--by NAME`, decision log |
| Hypothesis verdicts | `--by NAME`; supported/refuted requires verified claims |
| Protocol changes | `regor decision add` |
| Deleting data or runs | not provided by the engine; deliberate manual action |
| External submission, publication | outside the engine; manual |

These controls are **procedural**. Anyone with shell access can edit the YAML. To keep an
AI assistant from granting approvals, deny those commands in Claude Code's permission
settings. See `templates/claude_settings.example.json`, which denies
`regor approve`, `proposals approve`, `hypothesis set`, `git push` and Kaggle CLI
pushes, and asks before other risky commands.

## Data protection

- Raw data is gitignored by default. Commit manifests, never datasets you lack rights
  to redistribute.
- Hostnames are stored hashed in run provenance.
- Unpublished manuscripts belong to their project repositories, which should be private
  unless the researcher decides otherwise.

## Reporting a vulnerability

Open a private security advisory on the GitHub repository rather than a public issue.
