# scripts/

Utility scripts that are not part of the production application or test suite.
These are development and presentation helpers only.

| Script | Purpose | Dependencies |
|---|---|---|
| `create_ppt.py` | Generates `AgentTrade_Presentation.pptx` from Python. | `python-pptx` (see `requirements-dev.txt`) |
| `patch_main.py` | One-time text-replacement patch applied during development to add `user_owns_stock` logic. Already applied — kept for audit trail only. | stdlib only |

## Usage

```sh
# Install dev dependencies first
pip install -r requirements-dev.txt

# Generate presentation
python3 scripts/create_ppt.py
```

> These scripts are not imported by the API, smoke tests, or evaluator.
> Do not import them from application code.
