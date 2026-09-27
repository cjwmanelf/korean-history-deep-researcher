"""LangGraph: 기획 -> 병렬 집필 -> 점검 -> 선택 재파견 -> 종합."""
import argparse
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from core import ROOT, Model, load, save, read_chunks, validate_draft, cited_titles, write_draft

class State(TypedDict, total=False):
    question: str
    plan: list
    workers: list
    pending: list
    report: str
    coordinator_chars: int
    usage: list

WRITER = '''한국사 연구자다. 맡은 범위만 집필하고 다른 구역은 피하라. 제공된 자료만 근거로
구체적 사건, 원인, 차이, 한계를 설명하는 한국어 장문 원고(최소 5문단)를 작성한다.
assignment와 other_territories는 조사할 질문과 업무 경계이며 사실 근거가 아니다.
사실은 sources에서 확인한 것만 쓴다. 연대 순서와 조약 당사자를 확인하고, 단선적 발전·필연론을 피한다.
통설·전승·사료에 기록된 주장·해석을 구별한다. 특히 고조선의 건국 전승을 확정된 역사 연대와 혼동하지 않는다.
제공된 부분 원문으로 확인할 수 없는 사건은 빈칸을 상식으로 채우지 말고 부족함을 명시한다.
자료의 부족과 해석상 한계를 구분한다. 각 문단에 그 문단을 직접 뒷받침하는 evidence_options의 ID를 선택한다.
역할명이나 읽지 않은 연결 문서를 근거로 쓰지 마라. text에는 인용 표기나 E1 같은 내부 ID를 직접 쓰지 마라.
JSON Schema에 맞게 paragraphs에 문단 text와 evidence_ids를 넣고 needs_more, reason, next_titles를 반환한다.
새 원고는 완성된 전체 절이다. 원문 근거 구절이 있다는 것이 모든 해석을 보증하지는 않는다.'''

def validate_plan(plan, corpus, config):
    if not isinstance(plan,list) or len(plan)!=config['sections']: raise ValueError('잘못된 절 수')
    for i,p in enumerate(plan):
        if not isinstance(p.get('title'),str) or not isinstance(p.get('scope'),str): raise ValueError('역할 누락')
        seeds=p.get('seeds',[])
        if not seeds or any(t not in corpus['docs'] for t in seeds): raise ValueError('존재하지 않는 시작 자료')
        p['id']=i; p['budget']=config['read_budget_chars']//len(plan)
    return plan

