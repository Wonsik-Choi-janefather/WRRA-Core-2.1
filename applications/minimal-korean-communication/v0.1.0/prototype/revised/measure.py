import gzip
import importlib.util
import json
import statistics
import time
from itertools import permutations, product
from pathlib import Path

from context_lookup import Lookup
from engine import Engine

root = Path(__file__).resolve().parent
prior = root.parent / "v0_1"
spec = importlib.util.spec_from_file_location("old_engine", prior / "engine.py")
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)

def run(model, turns):
    for turn in turns:
        value = model.step(turn)
    return value

persons = {"하린": ("하린이가", "하린이에게"), "도윤": ("도윤이가", "도윤이에게"), "은서": ("은서가", "은서에게")}
cases = {"말투": [], "목적격 조사 생략": [], "말투와 조사 생략": [], "앞 대화 변경": []}
forms = [("책", "빌려주었어", True), ("손전등", "빌려줬어요", True),
         ("둘레컵", "빌려주었습니다", True), ("우산", "빌렸어요", False)]
for giver, taker in permutations(persons, 2):
    for obj, verb, forward in forms:
        subject, other = (giver, taker) if forward else (taker, giver)
        first, second = persons[subject][0], persons[other][1]
        gold = f"알림(빌려주다({giver},{taker},{obj}))"
        cases["말투"].append(([f"{first} {second} {obj}을 {verb}."], gold))
        cases["목적격 조사 생략"].append(([f"{first} {second} {obj} {'빌려줬어' if forward else '빌렸어'}."], gold))
        cases["말투와 조사 생략"].append(([f"{first} {second} {obj} {verb}."], gold))

for day, clock, place in product(("월요일", "화요일", "목요일"), ("두 시", "네 시"), ("공원 앞", "도서관 앞")):
    start = f"{day} {clock}에 {place}에서 만나자."
    cases["앞 대화 변경"].extend([
        ([start, "날짜는 금요일이야."], f"정정(만나다(우리,금요일,{clock},{place}))"),
        ([start, "장소는 학교야."], f"정정(만나다(우리,{day},{clock},학교))"),
    ])

suite = [row for group in cases.values() for row in group]
corpus = json.loads((prior / "lookup.json").read_text())
known = [([r["text"]], r["gold"]) for r in corpus]
assert len({tuple(t) for t,g in suite}) == len(suite)==96
assert not ({tuple(t) for t,g in known}&{tuple(t) for t,g in suite})
def dump(name, rows):
    path = root/name
    path.write_text(json.dumps(rows, ensure_ascii=False, separators=(",",":")))
    return path
original = dump("original.json", known)
complete = dump("target.json", suite)
sizes = lambda paths: (sum(p.stat().st_size for p in paths),
                      len(gzip.compress(b"".join(p.read_bytes() for p in paths), mtime=0)))
factories = {"기존 규칙":old.Engine, "보완 규칙":Engine,
             "원문만 조회":lambda:Lookup(original),"시험 전체 사전 저장":lambda:Lookup(complete)}
for name,f in factories.items():
    hits = {key:sum(run(f(),t)==g for t,g in group) for key,group in cases.items()}
    print(name,hits,sum(hits.values()))
print("규칙 저장 크기",sizes([root/"engine.py",root/"lexicon.json"]))
print("평가표 저장 크기",sizes([root/"context_lookup.py",complete]))
print("원문 조회 크기",sizes([root/"context_lookup.py",original]))
assert all(run(Engine(),[r["text"]])==run(old.Engine(),[r["text"]]) for r in corpus)
for text in ("하린이가 도윤이에게 빌려주었어.","하린이가 도윤이에게 모르는물건 빌려줬어요.",
             "하린 도윤 책 빌려줘.","날짜는 금요일이야."):
    print("불충분 입력",text,Engine().step(text))
for label,f in (("보완 규칙",Engine),("시험 전체 사전 저장",lambda:Lookup(complete))):
    samples=[]
    for _ in range(25):
        start=time.perf_counter_ns()
        for turns,gold in suite:
            m=f()
            assert run(m,turns)==gold
        samples.append((time.perf_counter_ns()-start)/1e6)
    print("초기화 포함 96건 ms",label,round(statistics.median(samples),2))
