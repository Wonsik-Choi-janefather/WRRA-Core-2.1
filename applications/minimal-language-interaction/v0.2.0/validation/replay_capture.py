"""Actual offline ASR for PCM, followed by deterministic timing replay."""
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter_ns
import wave

from engine.audio import FRAME_BYTES, FRAME_MS, RATE, WhisperKorean, rms
from engine.capture_grace import CaptureGrace, Job
from engine.evidence import Judgment, Observation, ReplyEvidence
from engine.recovery import RecoveringCafeStream


def deny_socket(event, args):
    if event.startswith("socket."):
        raise RuntimeError("Offline replay.")


sys.addaudithook(deny_socket)


def pcm(path, start, end):
    with wave.open(str(path)) as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (RATE, 1, 2):
            raise ValueError("Use 16 kHz mono PCM16 WAV.")
        audio.setpos(round(start * RATE))
        return audio.readframes(round((end - start) * RATE))


def capture_time(clip, release, minimum_frames=7):
    streak = 0
    for offset in range(0, len(clip) - FRAME_BYTES + 1, FRAME_BYTES):
        streak = streak + 1 if rms(clip[offset:offset + FRAME_BYTES]) >= 700 else 0
        if streak == minimum_frames:
            end = release + (offset // FRAME_BYTES + 1) * FRAME_MS
            return end - streak * FRAME_MS, end
    return None


def decode(model, recorded):
    padded = bytes(FRAME_BYTES * 5) + recorded + bytes(FRAME_BYTES * 25)
    model(padded, final=True)  # Measure a loaded and warmed recognizer.
    start = perf_counter_ns()
    primary, reference = model(padded, final=True), model.without_prompt(padded)
    assert primary.strip().rstrip(".!") == reference.strip().rstrip(".!") == "네"
    return primary, round((perf_counter_ns() - start) / 1e6)


def order(cafe, slot, item):
    return cafe.start(slot, slot, item, "한 잔", 0)[0]["question_id"]


def evidence(job, text):
    key = job.utterance
    voice = Observation(key + "/voice", key, "voice")
    address = Observation(key + "/address", key, "gaze")
    return ReplyEvidence(key, Judgment("전사", text, (voice,)),
                         Judgment("화자 테스트 값", job.dialogue, (voice,)),
                         Judgment("수신자 테스트 값", "카페", (address,)),
                         Judgment("대화", job.dialogue), Judgment("질문", job.question))


def compare(a, b, spoken, *, serial):
    cafe = CaptureGrace(5000, 4000)
    job_a = Job("A", order(cafe, "A", "녹차"), "uA")
    job_b = Job("B", order(cafe, "B", "보리차"), "uB")
    assert cafe.capture(job_a, *capture_time(spoken, 3900))[0]
    assert cafe.capture(job_b, *capture_time(spoken, 4400))[0]
    ready_a, ready_b = (release + len(spoken) // (RATE * 2 // 1000)
                        for release in (3900, 4400))
    end_a = ready_a + a[1]
    end_b = (max(ready_b, end_a) if serial else ready_b) + b[1]
    rows = {}
    for now, job, recognized in sorted(((end_a, job_a, a), (end_b, job_b, b)), key=lambda row: row[0]):
        outcome, _ = cafe.complete(job, evidence(job, recognized[0]), now)
        rows[job.dialogue] = {"complete_ms": now, "registered": outcome is not None
                              and outcome.status == "accepted"}
    return rows


def run(args):
    spoken = pcm(args.assent, 4.05, 4.5)
    impact = pcm(args.impulse, 0, .2)
    spoken_at = capture_time(spoken, 3900)
    impact_at = capture_time(impact, 4700)
    late_at = capture_time(spoken, 5000)
    assert spoken_at is not None and spoken_at[1] < 5000
    assert impact_at is None and late_at is not None and late_at[0] >= 5000

    ctx = RecoveringCafeStream().recognition_prompt()
    a = decode(WhisperKorean(args.small, ctx), spoken)
    b = decode(WhisperKorean(args.tiny, ctx), spoken)
    assert all(entry["registered"] for entry in compare(a, b, spoken, serial=False).values())

    cafe = CaptureGrace(5000, 4000)
    late_job = Job("A", order(cafe, "A", "녹차"), "late")
    assert not cafe.capture(late_job, *late_at)[0]
    assert cafe.complete(late_job, evidence(late_job, a[0]), late_at[1] + a[1])[0] is None
    assert not cafe.dialogues.orders()

    cafe = CaptureGrace(5000, 4000)
    old = Job("A", order(cafe, "A", "녹차"), "expired")
    assert cafe.capture(old, *spoken_at)[0]
    assert cafe.advance(9000)[0]["kind"] == "retry"
    assert cafe.complete(old, evidence(old, a[0]), 9001)[0] is None
    assert not cafe.dialogues.orders()

    cafe = CaptureGrace(5000, 4000)
    near = Job("A", order(cafe, "A", "녹차"), "near-boundary")
    near_at = capture_time(spoken, 4800)
    assert near_at is not None and near_at[0] < 5000 <= near_at[1]
    assert not cafe.advance(5000)
    assert cafe.capture(near, *near_at)[0]
    ready = 4800 + len(spoken) // (RATE * 2 // 1000)
    near_completed = ready + a[1]
    decision, _ = cafe.complete(near, evidence(near, a[0]), near_completed)
    near_registered = decision is not None and decision.status == "accepted"
    assert near_registered == (near_completed < 9000)
    assert bool(cafe.dialogues.orders()) == near_registered

    # Isolate the overlap effect by reusing the previous experiment's
    # measured Small latency with the same PCM sample.
    previous_ms = 3485
    earlier = CaptureGrace(5000, 4000)
    earlier_job = Job("A", order(earlier, "A", "녹차"), "fixed-latency")
    assert earlier.capture(earlier_job, *near_at)[0]
    fixed, _ = earlier.complete(earlier_job, evidence(earlier_job, a[0]), ready + previous_ms)
    assert fixed.status == "accepted"

    cutoff = CaptureGrace(5000, 4000)
    at_limit = Job("A", order(cutoff, "A", "녹차"), "on-cutoff")
    assert cutoff.advance(5139) == []
    accepted, emitted = cutoff.capture(at_limit, 5000, 5140)
    assert not accepted and emitted[0]["kind"] == "retry"
    assert not cutoff.dialogues.orders()

    independent = compare(a, b, spoken, serial=False)
    shared = compare(a, b, spoken, serial=True)
    return {"onset_detected_ms": spoken_at, "impact_detected": impact_at,
            "late_onset_detected_ms": late_at, "small_decode_ms": a[1], "tiny_decode_ms": b[1],
            "independent_worker_schedule": independent, "one_worker_schedule": shared,
            "modeled_extra_wait_b_ms": shared["B"]["complete_ms"] - independent["B"]["complete_ms"],
            "bad_registrations_in_late_cases": 0,
            "within_deadline_onset_missed": 0, "recovered_boundary_response": {
                "onset_detected_ms": near_at, "complete_ms": near_completed, "registered": near_registered,
                "replay_using_previous_latency_ms": previous_ms,
                "replay_using_previous_completion_ms": ready + previous_ms}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("small", "tiny", "assent", "impulse"):
        parser.add_argument(name, type=Path)
    print(json.dumps(run(parser.parse_args()), indent=2))
