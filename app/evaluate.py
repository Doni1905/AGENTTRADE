"""Run the 25 frozen questions x three retrieval modes x two local LLMs."""
import argparse
import csv
import json
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = json.loads((ROOT / 'data' / 'questions.json').read_text())
MODES = ('none', 'fixed', 'agentic')


def score(case, answer):
    text = answer.lower()
    present = all(t.lower() in text for t in case['must_contain'])
    forbidden = not any(t.lower() in text for t in case.get('must_not_contain', []))
    cite = bool(re.search(r'\[(?:doc|source)\s*\d+\]', text))
    return {'accuracy': int(present and forbidden),
            'reasoning_quality': int(present and forbidden and any(x in text for x in ('because', 'policy', 'source'))
                                     and (cite or case.get('no_citation_ok', False))),
            'citation_present': int(cite)}


def run(url, models, repetitions, output, report):
    if repetitions < 1 or repetitions > 10:
        raise ValueError('--repeats must be between 1 and 10')
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    started = datetime.now(timezone.utc).isoformat()
    with httpx.Client(timeout=360) as client:
        for model in models:
            for mode in MODES:
                for case in QUESTIONS:
                    for repeat in range(1, repetitions + 1):
                        body = {'question': case['question'], 'ticker': case['ticker'],
                                'model': model, 'mode': mode, 'evaluation': True}
                        start = time.monotonic()
                        try:
                            r = client.post(url, json=body)
                            r.raise_for_status()
                            raw = r.json()
                            if not isinstance(raw, dict) or not isinstance(raw.get('answer'), str) or not raw['answer'].strip():
                                raise ValueError('workflow returned no answer; verify the response node')
                            answer = raw['answer']
                            values = score(case, answer)
                            error = ''
                        except (httpx.HTTPError, ValueError) as exc:
                            answer = ''
                            values = {'accuracy': 0, 'reasoning_quality': 0, 'citation_present': 0}
                            error = str(exc)[:500]
                        rows.append({'model': model, 'mode': mode, 'case_id': case['id'],
                                     'repeat': repeat, 'question': case['question'], 'answer': answer,
                                     'latency_seconds': round(time.monotonic() - start, 2), 'error': error, **values})
                        print(f'{model} {mode} {case["id"]} #{repeat}: {values["accuracy"]} {error[:60]}', flush=True)
    with (output / 'raw.csv').open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    summary = []
    for model in models:
        for mode in MODES:
            block = [r for r in rows if r['model'] == model and r['mode'] == mode]
            valid = [r for r in block if not r['error']]
            groups = [[r['answer'].strip().lower() for r in valid if r['case_id'] == case['id']]
                      for case in QUESTIONS]
            consistency = (sum(len(v) == repetitions and len(set(v)) == 1 for v in groups) / len(groups)
                           if repetitions > 1 else None)
            summary.append({'model': model, 'mode': mode, 'n': len(block), 'successful': len(valid),
                            'accuracy': round(statistics.mean(r['accuracy'] for r in valid), 3) if valid else None,
                            'reasoning_quality': round(statistics.mean(r['reasoning_quality'] for r in valid), 3) if valid else None,
                            'citation_rate': round(statistics.mean(r['citation_present'] for r in valid), 3) if valid else None,
                            'exact_response_consistency': round(consistency, 3) if consistency is not None else None,
                            'errors': len(block) - len(valid)})
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    def fmt(value):
        return 'n/a' if value is None else f'{value:.3f}'
    lines = ['# Evaluation results', '', f'Run began (UTC): {started}.',
             f'{len(QUESTIONS)} frozen questions, {repetitions} repeat(s) per model and retrieval mode.',
             '', '| Model | RAG mode | Successful / attempted | Accuracy | Reasoning proxy | Citation rate | Exact consistency | Errors |',
             '|---|---|---:|---:|---:|---:|---:|---:|']
    for item in summary:
        lines.append(f'| {item["model"]} | {item["mode"]} | {item["successful"]} / {item["n"]} | '
                     f'{fmt(item["accuracy"])} | {fmt(item["reasoning_quality"])} | {fmt(item["citation_rate"])} | '
                     f'{fmt(item["exact_response_consistency"])} | {item["errors"]} |')
    lines += ['', 'Scores exclude failed requests and show their counts explicitly; a row with no successful requests is n/a.',
              'Accuracy is strict labeled-term matching, not expert judgment. Reasoning is a citation/rationale proxy.',
              'With one repeat, consistency is n/a; use three or more repeats for a consistency comparison.',
              'Inspect raw.csv and n8n traces for actual source support and tool calls. No trading performance inference.']
    (output / 'RESULTS.md').write_text('\n'.join(lines) + '\n')
    # Only replace this bounded section after a completed run, never inject illustrative metrics.
    if report:
        text = report.read_text()
        start_marker = '<!-- EVAL_RESULTS_START -->'
        end_marker = '<!-- EVAL_RESULTS_END -->'
        if text.count(start_marker) != 1 or text.count(end_marker) != 1:
            raise ValueError('Report has no unique evaluation results markers; outputs remain in results/')
        insertion = f'{start_marker}\n' + '\n'.join(lines) + f'\n{end_marker}'
        text = text[:text.index(start_marker)] + insertion + text[text.index(end_marker) + len(end_marker):]
        report.write_text(text)
    print(f'Real responses and scores saved to {output}; report: {report if report else "not updated"}')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--url', default='http://localhost:5678/webhook/agenttrade-analyze')
    p.add_argument('--models', nargs=2, default=['qwen2.5:3b', 'llama3.2:3b'])
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--output', type=Path, default=ROOT / 'results')
    p.add_argument('--report', type=Path, default=ROOT / 'docs' / 'REPORT.md')
    args = p.parse_args()
    run(args.url, args.models, args.repeats, args.output, args.report)
