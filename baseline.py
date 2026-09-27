"""같은 모델·자료·읽기 도구. 기본 실험의 실제 읽기량과 예산을 맞춘다."""
import time
import uuid
from core import Model, load, read_chunks, rank, validate_draft, cited_titles, write_draft
from graph import WRITER, store_run
from metrics import measure

BASELINE_WRITER=WRITER.replace('최소 5문단','4개 내용별 절, 각 절마다 최소 5문단')+'''
전체 20~24문단으로 쓰되, 한 문단은 약 150~250자로 간결하게 쓰고 각 문단의 evidence_ids는 핵심 1~3개만 고른다.
자료를 통째로 복사하거나 같은 개요를 반복하지 말고, JSON text 값에는 해당 문단 하나만 쓴다.'''

def run_baseline(question, budget=None, model=None, config=None):
    config=dict(config or load('config.json')); corpus=load('data/corpus.json'); model=model or Model()
    if budget is not None: config['read_budget_chars']=budget
    started=time.time()
    catalog=list(corpus['docs'])
    plan,plan_usage=model.ask('단일 연구자다. 질문 전체를 조사할 시작 문서를 제목 목록에서 1~8개 선택하라. '
        '시대와 쟁점을 골고루 덮고 JSON seeds 배열을 반환하라.',{'question':question,'catalog':catalog},1200,
        schema={'type':'object','additionalProperties':False,'required':['seeds'],'properties':{
            'seeds':{'type':'array','minItems':1,'maxItems':8,'items':{'type':'string','enum':catalog}}}})
    if not plan.get('seeds') or any(t not in corpus['docs'] for t in plan['seeds']): raise ValueError('잘못된 단일 연구자 자료 배정')
    reads,_=read_chunks(corpus,plan['seeds'],config['read_budget_chars'],config['chunk_chars'],question)
    draft,usage=write_draft(model,BASELINE_WRITER,{'question':question,'assignment':'단일 연구자로서 질문 전체를 4개 내용별 절로 논하라. 한국어로 작성한다.',
        'sources':reads},config['output_tokens_per_section']*config['sections'],paragraphs=20)
    usages=[usage]; invalid=[]
    try: validate_draft(draft,reads,require_evidence=True)
    except ValueError as exc:
        invalid.append({'candidate':draft,'error':str(exc)})
        draft,usage=write_draft(model,BASELINE_WRITER,{'question':question,'assignment':'전체 질문을 4개 내용별 절로 집필하는 단일 연구자',
            'sources':reads,'validation_error':str(exc)},config['output_tokens_per_section']*config['sections'],paragraphs=20)
        usages.append(usage)
        validate_draft(draft,reads,require_evidence=True)
    worker={'assignment':{'title':'단일 연구자'},'reads':reads,'used':sum(len(x['text']) for x in reads),
            'draft':draft,'round':1,'history':[{'round':1,'start':started,'end':time.time(),
                'prompt_source_chars':sum(u.get('source_chars_presented',sum(len(x['text']) for x in reads)) for u in usages),'invalid_drafts':invalid}],'usage':usages}
    bibliography='\n\n## 참고 자료\n\n'+'\n'.join(f"- [{t}]({corpus['metadata'][t]['url']}) · 한국어 위키백과 기여자" for t in sorted(set(cited_titles(draft['text']))))
    result={'id':uuid.uuid4().hex[:12],'pipeline_version':'2.0','question':question,'model':model.name,'config':config,
        'plan':plan,'usage':[plan_usage],
        'switches':{'baseline':True},'workers':[worker],'report':'# '+question+'\n\n'+draft['text']+bibliography,
        'elapsed_seconds':time.time()-started,'coordinator_chars':len(str(catalog))}
    result['metrics']=measure(result); store_run(result)
    return result
