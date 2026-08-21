# Contributing to Agent Session Bridge

We welcome contributions to this reference implementation! 

## Local Setup
1. Clone the repository.
2. Create a virtual environment: `python -m venv venv`
3. Activate the environment: `source venv/bin/activate` (Linux/macOS) or `.\venv\Scripts\activate` (Windows).
4. Install dependencies: `pip install -e .`

## Guidelines
* **No Real User Data:** Any fixtures added to `fixtures/` MUST be completely synthetic or explicitly public-safe. Do not commit actual credentials, proprietary tokens, or private conversation histories.
* **Loss Accounting:** If you add a new source parser (e.g., OpenAI, Kimi), it MUST accurately populate the canonical `LossReport` to account for any fields or structures it drops.
* **Style:** Code is formatted and linted with `ruff`. Use `ruff check .` to ensure compliance.
* **Typing:** Use strict typing. Ensure `mypy --namespace-packages --explicit-package-bases src/` passes.
* **Testing:** All new adapters must include corresponding unit tests in `tests/`. Run tests with `pytest`.