def build(corpus, config, model, switches=None, fixed_plan=None):
    switches={'territory':True,'links':True,'revision':True,**(switches or {})}
    def plan(s):
        if fixed_plan is not None:
            import copy
            return {'plan':validate_plan(copy.deepcopy(fixed_plan),corpus,config), 'workers':[],
                    'coordinator_chars':len(json.dumps(fixed_plan,ensure_ascii=False)), 'usage':[]}
        catalog=list(corpus['docs'])
        payload={'question':s['question'],'catalog':catalog,'roles':config['roles'],'sections':config['sections']}
        schema={'type':'object','additionalProperties':False,'required':['sections'],'properties':{
            'sections':{'type':'array','minItems':config['sections'],'maxItems':config['sections'],
            'items':{'type':'object','additionalProperties':False,'required':['title','scope','seeds'],
            'properties':{'title':{'type':'string'},'scope':{'type':'string'},
                          'seeds':{'type':'array','minItems':1,'maxItems':2,'items':{'type':'string','enum':catalog}}}}}}}
        result,usage=model.ask('코디네이터다. JSON {"sections":[{"title":"내용별 절 제목",'
            '"scope":"역할과 경계", "seeds":["목록에 있는 정확한 제목 1~2개"]}]}를 작성하라. '
            '형식(서론/결론)으로 나누지 말고 질문에 맞는 서로 다른 내용으로 나눈다. 역할 명단은 참고이며 '
            '질문에 없는 시대를 억지로 포함하지 마라. scope는 조사할 쟁점과 제외 범위를 명령형으로 적어라. '
            '역사적 사실이나 결론을 미리 서술하지 마라. 범위가 여러 시대에 걸치면 시작과 끝 시기를 대표하는 '
            '서로 다른 자료를 seed로 선택하여 범위 전체를 덮어라. 원문은 볼 수 없다.',payload,1600,schema=schema)
        return {'plan':validate_plan(result['sections'],corpus,config), 'workers':[],
                'coordinator_chars':len(json.dumps(payload,ensure_ascii=False)), 'usage':[usage]}

    def work(p, question, previous=None, others=None):
        start=time.time()
        previous=previous or {'reads':[],'offsets':{},'history':[], 'round':0, 'used':0, 'usage':[]}
        remaining=p['budget']-previous['used']
        budget=remaining if previous['round'] else max(1,p['budget']//config['max_rounds'])
        seeds=p['seeds']
        blocked={t for other in (others or []) for t in other.get('seeds',[]) if t not in p['seeds']} if switches['territory'] else set()
        if previous.get('draft'):
            requested=previous['draft'].get('next_titles',[])
            reachable={x['title'] for x in previous['reads']}
            if switches['links']:
                reachable.update(t for x in previous['reads'] for t in corpus['links'].get(x['title'],[]))
            seeds=[x for x in requested if x in reachable] or seeds
        new,offsets=read_chunks(corpus,seeds,budget,config['chunk_chars'],question+' '+p['title']+' '+p['scope'],
                               switches['links'],previous['offsets'],blocked_titles=blocked)
        reads=previous['reads']+new
        payload={'question':p['title']+' / '+p['scope'],'assignment':p,
            'other_territories':others if switches['territory'] else [],
            'sources':reads,'previous_draft':previous.get('draft',{}),
            'allowed_citations':sorted({x['title'] for x in reads}),
            'available_links':{x['title']:corpus['links'].get(x['title'],[]) if switches['links'] else [] for x in reads}}
        draft,usage=write_draft(model,WRITER,payload,config['output_tokens_per_section'])
        usages=[usage]; invalid_drafts=[]
        if not previous.get('draft'):
            try: validate_draft(draft,reads,require_evidence=True)
            except ValueError as exc:
                invalid_drafts.append({'candidate':draft,'error':str(exc)})
                draft,usage=write_draft(model,WRITER,{**payload,'validation_error':str(exc),
                    'correction':'허용된 문서만 근거로 원고를 새로 작성하라. 역할명과 미열람 문서는 인용하지 마라.'},config['output_tokens_per_section'])
                usages.append(usage)
        rejected=None
        try:
            validate_draft(draft,reads,require_evidence=True)
            # 새 초안이 기존에 인용한 자료를 잃으면 기존 원고를 보존한다.
            if previous.get('draft') and not set(cited_titles(previous['draft']['text'])) <= set(cited_titles(draft['text'])):
                rejected='기존 인용 손실'; draft_kept=previous['draft']
            else: draft_kept=draft
        except ValueError as exc:
            if not previous.get('draft'): raise
            rejected=str(exc); draft_kept=previous['draft']
        history=previous['history']+[{'round':previous['round']+1,'candidate':draft,'rejected':rejected,
                                     'start':start,'end':time.time(),'new_chars':sum(len(x['text']) for x in new),
                                     'prompt_source_chars':sum(u.get('source_chars_presented',sum(len(x['text']) for x in reads)) for u in usages),
                                     'invalid_drafts':invalid_drafts}]
        return {'assignment':p,'draft':draft_kept,'reads':reads,'offsets':offsets,'history':history,
                'round':previous['round']+1,'used':previous['used']+sum(len(x['text']) for x in new),
                'usage':previous['usage']+usages}

    def dispatch(s):
        others=[{'title':p['title'],'scope':p['scope'],'seeds':p['seeds']} for p in s['plan']]
        with ThreadPoolExecutor(max_workers=config['sections']) as pool:
            jobs=[pool.submit(work,p,s['question'],None,[o for j,o in enumerate(others) if j!=i]) for i,p in enumerate(s['plan'])]
            workers=[f.result() for f in jobs]
        return {'workers':workers}

    def inspect(s):
        return {'pending':[i for i,w in enumerate(s['workers']) if switches['revision'] and
                           w['draft']['needs_more'] and w['round']<config['max_rounds'] and w['used']<w['assignment']['budget']]}

    def revise(s):
        workers=list(s['workers'])
        with ThreadPoolExecutor(max_workers=config['sections']) as pool:
            futures={i:pool.submit(work,workers[i]['assignment'],s['question'],workers[i],
                [{'title':p['title'],'scope':p['scope'],'seeds':p['seeds']} for j,p in enumerate(s['plan']) if i!=j]) for i in s['pending']}
            for i,f in futures.items(): workers[i]=f.result()
        return {'workers':workers}

    def synthesize(s):
        # 원문을 코디네이터에 올리지 않는다. 검증된 원고만 순서대로 연결한다.
        report='# '+s['question']+'\n\n'
        for w in s['workers']:
            report+='## '+w['assignment']['title']+'\n\n'+w['draft']['text']+'\n\n'
            if w['draft']['needs_more']: report+='> 추가 확인 필요: '+w['draft'].get('reason','')+'\n\n'
        report+='## 참고 자료\n\n'
        for title in sorted(set(cited_titles(report))):
            report+=f"- [{title}]({corpus['metadata'][title]['url']}) · 한국어 위키백과 기여자\n"
        return {'report':report}

    g=StateGraph(State)
    for name,fn in [('plan',plan),('dispatch',dispatch),('inspect',inspect),('revise',revise),('synthesize',synthesize)]: g.add_node(name,fn)
    g.add_edge(START,'plan'); g.add_edge('plan','dispatch'); g.add_edge('dispatch','inspect')
    g.add_conditional_edges('inspect',lambda s:'revise' if s['pending'] else 'synthesize')
    g.add_edge('revise','inspect'); g.add_edge('synthesize',END)
    return g.compile()

def run(question, switches=None, model=None, config=None, persist=True, fixed_plan=None):
    from metrics import measure
    config=config or load('config.json'); corpus=load('data/corpus.json'); model=model or Model()
    if not question.strip() or len(question)>3000: raise ValueError('질문은 1~3000자로 입력해주세요.')
    if config['max_rounds']<1 or config['read_budget_chars']<config['sections']: raise ValueError('잘못된 예산 설정')
    started=time.time()
    state=build(corpus,config,model,switches,fixed_plan).invoke({'question':question})
    result={'id':uuid.uuid4().hex[:12],'pipeline_version':'2.0','model':model.name,'switches':switches or {},'config':config,
            'elapsed_seconds':time.time()-started,**state}
    result['metrics']=measure(result)
    if persist: store_run(result)
    return result

def store_run(result):
    folder=ROOT/'output'/'reports'/result['id']; folder.mkdir(parents=True,exist_ok=True)
    save(folder/'trace.json',result)
    (folder/'report.md').write_text(result['report'],encoding='utf-8')
    with (ROOT/'output'/'runs.jsonl').open('a',encoding='utf-8') as f:
        f.write(json.dumps({k:result[k] for k in ['id','model','question','elapsed_seconds','metrics']},ensure_ascii=False)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--question',default='고조선부터 해방까지 한국의 국가 운영과 대외 관계는 어떻게 변화했는가?')
    print(run(p.parse_args().question)['id'])
