"""Compare deadline-aware decoding using real, sequential ASR timings."""
import argparse
from array import array
from math import ceil, exp, sin
from pathlib import Path
import json
import random
from statistics import median
from time import perf_counter_ns

from engine.audio import FRAME_BYTES, WhisperKorean
from engine.capture_grace import CaptureGrace, Job
from engine.recovery import RecoveringCafeStream
from replay_capture import capture_time, evidence, order, pcm

MODELS = ("small", "tiny")
RELEASE_MS = 4800
READY_MS = 5250
DEADLINE_MS = 9000
SMALL_BUDGET_MS = 3868  # Prior warm p95, rounded up. A scheduling estimate.
ASSENT = {"네", "예"}


def decode(model, clip):
    signal = bytes(FRAME_BYTES * 5) + clip + bytes(FRAME_BYTES * 25)
    start = perf_counter_ns()
    first, second = model(signal, final=True), model.without_prompt(signal)
    return {"text": first, "reference": second,
            "yes": all(value.strip().rstrip(".!") in ASSENT for value in (first, second)),
            "ms": ceil((perf_counter_ns() - start) / 1e6)}


def route(policy, timings, ready):
    if policy == "small":
        hit = timings["small"]
        return hit, hit["ms"], "Small"
    hit = timings["tiny"]
    if hit["yes"] or policy == "tiny":
        return hit, hit["ms"], "Tiny"
    if ready + hit["ms"] + SMALL_BUDGET_MS >= DEADLINE_MS:
        return hit, hit["ms"], "Tiny; fallback skipped"
    fallback = timings["small"]
    return fallback, hit["ms"] + fallback["ms"], "Tiny → Small"


def registered(hit, elapsed, capture, ready, opened=True):
    cafe = CaptureGrace(5000, 4000)
    question = order(cafe, "A", "녹차")
    job = Job("A", question, "uA")
    if not opened or capture is None or not cafe.capture(job, *capture)[0]:
        return False
    if hit["yes"]:
        cafe.complete(job, evidence(job, hit["text"]), ready + elapsed)
    else:
        cafe.advance(ready + elapsed)
    return bool(cafe.dialogues.orders())


def quantiles(values):
    return {"median_ms": median(values), "p95_ms": sorted(values)[ceil(.95 * len(values)) - 1]}


def main(args):
    affirm = pcm(args.assent, 4.05, 4.5)
    rng = random.Random(82)
    impact = array("h", (int(9500 * exp(-i / 500) * sin(i * .85)) for i in range(2240))).tobytes()
    noise = array("h", (rng.randint(-2800, 2800) for _ in range(2880))).tobytes()
    alternatives = {
        "explicit_no": pcm(args.correction, 3.30, 3.95),
        "cancel": pcm(args.correction, 5.48, 7.89),
        "real_transient": pcm(args.correction, 0, .2),
        "synthetic_impact": impact,
        "sustained_noise": noise,
    }
    releases = {name: (3800 if name == "cancel" else RELEASE_MS) for name in alternatives}
    captures = {name: capture_time(clip, releases[name]) for name, clip in alternatives.items()}
    confirm_capture = capture_time(affirm, RELEASE_MS)
    assert confirm_capture == (4960, 5100)
    normal = {}
    negative = {}
    for label in MODELS:
        model = WhisperKorean(getattr(args, label), RecoveringCafeStream().recognition_prompt())
        decode(model, affirm)
        normal[label] = [decode(model, affirm) for _ in range(args.runs)]
        negative[label] = {name: decode(model, value) for name, value in alternatives.items()}
        del model

    aggregates = {}
    for policy in ("small", "tiny", "cascade"):
        approved, attempts, times = 0, [], []
        for i in range(args.runs):
            recognized, elapsed, path = route(policy, {m: normal[m][i] for m in MODELS}, READY_MS)
            times.append(elapsed)
            approved += registered(recognized, elapsed, confirm_capture, READY_MS)
            attempts.append(path)
        false = []
        for name, value in alternatives.items():
            ready = releases[name] + len(value) // 32
            recognized, elapsed, _ = route(policy, {m: negative[m][name] for m in MODELS}, ready)
            if registered(recognized, elapsed, captures[name], ready):
                false.append(name)
        aggregates[policy] = {"approved_by_deadline": approved, "attempts": args.runs,
                              "false_approvals": false, "inference": quantiles(times),
                              "paths": attempts}

    # Isolate head-of-line cost on one modeled worker. Use measured costs for
    # A's ambiguous synthetic input and B's actual assent.
    a_ready = 5150
    a = {m: negative[m]["sustained_noise"] for m in MODELS}
    assert not a["tiny"]["yes"]
    _, cost, path = route("cascade", a, a_ready)
    b_job = normal["tiny"][0]
    assert b_job["yes"]
    ends = {"independent": READY_MS + b_job["ms"],
            "one_worker_budgeted": max(a_ready + cost, READY_MS) + b_job["ms"],
            "one_worker_unbudgeted": max(a_ready + a["tiny"]["ms"] + a["small"]["ms"], READY_MS) + b_job["ms"]}
    queue = {mode: {"b_complete_ms": end, "b_queue_ms": end - READY_MS - b_job["ms"],
                    "b_registered": registered(b_job, end - READY_MS, confirm_capture, READY_MS)}
             for mode, end in ends.items()}
    # Earlier ambiguous inputs still exercise fallback; no approval is
    # manufactured when both decoders decline to recognize assent.
    early = 1600
    early_answer, early_cost, early_path = route("cascade", a, early)
    assert early_path == "Tiny → Small"
    assert not registered(early_answer, early_cost, capture_time(noise, early - 180), early)

    return {"results": aggregates, "normal_raw": normal, "negative_raw": negative,
            "negative_capture_ms": captures, "queue_model": queue, "a_budgeted_path": path,
            "early_fallback": {"path": early_path, "decode_ms": early_cost},
            "deadline_ms": DEADLINE_MS, "buffer_ready_ms": READY_MS, "small_budget_ms": SMALL_BUDGET_MS}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("small", "tiny", "assent", "correction"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--runs", type=int, default=8)
    print(json.dumps(main(parser.parse_args()), ensure_ascii=False, indent=2))
