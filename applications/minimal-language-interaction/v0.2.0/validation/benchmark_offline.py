"""Measure offline rules and optional local Whisper in separate processes."""
import argparse
import json
from pathlib import Path
import platform
import resource
from statistics import median
import sys
from time import perf_counter_ns
import wave


def block_socket(event, arguments):
    if event.startswith("socket."):
        raise RuntimeError(f"Socket access disallowed: {event}")


sys.addaudithook(block_socket)
from engine.dialogues import CafeDialogues
from engine.evidence import EvidenceRouter, Judgment, Observation, ReplyEvidence

ROOT = Path(__file__).resolve().parent


def sample(text="네"):
    dialogues = CafeDialogues()
    question = dialogues.open_confirmation("a", "A", "녹차", "한 잔")["question_id"]
    router = EvidenceRouter(dialogues)

    def reply(utterance, speaker, question_id):
        voice = Observation(utterance + "/voice", utterance, "voice")
        pointing = Observation(utterance + "/address", utterance, "address")
        return ReplyEvidence(utterance, Judgment("전사", text, (voice,)),
                             Judgment("화자", speaker, (voice,)),
                             Judgment("수신자", "카페", (pointing,)),
                             Judgment("대화", "a"), Judgment("질문", question_id))

    start = perf_counter_ns()
    assert router.record(reply("u1", None, question)).status == "held"
    updated = router.reask("u1")
    assert router.record(reply("u2", "A", question)).status == "unrouted"
    assert router.record(reply("u3", "A", updated.question_id)).status == "accepted"
    elapsed_ms = (perf_counter_ns() - start) / 1e6
    assert dialogues.orders() == {"a": {"품목": "녹차", "수량": "한잔"}}
    return elapsed_ms


def stats(values):
    ordered = sorted(values)
    p95 = ordered[(95 * len(ordered) + 99) // 100 - 1]
    return {"count": len(values), "median_ms": round(median(values), 4), "p95_ms": round(p95, 4)}


def peak_mib():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(value / (1024**2 if sys.platform == "darwin" else 1024), 2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path)
    parser.add_argument("--wav", type=Path)
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--end", type=float)
    parser.add_argument("--samples", type=int)
    args = parser.parse_args()
    if (args.model is None) != (args.wav is None):
        parser.error("--model and --wav are required together for voice measurements.")

    source_bytes = sum(path.stat().st_size for path in (ROOT / "engine").iterdir()
                       if path.suffix in (".py", ".json"))
    data = {"python": platform.python_version(), "architecture": platform.machine(),
            "engine_source_and_data_bytes": source_bytes}
    if args.model is None:
        sample()
        data["rule_cycle"] = stats([sample() for _ in range(args.samples or 500)])
    else:
        from engine.audio import RATE, WhisperKorean
        from engine.recovery import RecoveringCafeStream

        with wave.open(str(args.wav)) as recording:
            if (recording.getframerate(), recording.getnchannels(), recording.getsampwidth()) != (RATE, 1, 2):
                raise ValueError("Expected a 16 kHz, mono PCM WAV.")
            recording.setpos(round(args.start * RATE))
            end = round(args.end * RATE) if args.end is not None else recording.getnframes()
            pcm = recording.readframes(end - recording.tell())
        data["clip_seconds"] = len(pcm) / (2 * RATE)
        data["model_files_bytes"] = sum(file.stat().st_size for file in args.model.iterdir()
                                        if file.is_file())
        start = perf_counter_ns()
        recognizer = WhisperKorean(args.model, RecoveringCafeStream().recognition_prompt())
        data["model_load_ms"] = round((perf_counter_ns() - start) / 1e6, 2)

        def run():
            start = perf_counter_ns()
            primary = recognizer(pcm, final=True)
            reference = recognizer.without_prompt(pcm)
            assert primary.strip().rstrip(".!") == reference.strip().rstrip(".!") == "네"
            speech_ms = (perf_counter_ns() - start) / 1e6
            sample(primary)
            return speech_ms, (perf_counter_ns() - start) / 1e6

        cold_speech, cold_total = run()
        runs = [run() for _ in range(args.samples or 10)]
        data.update(cold_first_two_pass_ms=round(cold_speech, 2),
                    cold_first_with_rule_cycle_ms=round(cold_total, 2),
                    warm_two_pass=stats([speech for speech, _ in runs]),
                    warm_with_rule_cycle=stats([total for _, total in runs]))
    data["peak_process_mib"] = peak_mib()
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
