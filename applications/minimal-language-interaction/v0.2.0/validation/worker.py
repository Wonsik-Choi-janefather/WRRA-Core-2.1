"""Feed PCM by wall clock into one nonpreemptive, offline ASR worker."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
from threading import Event
from time import perf_counter, sleep

from benchmark_tail import decode
from engine.audio import WhisperKorean
from engine.capture_grace import CaptureGrace, Job
from engine.recovery import RecoveringCafeStream
from replay_capture import capture_time, evidence, order, pcm

DEADLINE = 9000
BUDGET = 3868


def run_trial(policy, a_release, small, tiny, quantity, assent):
    cafe = CaptureGrace(5000, 4000)
    old_a = cafe.start("A", "A", "녹차", "한 잔", 0)[0]["question_id"]
    # Seed an ordinary quantity question for a drink from an earlier turn.
    # In this fixture the pending order starts with a candidate item only.
    from engine.recovery import OrderQuestion
    cafe.dialogues._dialogues["A"].stream.order_question = OrderQuestion("녹차", "candidate")
    jobs = {"A": Job("A", old_a, "uA"), "B": Job("B", order(cafe, "B", "보리차"), "uB")}
    audio = {"A": quantity, "B": assent}
    release = {"A": a_release, "B": 4700}
    pending = {key: Event() for key in jobs}
    captured = {key: capture_time(audio[key], release[key]) for key in jobs}
    assert all(captured.values()), captured
    ready = {key: release[key] + len(audio[key]) // 32 for key in jobs}
    assert ready["A"] < ready["B"], ready
    start = perf_counter()

    def clock():
        return round((perf_counter() - start) * 1000)

    def until(time_ms):
        sleep(max(0, time_ms / 1000 - (perf_counter() - start)))

    def worker(key):
        pending[key].wait()
        began = clock()
        result = decode(tiny, audio[key])
        started_small = False
        if key == "A" and not result["yes"] and (
            policy == "always" or clock() + BUDGET < DEADLINE
        ):
            result = decode(small, audio[key])
            started_small = True
        end = clock()
        return key, began, end, started_small, result

    with ThreadPoolExecutor(max_workers=1) as executor:
        futures = {}
        timeline = [(times[1], 0, key) for key, times in captured.items()]
        timeline.extend((time_ms, 1, key) for key, time_ms in ready.items())
        for at, kind, key in sorted(timeline):
            until(at)
            if kind == 0:
                assert cafe.capture(jobs[key], captured[key][0], at)[0], captured
            else:
                futures[key] = executor.submit(worker, key)
                pending[key].set()
        results = sorted((future.result() for future in futures.values()), key=lambda row: row[2])

    entries = {}
    for key, began, end, fallback, result in results:
        job = jobs[key]
        text = result["text"]
        normalized = lambda value: value.strip().rstrip(".!")
        # The quantity fixture requires agreement on the specific response.
        # Let the actual execution engine interpret the agreeing transcript.
        agreed = normalized(text) == normalized(result["reference"]) and bool(text.strip())
        decision = None
        if agreed:
            decision, _ = cafe.complete(job, evidence(job, text), end)
        else:
            cafe.advance(end)
        entries[key] = {"queue_ms": began - ready[key], "inference_ms": end - began,
                        "buffer_to_result_ms": end - ready[key], "done_ms": end,
                        "fallback": fallback, "transcriptions": [text, result["reference"]],
                        "prompt": decision.prompt if decision else None,
                        "status": decision.status if decision else "held",
                        "registered": key in cafe.dialogues.orders()}
    return entries


def main(args):
    prompt = RecoveringCafeStream().recognition_prompt()
    small, tiny = (WhisperKorean(path, prompt) for path in (args.small, args.tiny))
    quantity = pcm(args.assent, 2.05, 2.95)
    assent = pcm(args.assent, 4.05, 4.5)
    for model in (small, tiny):
        decode(model, assent)
    probe = {name: decode(model, quantity) for name, model in (("Small",small),("Tiny",tiny))}
    def cleaned(pair):
        return {pair[key].strip().rstrip(".!") for key in ("text", "reference")}
    assert cleaned(probe["Small"]) == {"한 잔이요"} and cleaned(probe["Tiny"]) != {"한 잔이요"}, probe
    rows = {}
    for label, delay in (("early", 1200), ("edge", 4200)):
        for policy in ("always", "budgeted"):
            result = run_trial(policy, delay, small, tiny, quantity, assent)
            rows[f"{label}/{policy}"] = result
            print(label, policy, result, flush=True, file=__import__("sys").stderr)
    negatives = {}
    for label, clip in (
        ("explicit_no", pcm(args.correction, 3.30, 3.95)),
        ("cancel", pcm(args.correction, 5.48, 7.89)),
        ("opening_noise", pcm(args.correction, 0, .2)),
        ("other_yes", pcm(args.other, 0, .4)),
    ):
        hit = decode(tiny, clip)
        cafe = CaptureGrace(5000, 4000)
        job = Job("A", order(cafe, "A", "녹차"), label)
        capture = capture_time(clip, 1000)
        if capture and cafe.capture(job, *capture)[0] and hit["yes"]:
            decision = evidence(job, hit["text"])
            if label == "other_yes":
                decision = replace(decision, speaker=replace(decision.speaker, value="B"))
            cafe.complete(job, decision, 1000 + len(clip)//32 + hit["ms"])
        assert not cafe.dialogues.orders()
        negatives[label] = {"capture": capture, "recognized_assent": hit["yes"],
                            "speaker_test_value": "B" if label == "other_yes" else "A",
                            "registered": False}
    return {"probe": probe, "trials": rows, "negative": negatives}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for arg in ("small", "tiny", "assent", "correction", "other"):
        parser.add_argument(arg, type=Path)
    print(json.dumps(main(parser.parse_args()), ensure_ascii=False, indent=2))
