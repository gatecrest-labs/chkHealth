# Contributing

Thank you for considering a contribution to check.health!

## Development Setup

```bash
git clone <repo-url>
cd check.health
uv sync
cp .env.example .env  # fill in values
python manage_users.py add dev --role admin
uv run flask --app app run --debug
```

## Running Tests

```bash
uv run pytest -v
```

## Branch Convention

- `main` — stable releases
- `development` — active development; open PRs against this branch
- Feature branches: `feat/<short-description>`

## Pull Requests

1. Fork the repo and create a feature branch from `development`
2. Write tests for new behaviour
3. Ensure all tests pass (`uv run pytest`)
4. Open a PR against the `development` branch with a clear description
