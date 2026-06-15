# examplars

Runnable design pattern examples in Python. Each pattern is self-contained, backed by a real database, and executable with a single command.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/sampathreddy22/examplars
cd examplars
uv sync
```

## Running a Pattern

```bash
uv run examplars <pattern>
```

## Patterns

| Pattern | Description | Run |
|---|---|---|
| [Saga](patterns/saga/README.md) | Distributed transaction with compensating rollback — money transfer across accounts | `uv run examplars saga` |

## Adding a New Pattern

1. Create `patterns/<name>/` with a `main.py` that exposes `run()`
2. Register it in `patterns/cli.py`:

```python
REGISTRY: dict[str, str] = {
    "saga": "patterns.saga.main",
    "your-pattern": "patterns.your_pattern.main",  # ← add here
}
```

3. Run it: `uv run examplars your-pattern`

## Project Layout

```
examplars/
├── pyproject.toml       ← uv project + script entry point
├── patterns/
│   ├── cli.py           ← pattern dispatcher
│   └── saga/            ← money transfer saga pattern
│       ├── README.md
│       ├── db.py
│       ├── steps.py
│       ├── orchestrator.py
│       └── main.py
└── data/                ← runtime DBs (gitignored)
```
