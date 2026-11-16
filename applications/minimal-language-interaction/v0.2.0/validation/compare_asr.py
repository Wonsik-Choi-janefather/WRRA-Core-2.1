"""Compare offline ASR decisions on the same labeled PCM clips."""
import argparse
from array import array
import json
from math import exp, sin
from pathlib import Path
import random
import resource
from statistics import median
import sys
from time import perf_counter
import wave


def offline(event, args):
    if event.startswith("socket."):
        raise RuntimeError(f"Socket event blocked: {event}")


sys.addaudithook(offline)
from engine.audio import WhisperKorean, FRAME_BYTES, RATE
from engine.recovery import RecoveringCafeStream


def read(path, begin, end):
    with wave.open(str(path)) as f:
        if (f.getframerate(), f.getnchannels(), f.getsampwidth()) != (RATE, 1, 2):
            raise ValueError("Expected 16 kHz mono 16-bit PCM WAV.")
        f.setpos(round(begin * RATE))
        return f.readframes(round((end - begin) * RATE))


def run(args):
    rng = random.Random(314)
    noise = array("h", (rng.randint(-2400, 2400) for _ in range(2240))).tobytes()
    tap = array("h", (int(11000 * exp(-i / 550) * sin(i * .8)) for i in range(2240))).tobytes()
    cases = (
        ("original_assent", read(args.assent, 4.05, 4.5), True),
        ("cropped_assent_140ms", read(args.assent, 4.2, 4.34), True),
        ("quantity_reply", read(args.assent, 2.05, 2.95), False),
        ("explicit_cancel", read(args.correction, 5.48, 7.89), False),
        ("opening_noise", read(args.correction, 0, .2), False),
        ("generated_noise", noise, False),
        ("generated_tap", tap, False),
    )
    started = perf_counter()
    r = WhisperKorean(args.model, RecoveringCafeStream().recognition_prompt())
    load = perf_counter() - started

    def decode(clip):
        pcm = bytes(FRAME_BYTES * 5) + clip + bytes(FRAME_BYTES * 25)
        start = perf_counter()
        primary, reference = r(pcm, True), r.without_prompt(pcm)
        return primary, reference, 1000 * (perf_counter() - start)

    decode(cases[0][1])  # Exclude first inference from warm measurements.
    rows = []
    for name, pcm, expected in cases:
        primary, reference, latency = decode(pcm)
        assent = {"네", "예"}
        detected = all(text.strip().rstrip(".!") in assent for text in (primary, reference))
        rows.append({"clip": name, "expected_assent": expected, "detected_assent": detected,
                     "primary": primary, "reference": reference, "two_pass_ms": round(latency, 2)})
    return {"model": args.model.name, "model_file_bytes": sum(p.stat().st_size
                  for p in args.model.iterdir() if p.is_file()), "load_seconds": round(load, 3),
            "peak_process_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2),
            "median_two_pass_ms": round(median(row["two_pass_ms"] for row in rows), 2), "clips": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path)
    parser.add_argument("assent", type=Path)
    parser.add_argument("correction", type=Path)
    print(json.dumps(run(parser.parse_args()), ensure_ascii=False, indent=2))
