# Contributing

## Workflow

1. Fork the repository and create a branch from `master`.
2. Keep changes focused and update documentation when behavior or setup changes.
3. Run the repo-local checks from a clean checkout:

```bash
scripts/setup
scripts/lint
scripts/test
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
- Prefer the existing repo-local scripts over ad hoc commands.
- Avoid unrelated cleanup in the same pull request.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](./LICENSE).
