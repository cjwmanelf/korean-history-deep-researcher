"""정의 변경 시 모든 실행에 동일한 지표 함수를 적용한다."""
import json
from core import ROOT, save
from metrics import measure

def refresh():
    runs={}
    for path in sorted((ROOT/'output/reports').glob('*/trace.json')):
        run=json.loads(path.read_text(encoding='utf-8'))
        run['metrics']=measure(run); save(path,run); runs[run['id']]=run
    records=[{k:r[k] for k in ['id','model','question','elapsed_seconds','metrics']} for r in runs.values()]
    (ROOT/'output/runs.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    path=ROOT/'output/ablation.json'
    if path.exists():
        results=json.loads(path.read_text(encoding='utf-8'))
        for row in results: row['metrics']=runs[row['id']]['metrics']
        save(path,results)
    print('Refreshed',len(runs),'runs using the same metric definitions.')

if __name__=='__main__': refresh()
