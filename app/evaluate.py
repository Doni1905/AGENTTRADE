"""Run the 25 frozen questions x three retrieval modes x two local LLMs.

Improvements over v1:
 - Preserves raw_answer alongside scored_answer in raw.csv and raw_answers/ dir.
 - summary.json now includes separate blocks for 7B vs 3B routing and discovery queries.
 - Human source-support scoring via --scored-csv flag (reviewer marks source_support 0-2).
 - Reports real latency (p50/p95) per model+mode combination.
 - Surfaces real model errors without swallowing them.
"""
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

# Questions tagged as discovery (no explicit ticker) are evaluated separately.
_DISCOVERY_IDS = {q['id'] for q in QUESTIONS if not q.get('ticker')}


def score(case, answer):
    """Automated quality scoring for a single answer.

    Returns a dict with:
      accuracy              1 if all must_contain terms present and no forbidden term
      reasoning_quality     1 if accuracy=1 AND a rationale/citation marker is present
      citation_present      1 if a [doc N] or [source N] citation pattern is present
      source_support        None (filled in by human reviewer via --scored-csv)
    """
    text = answer.lower()
    present = all(t.lower() in text for t in case['must_contain'])
    forbidden = not any(t.lower() in text for t in case.get('must_not_contain', []))
    cite = bool(re.search(r'\[(?:doc|source)\s*\d+\]', text))
    return {
        'accuracy': int(present and forbidden),
        'reasoning_quality': int(
            present and forbidden
            and any(x in text for x in ('because', 'policy', 'source'))
            and (cite or case.get('no_citation_ok', False))
        ),
        'citation_present': int(cite),
        'source_support': None,   # placeholder; filled from --scored-csv
    }


