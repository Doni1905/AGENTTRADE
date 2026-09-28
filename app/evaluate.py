"""Run the same frozen 25-question benchmark under 3 retrieval conditions x 2 models."""
import argparse, csv, json, os, re, statistics, time
from pathlib import Path
import httpx

QUESTIONS = json.loads((Path(__file__).resolve().parent.parent/'data'/'questions.json').read_text())

def score(case, answer):
    text=answer.lower()
    present=all(t.lower() in text for t in case['must_contain'])
    forbidden=not any(t.lower() in text for t in case.get('must_not_contain',[]))
    cite=bool(re.search(r'\[(?:doc|source)\s*\d+\]',text))
    return {'accuracy':int(present and forbidden), 'reasoning_quality':int(present and forbidden and ('because' in text or 'policy' in text or 'source' in text) and (cite or case.get('no_citation_ok',False))), 'citation_present':int(cite)}

def run(url, models, repetitions, output):
    output.mkdir(parents=True,exist_ok=True)
    rows=[]
    with httpx.Client(timeout=240) as client:
        for model in models:
            for mode in ('none','fixed','agentic'):
                for case in QUESTIONS:
                    for repeat in range(repetitions):
                        body={'question':case['question'],'ticker':case['ticker'],'model':model,'mode':mode,'evaluation':True}
                        t=time.monotonic()
                        try:
                            r=client.post(url,json=body)
                            r.raise_for_status(); raw=r.json()
                            answer=str(raw.get('answer',raw.get('output',raw)))
                            values=score(case,answer); error=''
                        except Exception as exc:
                            answer=''; values={'accuracy':0,'reasoning_quality':0,'citation_present':0}; error=str(exc)
                        rows.append({'model':model,'mode':mode,'case_id':case['id'],'repeat':repeat+1,'question':case['question'],'answer':answer,'latency_seconds':round(time.monotonic()-t,2),'error':error,**values})
                        print(f"{model} {mode} {case['id']} #{repeat+1}: {values['accuracy']} {error[:60]}",flush=True)
    with (output/'raw.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader();w.writerows(rows)
    summary=[]
    for model in models:
        for mode in ('none','fixed','agentic'):
            block=[r for r in rows if r['model']==model and r['mode']==mode]
            grouped={c['id']:[r['answer'].strip().lower() for r in block if r['case_id']==c['id']] for c in QUESTIONS}
            consistent=sum(len(set(v))==1 for v in grouped.values())/len(grouped)
            summary.append({'model':model,'mode':mode,'n':len(block),'accuracy':round(statistics.mean(r['accuracy'] for r in block),3),'reasoning_quality':round(statistics.mean(r['reasoning_quality'] for r in block),3),'citation_rate':round(statistics.mean(r['citation_present'] for r in block),3),'exact_response_consistency':round(consistent,3),'errors':sum(bool(r['error']) for r in block)})
    (output/'summary.json').write_text(json.dumps(summary,indent=2))
    lines=['# Evaluation results','',f'Run with {len(QUESTIONS)} frozen dated questions, {repetitions} repeats per model/mode.','', '| Model | RAG mode | Accuracy | Reasoning quality | Citation rate | Exact consistency | Errors |','|---|---|---:|---:|---:|---:|---:|']
    for s in summary: lines.append(f"| {s['model']} | {s['mode']} | {s['accuracy']:.3f} | {s['reasoning_quality']:.3f} | {s['citation_rate']:.3f} | {s['exact_response_consistency']:.3f} | {s['errors']} |")
    lines+=['','Accuracy is strict presence/absence of labeled terms, not expert judgment. Reasoning proxy requires evidence and citation; citation quality needs manual audit. Exact response consistency is stringent wording agreement over repeats. Inspect raw.csv for failures, hallucinations, and confounders. No trading performance inference.']
    (output/'RESULTS.md').write_text('\n'.join(lines)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url',default='http://localhost:5678/webhook/agenttrade-analyze');p.add_argument('--models',nargs=2,default=['qwen2.5:3b','llama3.2:3b']);p.add_argument('--repeats',type=int,default=3);p.add_argument('--output',type=Path,default=Path('results'))
    a=p.parse_args();run(a.url,a.models,a.repeats,a.output)
