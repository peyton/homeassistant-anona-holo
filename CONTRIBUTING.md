# Contributing

## Workflow

1. Fork the repository and create a branch from `master`.
2. Keep changes focused and update documentation when behavior or setup changes.
3. Run the repo-local checks from a clean checkout:

```bash
mise bootstrap
just lint
just typecheck
just test
```

4. Open a pull request with a clear description of the user-visible change.

## Reporting bugs

Use [GitHub issues](../../issues/new/choose) and include:

- the Home Assistant version
- the integration version
- exact reproduction steps
- debug logs from startup through the failure
- any relevant screenshots or service-call payloads

## Style

- Python changes should follow PEP 8 and keep type hints intact.
- Prefer `mise bootstrap` for setup and the `justfile` for repo commands. The legacy `scripts/*` entry points remain as thin compatibility wrappers.
- Avoid unrelated cleanup in the same pull request.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](./LICENSE).
