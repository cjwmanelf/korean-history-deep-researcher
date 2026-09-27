"""정답표·판정 모델 없는 구조적 경보. 역사적 진실성 점수가 아니다."""
import re
from itertools import combinations
from core import cited_titles

def sentence_units(text):
    """마침표 뒤 인용 표기를 앞 문장에 붙인 후 동일 규칙으로 센다."""
    units=[]
    for part in re.split(r'(?<=[.!?。])\s+|\n+',text):
        part=part.strip()
        leading=re.match(r'^(?:\[\[[^\[\]]+\]\]\s*)+',part)
        if leading and units:
            units[-1]+=' '+leading.group()
            part=part[leading.end():].strip()
        if part and not part.startswith('#'): units.append(part)
    return [s for s in units if len(re.sub(r'\[\[[^\[\]]+\]\]','',s).strip())>=20]

def measure(run):
    workers=run['workers']; read_sets=[{x['title'] for x in w['reads']} for w in workers]
    citations=[(t,read_sets[i]) for i,w in enumerate(workers) for t in cited_titles(w['draft']['text'])]
    sentences=[s for w in workers for s in sentence_units(w['draft']['text'])]
    overlaps=[len(a&b)/max(1,len(a|b)) for a,b in combinations(read_sets,2)]
    usage=run.get('usage',[])+[u for w in workers for u in w.get('usage',[])]
    intervals=[h for w in workers for h in w.get('history',[]) if h['round']==1]
    parallel_overlap=(min(h['end'] for h in intervals)-max(h['start'] for h in intervals)) if len(intervals)>1 else 0
    return {'read_chars':sum(w['used'] for w in workers),
        'worker_source_chars_presented':sum(sum(h.get('prompt_source_chars',0) for h in w['history']) if w.get('history') else w['used'] for w in workers),
        'input_tokens':sum(u.get('input_tokens',0) for u in usage),
        'output_tokens':sum(u.get('output_tokens',0) for u in usage),
        'parallel_overlap_seconds':max(0,parallel_overlap),
        'coordinator_raw_chars':0,'coordinator_catalog_chars':run.get('coordinator_chars',0),
        'unique_documents':len(set().union(*read_sets)),
        'unread_citations':sum(t not in seen for t,seen in citations),
        'citation_sentence_ratio':sum(bool(cited_titles(s)) for s in sentences)/max(1,len(sentences)),
        'mean_document_overlap':sum(overlaps)/max(1,len(overlaps)),
        'budget_utilization':sum(w['used'] for w in workers)/max(1,run['config']['read_budget_chars']),
        'unresolved_sections':sum(w['draft']['needs_more'] for w in workers),
        'revision_attempts':sum(w['round']-1 for w in workers),
        'report_chars':len(run['report'])}
