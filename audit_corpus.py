"""모델 최대 창과 운영상 제한을 구별해 실제 토큰 수를 보고한다."""
import json
import tiktoken
from core import ROOT, load, save

def audit():
    corpus=load('data/corpus.json'); config=load('config.json')
    enc=tiktoken.encoding_for_model(config['model'])
    text=json.dumps(corpus['docs'],ensure_ascii=False)
    tokens=len(enc.encode(text))
    stats={'documents':len(corpus['docs']), 'characters':sum(map(len,corpus['docs'].values())),
           'tokens':tokens,'tokenizer':enc.name,'model':config['model'],
           'model_context_window':config['context_window_tokens'],
           'exceeds_model_window':tokens>config['context_window_tokens'],
           'working_context_tokens':config['working_context_tokens'],
           'exceeds_working_context':tokens>config['working_context_tokens'],
           'min_document_characters':min(map(len,corpus['docs'].values())),
           'invalid_links':[(k,v) for k,vs in corpus['links'].items() for v in vs if v not in corpus['docs']]}
    save(ROOT/'data/context_audit.json',stats)
    print(json.dumps(stats,ensure_ascii=False,indent=2))
    return stats

if __name__=='__main__': audit()
