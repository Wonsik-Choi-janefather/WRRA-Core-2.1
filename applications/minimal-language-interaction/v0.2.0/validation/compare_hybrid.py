"""Replay the same correction and confirmation flow under two ASR policies."""
import argparse
import json
from pathlib import Path
import resource
from statistics import median
import sys
from time import perf_counter

from compare_asr import read
from engine.audio import FRAME_BYTES, WhisperKorean, rms
from engine.recovery import OrderQuestion, RecoveringCafeStream

ASSENT = {"네", "예"}


def run(args):
    stream = RecoveringCafeStream()
    stream.order_question = OrderQuestion("보리차", "confirm", "한 잔")
    prompt = stream.recognition_prompt()
    started = perf_counter()
    small = WhisperKorean(args.small, prompt)
    tiny = WhisperKorean(args.tiny, prompt) if args.tiny else None
    load_ms = (perf_counter() - started) * 1000

    def pair(model, pcm):
        wave = bytes(FRAME_BYTES * 5) + pcm + bytes(FRAME_BYTES * 25)
        return model(wave, True), model.without_prompt(wave)

    original = read(args.assent, 4.05, 4.5)
    cropped = read(args.assent, 4.2, 4.34)
    pair(small, original)
    if tiny:
        pair(tiny, original)

    def turn(dialogue, pcm):
        voiced_ms = 20 * sum(rms(pcm[i:i + FRAME_BYTES]) >= 700
                             for i in range(0, len(pcm) - FRAME_BYTES + 1, FRAME_BYTES))
        start = perf_counter()
        route = "Small"
        recognized = None
        if tiny and dialogue.awaiting_order_assent and 120 <= voiced_ms <= 220:
            first, second = pair(tiny, pcm)
            if all(text.strip().rstrip(".!") in ASSENT for text in (first, second)):
                recognized = first, second
                route = "Tiny"
            else:
                route = "Tiny → Small"
        first, second = recognized if recognized is not None else pair(small, pcm)
        if not first:
            result = None
        elif voiced_ms < 160:
            result = dialogue.finish_short_assent(first, lambda: second)
        else:
            dialogue.feed(first, limit=0)
            result = dialogue.finish_checked(lambda: second)
        return {"route": route, "first": first, "second": second, "voiced_ms": voiced_ms,
                "latency_ms": round((perf_counter() - start) * 1000, 2),
                "status": result["status"] if result else "no_decision",
                "prompt": result.get("prompt") if result else None, "order": dialogue.engine.order}

    rows = {}
    rows["item_correction"] = turn(stream, read(args.corrections, 0, 3.28))
    rows["quantity_correction"] = turn(stream, read(args.corrections, 3.28, 6.25))
    rows["short_assent"] = turn(stream, cropped)
    assert rows["item_correction"]["order"] is None
    assert rows["quantity_correction"]["order"] is None
    assert stream.engine.order == {"품목": "녹차", "수량": "두잔"}, rows

    for label, pcm, pending, expected in (
        ("original_assent", original, True, True),
        ("assent_without_question", cropped, False, False),
        ("opening_noise", read(args.alternative, 0, .2), True, False),
        ("cancel_with_question", read(args.corrections, 6.25, 8.6), True, False),
    ):
        trial = RecoveringCafeStream()
        if pending:
            trial.order_question = OrderQuestion("녹차", "confirm", "한 잔")
        rows[label] = turn(trial, pcm)
        assert bool(trial.engine.order) == expected, rows[label]
    models = [args.small] + ([args.tiny] if args.tiny else [])
    return {"load_ms": round(load_ms, 2), "peak_process_mib": round(
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2),
        "model_files_bytes": sum(p.stat().st_size for model in models for p in model.iterdir() if p.is_file()),
        "assent_median_ms": round(median(rows[key]["latency_ms"]
             for key in ("short_assent", "original_assent")), 2),
        "full_flow_ms": round(sum(rows[key]["latency_ms"]
             for key in ("item_correction", "quantity_correction", "short_assent")), 2),
        "turns": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("small", type=Path)
    parser.add_argument("assent", type=Path)
    parser.add_argument("corrections", type=Path)
    parser.add_argument("alternative", type=Path)
    parser.add_argument("--tiny", type=Path)
    print(json.dumps(run(parser.parse_args()), ensure_ascii=False, indent=2))
