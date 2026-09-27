from pathlib import Path
import json
import streamlit as st
from core import ROOT, load

st.set_page_config(page_title='사료 | 한국사 딥리서처',page_icon='📚',layout='wide')
st.markdown('''<style>
.stApp {background:#f7f5ef;color:#213c36} h1,h2,h3 {color:#213c36}
[data-testid="stSidebar"] {background:#e8ede5}
div.stButton > button[kind="primary"] {background:#214f42;border:none}
</style>''',unsafe_allow_html=True)
st.caption('HISTORY RESEARCH LAB  /  고조선부터 해방까지')
st.title('사료를 나눠 읽고, 역사를 연결하다')
st.write('한국사 딥리서처 · 질문에서 근거가 보이는 장문 보고서까지')
questions=load('data/questions.json')
with st.sidebar:
    st.header('연구 설정')
    st.caption('고조선 · 삼국 · 남북국 · 고려 · 조선 · 근현대')
    mode=st.radio('작업', ['새 연구','저장된 연구 보기','실험 비교'])
    st.info('원문 → 분담 집필 → 부족한 절 재조사 → 보고서')
    st.caption('인용 문서와 직접 근거 구절을 검증합니다. 역사적 해석과 문장별 인용 적합성은 원문과 대조하세요.')

corpus_path=ROOT/'data/corpus.json'
if not corpus_path.exists():
    st.warning('먼저 python collect.py를 실행해 자료를 수집하세요.'); st.stop()
corpus=load('data/corpus.json')
a,b,c=st.columns(3)
a.metric('연구 자료',f"{len(corpus['docs'])}건")
b.metric('전체 원문',f"{sum(map(len,corpus['docs'].values())):,}자")
c.metric('내용별 연구자','4명')
with st.expander('시대별 자료 둘러보기'):
    era=st.selectbox('시대',['고조선·고대','삼국·남북국','고려','조선','근현대','전체'])
    groups={'고조선·고대':['고조선','부여','삼국유사'], '삼국·남북국':['고구려','백제','신라','가야','발해','삼국','남북국'],
            '고려':['고려','무신'], '조선':['조선','세종','훈민정음','임진왜란','병자호란','대동법','경국대전','실학','붕당','흥선'],
            '근현대':['독립','개혁','대한','운동','조약','전투','신간회','의열단','신민회']}
    titles=[t for t in corpus['docs'] if era=='전체' or any(k in t for k in groups.get(era,[]))]
    if titles:
        title=st.selectbox('문서',titles)
        st.caption(f"{len(corpus['docs'][title]):,}자 · 문서 이름으로 분류한 탐색 보조 기능")
        st.link_button('위키백과 원문 열기',corpus['metadata'][title]['url'])
        st.text(corpus['docs'][title][:1500]+'…')
    else: st.info('이 시대 자료는 아직 수집되지 않았습니다.')

def show(result):
    st.subheader('연구 결과')
    st.caption(f"실행 {result['id']} · {result['model']} · {result['elapsed_seconds']:.1f}초")
    final_ids={row['id'] for row in load('output/ablation.json')} if (ROOT/'output/ablation.json').exists() else set()
    if result['id'] not in final_ids: st.info('이전 실험 또는 별도 실행 기록입니다. 최종 비교 실험과 구분해 확인하세요.')
    report_tab,trace_tab,metrics_tab=st.tabs(['보고서','누가 무엇을 읽고 썼나','진단'])
    with report_tab:
        st.markdown(result['report'])
        st.download_button('보고서 내려받기',result['report'],file_name='korean-history-report.md')
    with trace_tab:
        for w in result['workers']:
            with st.expander(w['assignment']['title'],expanded=False):
                st.write(w['assignment'].get('scope','전체 연구'))
                st.caption(f"읽은 분량 {w['used']:,}자 · 집필 {w['round']}회")
                st.markdown(w['draft']['text'])
                for e in w['draft'].get('evidence',[]):
                    st.info(e['title']+' · 직접 확인한 구절: '+e['quote'])
                for r in w['reads']:
                    with st.expander(f"{r['title']} · {r['start']:,}–{r['end']:,}자"):
                        st.text(r['text'])
                        st.link_button('원문 출처',corpus['metadata'][r['title']]['url'])
                st.json(w['history'],expanded=False)
    with metrics_tab:
        st.json(result['metrics'])
        st.warning('지표는 오류와 중복을 찾는 신호입니다. 점수가 높다고 역사적으로 더 정확한 보고서는 아닙니다.')

paths=sorted((ROOT/'output/reports').glob('*/trace.json'),key=lambda p:p.stat().st_mtime,reverse=True)
if mode=='새 연구':
    choice=st.selectbox('질문 예시',[q['question'] for q in questions])
    question=st.text_area('연구 질문',value=choice,height=100)
    st.caption(next(q['why_split'] for q in questions if q['question']==choice))
    if st.button('연구 시작',type='primary',disabled=not question.strip()):
        try:
            from graph import run
            with st.status('자료 배정과 병렬 집필을 진행하고 있습니다.',expanded=True) as status:
                st.write('4개 내용 구역으로 나누고, 부족한 절만 최대 2회까지 집필합니다.')
                st.session_state['result']=run(question)
                status.update(label='연구 완료',state='complete')
        except Exception as exc:
            st.error(f'연구를 완료하지 못했습니다: {type(exc).__name__}. API 키, 사용 한도, 네트워크를 확인하세요.')
    if 'result' in st.session_state: show(st.session_state['result'])
elif mode=='저장된 연구 보기':
    if not paths: st.info('아직 실행된 연구가 없습니다. 새 연구를 시작해 주세요.')
    else:
        p=st.selectbox('실행 기록',paths,format_func=lambda p:p.parent.name)
        show(json.loads(p.read_text(encoding='utf-8')))
else:
    if len(paths)<2: st.info('비교 실험을 실행하면 두 보고서를 나란히 확인할 수 있습니다.')
    else:
        cols=st.columns(2)
        for i,col in enumerate(cols):
            with col:
                p=st.selectbox('비교 대상',paths,index=i,key=f'compare{i}',format_func=lambda p:p.parent.name)
                r=json.loads(p.read_text(encoding='utf-8'))
                st.caption(str(r['switches'])); st.markdown(r['report'])
    if (ROOT/'output/ablation.json').exists(): st.dataframe(load('output/ablation.json'))
