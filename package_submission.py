"""명시한 프로젝트 파일만 ZIP에 넣어 키·가상환경·PDF 원본을 제외한다."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parent

def package():
    destination=ROOT/'dist/korean-history-deep-researcher.zip'
    destination.parent.mkdir(exist_ok=True)
    files=[p for p in ROOT.iterdir() if p.is_file() and (p.suffix in {'.py','.md','.json','.txt'} or p.name in {'.env.example','.gitignore','LICENSE'})]
    for folder in ['data','output','tests','.github']:
        files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
    with ZipFile(destination,'w',compression=ZIP_DEFLATED,compresslevel=9) as archive:
        for path in sorted(set(files)):
            if path.name=='.env' or '.venv' in path.parts: raise RuntimeError('비밀 파일 차단')
            archive.write(path,'korean-history-deep-researcher/'+path.relative_to(ROOT).as_posix())
    if destination.stat().st_size>5_000_000: raise RuntimeError('과제 업로드 제한 5MB를 넘었습니다.')
    print(destination.name,destination.stat().st_size,'bytes')

if __name__=='__main__': package()
