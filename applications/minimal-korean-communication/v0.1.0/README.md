# 언어의 최소 골격 | A Minimal Execution Architecture for Bounded Korean Communication

Version 0.1.0 · Bilingual research manuscript and reproducibility materials.

**최원식 / Wonsik Choi** · Independent Researcher, Seoul, Republic of Korea  
Public research contact: janefather@gmail.com · [ORCID 0009-0001-4263-9772](https://orcid.org/0009-0001-4263-9772)

## Contents

- `manuscripts/` — Korean and English manuscripts.
- `data/` — 100 original utterances, semantic annotations and the 16 development variants.
- `prototype/v0_1/` — initial rule engine, lookup baseline, data, ablations and the 432-case combinatorial check.
- `prototype/revised/` — the revised 96-case evaluation, gold outputs, lookup comparator and runtime probes.
- `results/` — reported runtime results and exhaustive verification of the finite-state encoding.
- `metadata/` — Zenodo deposit metadata. A DOI for this release becomes citable after publication.

## Reproduce

From this directory, use Python 3.9 or later. The runtime probe uses Linux process memory conventions. No external Python dependencies are needed.

```sh
python3 results/verify_lower_bound.py
python3 prototype/v0_1/evaluate.py
python3 prototype/revised/measure.py
python3 prototype/revised/runtime_probe.py rules memory
python3 prototype/revised/runtime_probe.py lookup memory
python3 prototype/revised/runtime_probe.py rules speed
python3 prototype/revised/runtime_probe.py lookup speed
python3 prototype/revised/runtime_probe.py rules rss
python3 prototype/revised/runtime_probe.py lookup rss
```

The 10-bit lower bound applies to a separate exact finite-state task. The 7,615-byte size applies to the revised prototype's engine and lexicon. Both methods score 96/96 on the bounded development set when its dialogues and gold answers are present in the lookup baseline. The revised rules score 13/100 on the original utterances. The recorded timing and memory are x86-64 Linux results.

## WRRA 연구 계보 | Related work

- [WRRA Core 2.1 paper DOI](https://doi.org/10.5281/zenodo.23386861) · [Core 2.1 GitHub](https://github.com/Wonsik-Choi-janefather/WRRA-Core-2.1). Structural inheritance, finite retained state and an explicit execution contract.
- [WRRA Core 2.0 GitHub paper](https://github.com/Wonsik-Choi-janefather/WRRA-Core-2.0/blob/main/WRRA_Core_2_0_EN.pdf). Preceding architecture specification.
- [WRRA Core 1.0 paper DOI](https://doi.org/10.5281/zenodo.22650956) · [Core 1.0 GitHub](https://github.com/Wonsik-Choi-janefather/wrra-core). Baseline domain-agnostic execution and minimum sufficient computation.

The language experiment instantiates these distinctions as reusable lexicon and relation rules, retained dialogue state, and a task-specific observable output.
