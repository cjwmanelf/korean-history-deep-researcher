import pytest
from core import read_chunks, validate_draft, write_draft
from graph import build, validate_plan

CORPUS={'docs':{'A':'a'*100,'B':'b'*100,'C':'c'*100},'links':{'A':['B'],'B':['C'],'C':[]},
        'metadata':{x:{'url':'https://example.org/'+x} for x in 'ABC'}}
CONFIG={'sections':2,'roles':['one','two'],'read_budget_chars':120,'chunk_chars':20,
        'max_rounds':2,'output_tokens_per_section':500}

def test_budget_and_link_switch():
    on,_=read_chunks(CORPUS,['A'],60,20,'',True)
    off,_=read_chunks(CORPUS,['A'],60,20,'',False)
    assert sum(len(x['text']) for x in on)==60
    assert {x['title'] for x in on}=={'A','B','C'}
    assert {x['title'] for x in off}=={'A'}

def test_reserved_sources_are_not_read():
    reads,_=read_chunks(CORPUS,['A'],60,20,'',True,blocked_titles={'B'})
    assert {x['title'] for x in reads}=={'A'}
    assert sum(len(x['text']) for x in reads)==60

def test_writer_receives_only_its_assigned_question():
    class InspectQuestion(FakeModel):
        def ask(self,instruction,data,max_tokens,**kwargs):
            if 'sources' in data:
                assert 'GLOBAL_QUESTION' not in data['question']
                assert data['assignment']['scope'] in data['question']
            return super().ask(instruction,data,max_tokens,**kwargs)
    build(CORPUS,CONFIG,InspectQuestion()).invoke({'question':'GLOBAL_QUESTION'})

def test_unread_citation_rejected():
    with pytest.raises(ValueError): validate_draft({'text':'claim [[B]]','needs_more':False},[{'title':'A'}])

def test_evidence_must_be_literal_text_that_was_read():
    reads=[{'title':'A','text':'a'*50}]
    valid={'text':'claim [[A]]','needs_more':False,'evidence':[{'title':'A','quote':'a'*15}]}
    validate_draft(valid,reads,require_evidence=True)
    invalid={**valid,'evidence':[{'title':'A','quote':'b'*15}]}
    with pytest.raises(ValueError): validate_draft(invalid,reads,require_evidence=True)

def test_every_cited_document_requires_an_evidence_quote():
    reads=[{'title':'A','text':'a'*50},{'title':'B','text':'b'*50}]
    draft={'text':'claim [[A]] [[B]]','needs_more':False,'evidence':[{'title':'A','quote':'a'*15}]}
    with pytest.raises(ValueError): validate_draft(draft,reads,require_evidence=True)

def test_structured_evidence_ids_create_real_citations():
    class StructuredModel:
        def ask(self,instruction,data,max_tokens,**kwargs):
            assert kwargs['schema']['properties']['paragraphs']['items']['properties']['evidence_ids']['items']['enum']==['E1']
            return {'paragraphs':[{'text':'자료에 근거한 문장이다.','evidence_ids':['E1']}],
                    'needs_more':False,'reason':'','next_titles':[]},{}
    reads=[{'title':'실제 문서','text':'이것은 읽은 자료에서 직접 발췌한 충분히 긴 원문입니다.'}]
    draft,_=write_draft(StructuredModel(),'test',{'sources':reads},200,paragraphs=1)
    assert draft['text'].endswith('[[실제 문서]]')
    validate_draft(draft,reads,require_evidence=True)

def test_invalid_assignment():
    with pytest.raises(ValueError): validate_plan([{'title':'x','scope':'y','seeds':['Z']}]*2,CORPUS,CONFIG)

class FakeModel:
    name='test-double'
    def ask(self,instruction,data,max_tokens,**kwargs):
        if 'catalog' in data:
            return {'sections':[{'title':x,'scope':x,'seeds':[x]} for x in ['A','C']]},{}
        assert all(x['title'] in CORPUS['docs'] for x in data['sources'])
        title=data['assignment']['title']
        return {'text':'검증용 문장입니다. [['+title+']]','needs_more':title=='A',
                'reason':'추가 근거','next_titles':['B'],
                'evidence':[{'title':title,'quote':next(x['text'][:15] for x in data['sources'] if x['title']==title)}]},{}

def test_only_insufficient_section_retries_and_no_raw_upstairs():
    result=build(CORPUS,CONFIG,FakeModel()).invoke({'question':'test'})
    assert [w['round'] for w in result['workers']]==[2,1]
    assert all(w['used']<=60 for w in result['workers'])
    assert len(result['workers'][0]['history'])==2
    assert '[[A]]' in result['report']

def test_revision_off_changes_execution():
    result=build(CORPUS,CONFIG,FakeModel(),{'revision':False}).invoke({'question':'test'})
    assert all(w['round']==1 for w in result['workers'])

def test_read_offsets_do_not_reread():
    first,offsets=read_chunks(CORPUS,['A'],30,20,'',False)
    second,_=read_chunks(CORPUS,['A'],30,20,'',False,offsets)
    assert sum(len(x['text']) for x in first+second)==60
    assert min(x['start'] for x in second)==30

def test_failed_revision_preserves_original():
    class BadRevision(FakeModel):
        def ask(self,instruction,data,max_tokens,**kwargs):
            if data.get('previous_draft'):
                return {'text':'없는 자료 [[Z]]','needs_more':False},{}
            return super().ask(instruction,data,max_tokens)
    result=build(CORPUS,CONFIG,BadRevision()).invoke({'question':'test'})
    assert '[[A]]' in result['workers'][0]['draft']['text']
    assert result['workers'][0]['history'][-1]['rejected']

def test_territory_switch_changes_prompt():
    class InspectModel(FakeModel):
        def __init__(self): self.others=[]
        def ask(self,instruction,data,max_tokens,**kwargs):
            if 'other_territories' in data: self.others.append(data['other_territories'])
            return super().ask(instruction,data,max_tokens)
    model=InspectModel()
    build(CORPUS,CONFIG,model,{'territory':False}).invoke({'question':'test'})
    assert model.others and all(x==[] for x in model.others)

def test_workers_are_actually_parallel():
    import threading
    barrier=threading.Barrier(2,timeout=3)
    class ParallelModel(FakeModel):
        def ask(self,instruction,data,max_tokens,**kwargs):
            if 'sources' in data and not data.get('previous_draft'): barrier.wait()
            return super().ask(instruction,data,max_tokens)
    result=build(CORPUS,CONFIG,ParallelModel()).invoke({'question':'test'})
    assert len(result['workers'])==2
