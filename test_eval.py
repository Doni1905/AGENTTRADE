import sys, tempfile, json
from pathlib import Path
import importlib.util

ROOT = Path('/Users/doni/.gemini/antigravity-ide/scratch/AGENTTRADE')
spec = importlib.util.spec_from_file_location('evaluate', ROOT / 'app' / 'evaluate.py')
evaluate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate)

class FakeEvaluationClient:
    def __init__(self, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def post(self, *args, **kwargs):
        class NewsResponse:
            def __init__(self, s, j): self.status_code = s; self.j = j
            def json(self): return self.j
            def raise_for_status(self): pass
        return NewsResponse(200, {"answer": "source [doc 1] because policy"})

evaluate.httpx.Client = FakeEvaluationClient
with tempfile.TemporaryDirectory() as folder:
    result_dir = Path(folder) / 'results'
    report = Path(folder) / 'REPORT.md'
    report.write_text('Before\n<!-- EVAL_RESULTS_START -->\nNot measured.\n<!-- EVAL_RESULTS_END -->\nAfter\n')
    evaluate.run('http://localhost:5678/fake', ['qwen2.5:3b', 'llama3.2:3b'], 1, result_dir, report)
    sums = json.loads((result_dir / 'summary.json').read_text())
    print("LEN:", len(sums))
    print("SUMS:", json.dumps(sums, indent=2))
