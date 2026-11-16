import copy
import json
from itertools import permutations
import statistics
import time
import tracemalloc
from pathlib import Path

from baseline import Lookup
from engine import Engine

ROOT = Path(__file__).resolve().parent

# Published development cases with independently written expected outputs.
CASES = [
    ("V01", ["녹차 두 잔 주세요."], "요청(주다(청자,화자,녹차,두잔))"),
    ("V02", ["국을 먹기 전에 식히자."], "제안(먼저(식히다(우리,국),먹다(우리,국)))"),
    ("V03", ["생선이 있으면 두부는 빼 주세요."], "요청(조건(있다(생선),빼다(청자,두부)))"),
    ("V04", ["저기 약국 앞에서 세워 주세요."], "요청(세우다(청자,차,저기 약국 앞))"),
    ("V05", ["출발하면 문자 보내 줘."], "요청(조건(출발하다(청자),보내다(청자,화자,문자)))"),
    ("V06", ["수진이가 내일 온대."], "알림(전언(수진,오다(수진,내일)))"),
    ("V07", ["유리컵 대신 저걸 주세요."], "요청(대신(주다(청자,화자,머그컵),주다(청자,화자,유리컵)))"),
    ("V08", ["목요일 세 시에 역 앞에서 만나자.", "날짜는 금요일이야."],
     "정정(만나다(우리,금요일,세 시,역 앞))"),
    ("V09", ["목요일 세 시에 역 앞에서 만나자.", "장소는 도서관이야."],
     "정정(만나다(우리,목요일,세 시,도서관))"),
    ("V10", ["지영이는 민수에게 우산을 빌렸어."], "알림(빌려주다(민수,지영,우산))"),
    ("V11", ["우산을 민수한테 지영이가 빌려줬어."], "알림(빌려주다(지영,민수,우산))"),
    ("V12", ["하린이가 도윤이한테 손전등을 빌려줬어."], "알림(빌려주다(하린,도윤,손전등))"),
    ("V13", ["열쇠를 찾은 건 지영이라고 민수는 생각해."], "알림(생각하다(민수,찾다(지영,열쇠)))"),
    ("V14", ["수진이가 문을 잠갔어.", "민수는 그 사실을 알아."], "알림(알다(민수,잠그다(수진,문)))"),
    ("V15", ["수진이는 민수가 자기가 늦는 걸 안다고 생각해."], "확인(누가늦나요)"),
    ("V16", ["민수가 지영이에게 수진이가 도착했다고 말했어."], "알림(전달하다(민수,지영,도착하다(수진)))"),
]


def run(system, conversation):
    for text in conversation:
        output = system.step(text)
    return output


def score(factory, cases):
    return [label for label, conversation, gold in cases if run(factory(), conversation) == gold]


def measure(factory):
    system = factory()
    def batch():
        for _, turns, _ in CASES:
            if isinstance(system, Engine):
                system.last_fact = system.meeting = None
            run(system, turns)
    times = []
    for _ in range(100):
        start = time.perf_counter_ns()
        batch()
        times.append(time.perf_counter_ns() - start)
    tracemalloc.start()
    batch()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"batch_median_us": round(statistics.median(times)/1000, 1),
            "batch_peak_extra_python_bytes": peak}


def main():
    rows = Lookup().rows
    original = [(r["id"], [r["text"]], r["gold"]) for r in rows]
    result = {}
    for name, factory in (("lookup", Lookup), ("engine", Engine)):
        result[name] = {"original_exact_ids": score(factory, original),
                        "development_exact_ids": score(factory, CASES),
                        "execution": measure(factory)}
    result["components_removed"] = {
        component: sorted(set(result["engine"]["development_exact_ids"])
                          - set(score(lambda: Engine(disabled=(component,)), CASES)))
        for component in ("bind", "retain", "update", "embed")
    }
    phrase = "은서가 지후한테 별컵을 빌려줬어."
    engine = Engine()
    new_lexicon = copy.deepcopy(engine.lex)
    new_lexicon["objects"].append("별컵")
    assert engine.step(phrase) is None
    assert Engine(new_lexicon).step(phrase) == "알림(빌려주다(은서,지후,별컵))"
    assert Engine().step("민수는 그 사실을 알아.") == "확인(어느사실)"
    assert Engine().step("날짜는 금요일이야.") == "확인(어느약속)"
    subject_forms = {"하린": "하린이가", "도윤": "도윤이가", "은서": "은서가", "지후": "지후가"}
    recipient_forms = {"하린": "하린이한테", "도윤": "도윤이한테", "은서": "은서한테", "지후": "지후한테"}
    object_forms = {"책": "책을", "손전등": "손전등을", "둘레컵": "둘레컵을"}
    recombinations = []
    for sender, receiver in permutations(("하린", "도윤", "은서", "지후"), 2):
        for obj in ("책", "손전등", "둘레컵"):
            for subject, other, verb in ((sender, receiver, "빌려줬어"), (receiver, sender, "빌렸어")):
                for words in permutations((subject_forms[subject], recipient_forms[other], object_forms[obj])):
                    utterance = " ".join((*words, verb))
                    recombinations.append((utterance, [utterance], f"알림(빌려주다({sender},{receiver},{obj}))"))
    result["generated_role_recombinations"] = {
        "total": len(recombinations),
        "lookup_pass": len(score(Lookup, recombinations)),
        "engine_pass": len(score(Engine, recombinations)),
    }
    sizes = {name: (ROOT/name).stat().st_size for name in
             ("baseline.py", "lookup.json", "engine.py", "lexicon.json")}
    result["file_bytes"] = sizes
    result["word_added_without_engine_change"] = "별컵"
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
