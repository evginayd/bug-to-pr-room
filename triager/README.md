# Triager (v2)

The custom Triager agent: Python on the Claude API, connected to Switch over
its agent protocol. Design and milestones: [docs/v2-custom-triager.md](../docs/v2-custom-triager.md).

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
cp .env.example .env   # fill in, then load it into your shell
triager --check
```
