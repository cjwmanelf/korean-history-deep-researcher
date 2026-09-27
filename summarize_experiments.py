"""실제 기록만으로 조건별 평균·범위를 저장한다. 승자 순위는 만들지 않는다."""
from collections import defaultdict
from statistics import mean
from core import ROOT, load

def summarize(source='output/ablation.json',destination='output/experiment-summary.md'):
    rows=load(source); groups=defaultdict(list)
    for row in rows: groups[row['variant']].append(row['metrics'])
    keys=['read_chars','worker_source_chars_presented','unique_documents','unread_citations',
          'citation_sentence_ratio','mean_document_overlap','revision_attempts','report_chars','input_tokens','output_tokens']
    out=['# 조건별 실제 측정값','', '각 셀은 평균 [최솟값, 최댓값]입니다. 순위표가 아닙니다.','',
         '| 조건 | 반복 수 | '+' | '.join(keys)+' |', '|---|---|'+'---|'*len(keys)]
    for name,metrics in groups.items():
        cells=[]
        for key in keys:
            values=[m[key] for m in metrics]
            cells.append(f'{mean(values):.3f} [{min(values):.3f}, {max(values):.3f}]')
        out.append('| '+name+' | '+str(len(metrics))+' | '+' | '.join(cells)+' |')
    (ROOT/destination).write_text('\n'.join(out)+'\n',encoding='utf-8')

if __name__=='__main__': summarize()