def _latency_percentiles(values):
    if not values:
        return None, None
    s = sorted(values)
    p50 = s[len(s) // 2]
    p95 = s[min(int(len(s) * 0.95), len(s) - 1)]
    return round(p50, 2), round(p95, 2)


def run(url, models, repetitions, output, report, scored_csv=None):
    if repetitions < 1 or repetitions > 10:
        raise ValueError('--repeats must be between 1 and 10')
    output.mkdir(parents=True, exist_ok=True)
    raw_answers_dir = output / 'raw_answers'
    raw_answers_dir.mkdir(exist_ok=True)

    # Load human source-support scores if supplied.
    human_scores: dict[str, int] = {}
    if scored_csv and Path(scored_csv).exists():
        with open(scored_csv, newline='') as f:
            for row in csv.DictReader(f):
                key = f"{row['model']}|{row['mode']}|{row['case_id']}|{row['repeat']}"
                try:
                    human_scores[key] = int(row['source_support'])
                except (KeyError, ValueError):
                    pass

    rows = []
    started = datetime.now(timezone.utc).isoformat()
    with httpx.Client(timeout=360) as client:
        for model in models:
            for mode in MODES:
                for case in QUESTIONS:
                    for repeat in range(1, repetitions + 1):
                        body = {
                            'question': case['question'],
                            'ticker': case.get('ticker'),
                            'model': model,
                            'mode': mode,
                            'evaluation': True,
                        }
                        t0 = time.monotonic()
                        raw_answer = ''
                        error = ''
                        try:
                            r = client.post(url, json=body)
                            r.raise_for_status()
                            raw = r.json()
                            # Accept either the /research wrapper or a bare n8n answer.
                            if isinstance(raw, dict) and isinstance(raw.get('raw_answer'), str):
                                raw_answer = raw['raw_answer']   # preserved by main.py
                            elif isinstance(raw, dict) and isinstance(raw.get('answer'), str):
                                raw_answer = raw['answer']
                            if not raw_answer.strip():
                                # Surface the real model error.
                                error = (raw.get('error') or raw.get('message') or
                                         'workflow returned no answer; check n8n execution log')
                                raise ValueError(error)
                            values = score(case, raw_answer)
                        except (httpx.HTTPError, ValueError) as exc:
                            raw_answer = raw_answer or ''
                            values = {
                                'accuracy': 0, 'reasoning_quality': 0,
                                'citation_present': 0, 'source_support': None,
                            }
                            error = str(exc)[:500]

                        latency = round(time.monotonic() - t0, 2)
                        human_key = f"{model}|{mode}|{case['id']}|{repeat}"
                        values['source_support'] = human_scores.get(human_key)

                        row = {
                            'model': model, 'mode': mode, 'case_id': case['id'],
                            'repeat': repeat, 'is_discovery': case['id'] in _DISCOVERY_IDS,
                            'question': case['question'], 'answer': raw_answer,
                            'latency_seconds': latency, 'error': error,
                            **values,
                        }
                        rows.append(row)

                        # Persist raw answer to a separate file for trace inspection.
                        trace_path = raw_answers_dir / f"{model.replace(':', '_')}_{mode}_{case['id']}_{repeat}.txt"
                        trace_path.write_text(raw_answer or f'ERROR: {error}', encoding='utf-8')

                        print(
                            f'{model} {mode} {case["id"]} #{repeat}: '
                            f'acc={values["accuracy"]} cite={values["citation_present"]} '
                            f'src={values["source_support"]} lat={latency}s {error[:60]}',
                            flush=True,
                        )

    with (output / 'raw.csv').open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    # -----------------------------------------------------------------------
    # Build summary blocks: overall, by model tier (7B vs 3B), by query type.
    # -----------------------------------------------------------------------
    summary = []
    for model in models:
        tier = '7b' if '7b' in model.lower() else '3b'
        for mode in MODES:
            for query_type in ('all', 'named', 'discovery'):
                block = [
                    r for r in rows
                    if r['model'] == model and r['mode'] == mode and (
                        query_type == 'all' or
                        (query_type == 'discovery') == bool(r['is_discovery'])
                    )
                ]
                valid = [r for r in block if not r['error']]
                latencies = [r['latency_seconds'] for r in valid]
                p50, p95 = _latency_percentiles(latencies)
                groups = [
                    [r['answer'].strip().lower() for r in valid if r['case_id'] == case['id']]
                    for case in QUESTIONS
                    if query_type == 'all' or (query_type == 'discovery') == (case['id'] in _DISCOVERY_IDS)
                ]
                consistency = (
                    sum(len(v) == repetitions and len(set(v)) == 1 for v in groups) / len(groups)
                    if repetitions > 1 and groups else None
                )
                ss_vals = [r['source_support'] for r in valid if r['source_support'] is not None]
                summary.append({
                    'model': model, 'tier': tier, 'mode': mode, 'query_type': query_type,
                    'n': len(block), 'successful': len(valid),
                    'accuracy': round(statistics.mean(r['accuracy'] for r in valid), 3) if valid else None,
                    'reasoning_quality': round(statistics.mean(r['reasoning_quality'] for r in valid), 3) if valid else None,
                    'citation_rate': round(statistics.mean(r['citation_present'] for r in valid), 3) if valid else None,
                    'source_support_mean': round(statistics.mean(ss_vals), 3) if ss_vals else None,
                    'exact_response_consistency': round(consistency, 3) if consistency is not None else None,
                    'latency_p50_s': p50, 'latency_p95_s': p95,
                    'errors': len(block) - len(valid),
                })

    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')

    def fmt(value):
        return 'n/a' if value is None else f'{value:.3f}'

    lines = [
        '# Evaluation results', '',
        f'Run began (UTC): {started}.',
        f'{len(QUESTIONS)} frozen questions, {repetitions} repeat(s) per model and retrieval mode.',
        '',
        '## Overall (all query types)',
        '',
        '| Model | Tier | RAG mode | Succ/Att | Accuracy | Reasoning | Citation | Src-support | p50 lat | p95 lat | Errors |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for item in (s for s in summary if s['query_type'] == 'all'):
        lines.append(
            f'| {item["model"]} | {item["tier"]} | {item["mode"]} '
            f'| {item["successful"]} / {item["n"]} '
            f'| {fmt(item["accuracy"])} | {fmt(item["reasoning_quality"])} '
            f'| {fmt(item["citation_rate"])} | {fmt(item["source_support_mean"])} '
            f'| {fmt(item["latency_p50_s"])} | {fmt(item["latency_p95_s"])} '
            f'| {item["errors"]} |'
        )

    lines += [
        '',
        '## Named-ticker queries only',
        '',
        '| Model | Tier | RAG mode | Succ/Att | Accuracy | Reasoning | Citation | Src-support | p50 lat | p95 lat | Errors |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for item in (s for s in summary if s['query_type'] == 'named'):
        lines.append(
            f'| {item["model"]} | {item["tier"]} | {item["mode"]} '
            f'| {item["successful"]} / {item["n"]} '
            f'| {fmt(item["accuracy"])} | {fmt(item["reasoning_quality"])} '
            f'| {fmt(item["citation_rate"])} | {fmt(item["source_support_mean"])} '
            f'| {fmt(item["latency_p50_s"])} | {fmt(item["latency_p95_s"])} '
            f'| {item["errors"]} |'
        )

    lines += [
        '',
        '## Discovery queries only (no explicit ticker)',
        '',
        '| Model | Tier | RAG mode | Succ/Att | Accuracy | Reasoning | Citation | Src-support | p50 lat | p95 lat | Errors |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for item in (s for s in summary if s['query_type'] == 'discovery'):
        lines.append(
            f'| {item["model"]} | {item["tier"]} | {item["mode"]} '
            f'| {item["successful"]} / {item["n"]} '
            f'| {fmt(item["accuracy"])} | {fmt(item["reasoning_quality"])} '
            f'| {fmt(item["citation_rate"])} | {fmt(item["source_support_mean"])} '
            f'| {fmt(item["latency_p50_s"])} | {fmt(item["latency_p95_s"])} '
            f'| {item["errors"]} |'
        )

    lines += [
        '',
        'Scores exclude failed requests; error counts are explicit.',
        'Accuracy = strict labeled-term matching, not expert judgment.',
        'Reasoning = citation/rationale proxy (automated).',
        'Source-support = human reviewer score 0–2 (0=unsupported, 1=partial, 2=fully supported); n/a until --scored-csv supplied.',
        'Latency is real wall-clock time per request; p95 captures tail latency.',
        'With one repeat, consistency is n/a; use ≥3 repeats for a consistency comparison.',
        'Raw LLM answers preserved in raw_answers/ for trace inspection.',
        'No trading performance inference from these scores.',
    ]

    (output / 'RESULTS.md').write_text('\n'.join(lines) + '\n')

    # Only replace a bounded section in the report doc, never inject illustrative metrics.
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
    p.add_argument('--url', default='http://localhost:8000/research',
                   help='POST endpoint (default: FastAPI /research, not the raw n8n webhook)')
    p.add_argument('--models', nargs='+', default=['qwen2.5:7b', 'qwen2.5:3b'],
                   help='Ollama model tags to compare; include both 7B and 3B for routing analysis')
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--output', type=Path, default=ROOT / 'results')
    p.add_argument('--report', type=Path, default=ROOT / 'docs' / 'REPORT.md')
    p.add_argument('--scored-csv', type=str, default=None,
                   help='Path to a reviewer-annotated CSV with source_support column (0-2 per row)')
    args = p.parse_args()
    run(args.url, args.models, args.repeats, args.output, args.report, args.scored_csv)
