# Boxes — Claude Instructions

## Repository

This is a personal fork of `florianfesti/boxes`, maintained independently at `https://github.com/tracugl/boxes`.

## Pull Requests

**NEVER open a PR targeting `florianfesti/boxes`.** All PRs must target this repo (`tracugl/boxes`) only.

When creating a PR, always explicitly pass `--repo tracugl/boxes` to the `gh` CLI to prevent accidental upstream targeting:

```bash
gh pr create --repo tracugl/boxes --base master
```

The upstream remote exists solely for fetching changes into this fork. Nothing is ever pushed or PR'd back to it.
