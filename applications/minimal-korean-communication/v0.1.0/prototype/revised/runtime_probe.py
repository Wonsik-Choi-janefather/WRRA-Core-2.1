import gc
import json
import re
import resource
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from context_lookup import Lookup
from engine import Engine

path=Path(__file__).with_name("target.json")
suite=json.loads(path.read_text())
name,mode=sys.argv[1:]
factory=Engine if name=="rules" else lambda:Lookup(path)

def batch(model):
    for turns,gold in suite:
        if name=="rules":
            model.last_fact=model.meeting=None
        else:
            model.turns.clear()
        for utterance in turns:
            answer=model.step(utterance)
        if answer!=gold:
            raise ValueError((turns,answer,gold))

if mode=="memory":
    gc.collect()
    tracemalloc.start()
    model=factory()
    batch(model)
    gc.collect()
    if name=="rules":
        model.last_fact=model.meeting=None
    if name=="lookup":
        model.turns.clear()
    resident,peak=tracemalloc.get_traced_memory()
    tracemalloc.stop()
    tracemalloc.start()
    batch(model)
    _,extra=tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(json.dumps([resident,peak,extra]))
elif mode=="rss":
    model=factory()
    batch(model)
    print(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
else:
    model=factory()
    for _ in range(20):
        batch(model)
    samples=[]
    for _ in range(200):
        start=time.perf_counter_ns()
        batch(model)
        samples.append((time.perf_counter_ns()-start)/1000)
    q=statistics.quantiles(samples,n=100,method="inclusive")
    print(json.dumps([statistics.median(samples),q[94]]))
