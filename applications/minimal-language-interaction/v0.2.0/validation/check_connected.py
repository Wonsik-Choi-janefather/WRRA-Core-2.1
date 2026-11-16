"""Test local ASR → captured question → durable approval → order recovery."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from approval_bridge import connect_utterance
from durable_orders import dispatch, initialize, receipt, registry
from engine.capture_grace import CaptureGrace, Job
from replay_capture import evidence, order

EXPECTED = {"품목": "녹차", "수량": "한잔"}


def submit(folder, captured, kind="valid", crash=None):
    cafe = CaptureGrace(5000, 4000)
    job = Job("A", order(cafe, "A", "녹차"), "uA")
    if kind == "old_question":
        assert cafe.advance(5140)[0]["kind"] == "retry"
    if kind == "old_question":
        assert not cafe.capture(job, 5200, 5340)[0]
    else:
        assert cafe.capture(job, *captured["detected"])[0]
    reply = evidence(job, captured["primary"])
    if kind == "speaker_mismatch":
        reply = replace(reply, speaker=replace(reply.speaker, value="B"))
    if kind == "unknown_speaker":
        reply = replace(reply, speaker=replace(reply.speaker, value=None))
    time = 9000 if kind == "expired_asr" else captured["complete"]
    session = "session-B" if kind == "other_session" else "session-A"
    reference = "아니요" if kind == "asr_disagreement" else captured["reference"]
    return connect_utterance(cafe, folder, session, job, reply, time, reference, crash)


def read_capture(model_path, path):
    from time import perf_counter_ns
    from engine.audio import FRAME_BYTES, WhisperKorean
    from engine.recovery import RecoveringCafeStream
    from replay_capture import capture_time, pcm

    spoken = pcm(path, 4.05, 4.5)
    detected = capture_time(spoken, 4800)
    assert detected == (4960, 5100)
    signal = bytes(FRAME_BYTES * 5) + spoken + bytes(FRAME_BYTES * 25)
    recognizer = WhisperKorean(model_path, RecoveringCafeStream().recognition_prompt())
    recognizer(signal, final=True)
    start = perf_counter_ns()
    first, second = recognizer(signal, final=True), recognizer.without_prompt(signal)
    elapsed = round((perf_counter_ns() - start) / 1e6)
    assert first.strip().rstrip(".!") == second.strip().rstrip(".!") == "네"
    assert 5250 + elapsed < 9000
    return {"detected": detected, "complete": 5250 + elapsed, "asr_ms": elapsed,
            "primary": first, "reference": second}


def crash_process(folder, saved, mode, point):
    child = subprocess.run([sys.executable, __file__, "--child", str(folder), str(saved), mode, point],
                           capture_output=True, timeout=10)
    assert child.returncode == 77, child.stderr.decode()


def trial(captured):
    results = []
    for point in ("before_approval_commit", "after_approval_commit", "after_registry_commit_before_reply"):
        with TemporaryDirectory() as name:
            folder = Path(name)
            initialize(folder)
            recorded = folder / "input.json"
            recorded.write_text(json.dumps(captured, ensure_ascii=False), encoding="utf-8")
            if point == "after_registry_commit_before_reply":
                key = submit(folder, captured)
                crash_process(folder, recorded, "dispatch", point)
            else:
                crash_process(folder, recorded, "submit", point)
            previous = registry(folder)
            recovered = dispatch(folder)
            if point == "before_approval_commit":
                assert not recovered and not registry(folder)
            else:
                assert len(recovered) == 1
            key = submit(folder, captured)
            dispatch(folder)
            assert registry(folder) == {key: (1, EXPECTED)}
            assert receipt(folder, key) == 1
            if previous:
                assert registry(folder) == previous
            results.append({"scenario": point, "orders_before_recovery": len(previous),
                            "recovered_without_source_replay": bool(recovered), "final_orders": 1})

    with TemporaryDirectory() as name:
        folder = Path(name)
        initialize(folder)
        for kind in ("old_question", "expired_asr", "speaker_mismatch", "unknown_speaker", "asr_disagreement"):
            assert submit(folder, captured, kind) is None
            assert dispatch(folder) == {} and registry(folder) == {}
            results.append({"scenario": kind, "durable_approval_created": False, "final_orders": 0})
        assert submit(folder, captured) != submit(folder, captured, "other_session")
        assert len(dispatch(folder)) == len(registry(folder)) == 2
        results.append({"scenario": "same_payload_two_sessions", "final_orders": 2})
    return results


if __name__ == "__main__":
    if sys.argv[1:2] == ["--child"]:
        _, _, folder, saved, mode, point = sys.argv
        if mode == "submit":
            submit(Path(folder), json.loads(Path(saved).read_text(encoding="utf-8")), crash=point)
        else:
            dispatch(Path(folder), point)
    else:
        parser = argparse.ArgumentParser()
        parser.add_argument("tiny", type=Path)
        parser.add_argument("assent", type=Path)
        args = parser.parse_args()
        capture = read_capture(args.tiny, args.assent)
        print(json.dumps({"capture": capture, "trials": trial(capture)}, ensure_ascii=False, indent=2))
