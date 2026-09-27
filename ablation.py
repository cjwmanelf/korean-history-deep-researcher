import argparse
from core import ROOT, load, save
from graph import run
from baseline import run_baseline

def experiment(question, repeats=3):
    results=[]
    for repeat in range(repeats):
        full=run(question)
        results.append({'repeat':repeat,'variant':'full','id':full['id'],'metrics':full['metrics']})
        print(f"repeat {repeat+1}: full {full['id']}",flush=True)
        save(ROOT/'output/ablation.json',results)
        for switch in ['territory','links','revision']:
            result=run(question,{switch:False},fixed_plan=full['plan'])
            results.append({'repeat':repeat,'variant':'no_'+switch,'id':result['id'],'metrics':result['metrics']})
            print(f"repeat {repeat+1}: no_{switch} {result['id']}",flush=True)
            save(ROOT/'output/ablation.json',results)
        result=run_baseline(question,budget=full['metrics']['read_chars'])
        results.append({'repeat':repeat,'variant':'baseline','id':result['id'],'metrics':result['metrics']})
        print(f"repeat {repeat+1}: baseline {result['id']}",flush=True)
        save(ROOT/'output/ablation.json',results)
    return results

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--repeats',type=int,default=3); p.add_argument('--question-id',default='q9')
    args=p.parse_args(); q=next(q for q in load('data/questions.json') if q['id']==args.question_id)
    experiment(q['question'],args.repeats)
