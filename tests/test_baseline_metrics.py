import baseline
from metrics import measure
from metrics import sentence_units

def test_citation_after_period_stays_with_sentence():
    text='역사적 사건의 원인과 경과를 충분히 설명하는 문장이다. [[자료]]\n\n다음 사건의 경과도 충분히 길게 서술한 문장이다. [[다른 자료]]'
    units=sentence_units(text)
    assert len(units)==2
    assert units[0].endswith('[[자료]]')
    assert units[1].endswith('[[다른 자료]]')

def test_baseline_consumes_matching_read_budget(monkeypatch):
    corpus={'docs':{'A':'x'*200,'B':'y'*200},'links':{'A':['B'],'B':['A']},
            'metadata':{'A':{'url':'https://example.org/a'},'B':{'url':'https://example.org/b'}}}
    config={'read_budget_chars':300,'chunk_chars':20,'sections':2,'output_tokens_per_section':100}
    monkeypatch.setattr(baseline,'load',lambda _:corpus)
    monkeypatch.setattr(baseline,'store_run',lambda _:None)
    class Model:
        name='test-double'
        def ask(self,*args,**kwargs):
            if 'catalog' in args[1]: return {'seeds':['A','B']},{}
            return {'text':'검증용 문장입니다. [[A]]','needs_more':False,'evidence':[{'title':'A','quote':'x'*15}]},{}
    result=baseline.run_baseline('question',budget=120,model=Model(),config=config)
    assert result['metrics']['read_chars']==120
    assert result['metrics']['budget_utilization']==1
    assert result['metrics']['unread_citations']==0
