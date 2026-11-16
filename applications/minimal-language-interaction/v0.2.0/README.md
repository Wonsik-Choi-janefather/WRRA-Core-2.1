# A Minimal Execution Architecture for Language Interaction

Wonsik Choi · [ORCID 0009-0001-4263-9772](https://orcid.org/0009-0001-4263-9772) · janefather@gmail.com

- [English manuscript](PAPER.md)
- [Zenodo preprint DOI](https://doi.org/10.5281/zenodo.24277072)
- [Earlier Korean communication study](https://doi.org/10.5281/zenodo.24268233)
- [WRRA Core 2.1](https://doi.org/10.5281/zenodo.23386861)

WRRA Core 2.1 prototype for offline dialogue control. Korean café-ordering experiments test which speaker, addressee, and question relations are required, derive bounded 22- and 43-bit state encodings, and measure speech deadlines, worker contention, and crash recovery.

The release includes annotated utterances and development cases, ten scripted confirmation scenes, state-count checks, raw timing and scheduling measurements, and process-termination results. Original recordings and model weights are outside the release.

**Keywords** · Language Interaction · Dialogue State Tracking · Finite-State Dialogue Control · State-Space Minimality · On-Device Speech Recognition · Deadline-Aware Scheduling · Idempotent Execution · Crash Recovery · Korean Dialogue · WRRA Core 2.1

## Reproduce the deterministic checks

From this directory:

```sh
python validation/verify_minimum.py
python validation/verify_overlap_bits.py
python validation/check_crash.py
```

Compare standard output with the matching files in `results/`. `validation/replay_capture.py`, `validation/benchmark_tail.py`, `validation/worker.py`, and `validation/check_connected.py` require local Whisper models and audio matching their specified clip offsets. `results/` retains the recorded runs, including delayed completions and rejected requests. Timing depends on the hardware, runtime load, and audio.

`early-data/` preserves the earlier problem and its results for comparison. The 10-bit relation-retention exercise and the 22- and 43-bit timed control bounds concern different finite tasks.
