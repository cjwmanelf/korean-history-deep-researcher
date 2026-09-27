"""한국어 위키백과 API에서 연결된 연구 자료를 수집한다."""
import argparse
import json
import re
import statistics
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import requests

SEEDS = ['강화도 조약', '갑신정변', '동학 농민 운동', '갑오개혁', '독립협회', '대한제국',
         '을사조약', '국채보상운동', '신민회', '3·1 운동', '대한민국 임시정부',
         '의열단', '한국광복군', '광주 학생 항일 운동', '신간회', '물산장려운동',
         '일제강점기', '조선어학회 사건', '봉오동 전투', '청산리 전투', '한일병합조약',
         '고조선', '부여', '고구려', '백제', '신라', '가야', '발해', '삼국 시대', '남북국 시대',
         '후삼국 시대', '고려', '고려 태조', '고려 광종', '고려 성종', '무신정권',
         '몽골의 고려 침입', '고려 공민왕', '조선', '조선 태조', '세종대왕', '훈민정음',
         '임진왜란', '병자호란', '대동법', '조선 영조', '조선 정조', '흥선대원군',
         '삼국사기', '삼국유사', '경국대전', '조선왕조실록', '조선의 신분 제도',
         '붕당', '실학', '조선의 과거 제도', '고려의 대외 관계']
API = 'https://ko.wikipedia.org/w/api.php'
EXCLUDED = {'카카오 (기업)', '다음', '웨이백 머신', '위키백과', '네이버', '구글', '인터넷 아카이브', '국제 표준 도서 번호', '디지털 객체 식별자'}

def api(**params):
    for attempt in range(7):
        try:
            time.sleep(1.5)
            r = requests.get(API, params={'action':'query','format':'json','formatversion':2, **params},
                             headers={'User-Agent':'KoreanHistoryDeepResearch/1.0 (educational corpus)'}, timeout=40)
            r.raise_for_status()
            result = r.json()
            if 'error' in result: raise ValueError(result['error'])
            return result
        except (requests.RequestException, ValueError):
            if attempt == 6: raise
            time.sleep(min(45, 3 * 2 ** attempt))

def fetch(title):
    import hashlib
    cache=Path('tmp/wiki')/(hashlib.sha256(title.encode()).hexdigest()+'.json')
    if cache.exists(): return json.loads(cache.read_text(encoding='utf-8'))
    data = api(titles=title, redirects=1, prop='extracts|info', explaintext=1, inprop='url')
    page = data['query']['pages'][0]
    links, cont = [], {}
    while True:
        result = api(titles=page['title'], prop='links', plnamespace=0, pllimit='max', **cont)
        links.extend(x['title'] for x in result['query']['pages'][0].get('links', []))
        cont = result.get('continue', {})
        if not cont: break
    cache.parent.mkdir(parents=True,exist_ok=True)
    cache.write_text(json.dumps([page,links],ensure_ascii=False),encoding='utf-8')
    return page, links

def collect(target=36):
    docs, edges, metadata, attempted = {}, {}, {}, set()
    existing=Path('data/corpus.json')
    if existing.exists():
        previous=json.loads(existing.read_text(encoding='utf-8'))
        docs,edges,metadata=previous['docs'],previous['links'],previous.get('metadata',{})
        for title in EXCLUDED:
            docs.pop(title,None); edges.pop(title,None); metadata.pop(title,None)
    candidates = list(SEEDS)
    for depth in range(3):
        for title in candidates:
            if title in EXCLUDED or title in attempted or re.search(r'^\d+년$|목록|분류:|틀:', title): continue
            attempted.add(title)
            page, links = fetch(title)
            body = page.get('extract', '')
            if len(body) < 3000: continue
            name = page['title']
            docs[name], edges[name] = body, links
            metadata[name] = {'url': page.get('fullurl', 'https://ko.wikipedia.org/wiki/'+quote(name)),
                              'revision':page.get('lastrevid'), 'collected_at':datetime.now(timezone.utc).isoformat(),
                              'license':'CC BY-SA 4.0; Wikipedia contributors', 'discovery_depth':depth}
            print(f'{len(docs):02d} {name} {len(body):,}', flush=True)
            if len(docs) >= target: break
        if len(docs) >= target: break
        counts = Counter(x for links in edges.values() for x in set(links))
        history_words=('조선','고려','고구려','백제','신라','발해','전쟁','전투','조약','시대','제국','혁명','운동','정변','왕조','왕')
        candidates = sorted((x for x in counts if x not in attempted),
                            key=lambda x:(-int(any(w in x for w in history_words)),-counts[x],x))
    if len(docs) < 30: raise RuntimeError('30개 이상의 본문을 수집하지 못했습니다.')
    edges = {k:[v for v in vals if v in docs and v != k] for k,vals in edges.items()}
    result = {'docs':docs,'links':edges,'metadata':metadata}
    Path('data').mkdir(exist_ok=True)
    Path('data/corpus.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    stats = {'documents':len(docs),'characters':sum(map(len,docs.values())),
             'median_links':statistics.median(map(len,edges.values())),
             'isolated':[k for k,v in edges.items() if not v]}
    Path('data/corpus_stats.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
    print(stats)

if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--target',type=int,default=36)
    collect(p.parse_args().target)
