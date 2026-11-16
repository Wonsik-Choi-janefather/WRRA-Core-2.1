# A Minimal Execution Architecture for Language Interaction

## From Dialogue Relations to Time Constraints and Durable Execution

**Wonsik Choi** · 16 November 2026 · Research preprint  
Correspondence: janefather@gmail.com · [ORCID 0009-0001-4263-9772](https://orcid.org/0009-0001-4263-9772)  
Architectural reference: [WRRA Core 2.1](https://doi.org/10.5281/zenodo.23386861)
Earlier study: [A Minimal Execution Architecture for Bounded Korean Communication](https://doi.org/10.5281/zenodo.24268233)

### Abstract

We define a target interaction and identify the dialogue relations and minimum execution state space needed to implement it. Building on WRRA Core 2.1, we separate vocabulary, relation-processing rules, and dialogue state, then add speaker, addressee, and confirmation-question bindings, recognition deadlines, and durable approval records to a Korean café-ordering task. We exhaustively evaluated all eight subsets of the three relations on ten scripted scenes ending in the same assent. Only the complete relation set preserved all three valid approvals with zero incorrect registrations. With a bounded menu, millisecond timing and two question labels, the fixed-width state encoding required 22 bits for one dialogue and 43 bits for two independent dialogues. Offline replay associated an answer starting at 4.96 s with the original question after a 140 ms onset check. In eight repetitions of the same recording, Small completed seven approvals by the 9 s deadline and Tiny-first completed eight. Forced process termination in a voice-to-order fixture showed recovery after durable approval and no duplicate order for a repeated approval ID. The conclusions concern the specified task, audio samples and prototype.

**Keywords** Language interaction, dialogue state, finite-state minimality, offline speech recognition, approval records

## 1 Introduction

Two people can say the same Korean *ne* (“yes”) while addressing different listeners. Even the right speaker can answer a question that was superseded by a correction. The study asks which relations distinguish those events, how many states are needed to retain the distinction while the system waits, and what record allows an approved action to resume after interruption.

## 2 Study design

### 2.1 Korean materials and task scope

The project began with 100 everyday Korean utterances. The initial rule prototype, extended for loans and appointment corrections, matched the expected meaning structures for 13 of the 100 original utterances and all 96 investigator-constructed development cases. A lookup baseline given all development inputs and answers also passed all 96 cases. The 13 original utterances describe the scope covered by the initial rules. Later experiments focus on café-order confirmation, correction, cancellation, late replies, and registration recovery.

An earlier task concerned 1,024 distinguishable retained relation states, requiring 10 bits. The corresponding enhanced prototype occupied 7,615 bytes of source and data. These figures refer to the earlier relation task and its implementation respectively. The café state bound and extended engine size are reported separately.

The café experiments comprise scripted scenes with a common final utterance, offline replay of existing Korean recordings and a real single-worker scheduling trial, and forced process termination after passing speech recognition results to the existing dialogue and durable registration components. Speaker and addressee labels were controlled inputs in the relevant trials. The study did not estimate automatic speaker identification or gaze accuracy.

### 2.2 WRRA transformation and test criteria

Transcription supplies the surface form. Dialogue control binds the utterance, speaker, addressee, dialogue, and question identities. Incomplete judgments remain in the evidence record alongside their reported origins. A correction changes the affected slot and issues a new question. The controller distinguishes the speech-onset cutoff from the recognition-completion cutoff. An eligible and explicitly confirmed approval is sent to the durable registry.

| Validated input | WRRA transformation and output | Falsification condition |
|---|---|---|
| Ten scenes with the same assent | Group indistinguishable observations and compare expected order states | One of the three relations can be removed while preserving all outcomes |
| Bounded menu, deadlines and queue | Enumerate distinguishable states and assign a fixed-width code | A narrower code preserves all specified outputs |
| Deadline-edge audio and worker contention | Separate onset from completion and isolate superseded questions | A late reply approves the original question, or a timely eligible reply is lost |
| Process termination during approval and registration | Replay the same approval ID and compare registration receipts | Durable approval is lost or a single ID produces duplicate orders |

### 2.3 Related work

Clark and Brennan's account of grounding situates confirmation within coordination between interlocutors [1]. The state lower bound uses distinguishability by subsequent inputs, following the principle used for finite automata [2]. The offline recognition tests use Whisper models [3]. Idempotence refers to preserving the intended effect of one request across repeated requests [4].

## 3 Relation minimality and state encoding

### 3.1 Exhaustive projection of three relations

The final surface utterance, target dialogue, and pre-correction or post-correction context are fixed where relevant. For each selected subset, scenes with identical retained observations form a class. When a class contains conflicting expected order states, a deterministic decision rule restricted to those observations cannot reproduce every outcome. Its minimum error count in each class is the class size minus the frequency of its majority outcome. A policy allowing zero incorrect registrations must withhold valid approvals in the conflicting classes.

| Removed relation | Indistinguishable cases | Minimum valid approvals withheld at zero incorrect registrations |
|---|---|---:|
| Speaker | Customer assent versus another customer's assent | 1 |
| Addressee | Assent to the device versus assent to a companion | 1 |
| Question | Assent to the earlier versus revised question | 2 |
| None | No class contains conflicting expected outcomes | 0 |

All eight subsets were evaluated. Only the full subset had zero unavoidable errors. The existing engine reproduced the three expected approvals and seven non-registrations. The result is about required distinctions under the fixed observations. An explicit reply link or an established screen selection can carry a question relation without using the same field layout.

### 3.2 Fixed-width codes for a bounded timing model

The menu contains five items, six permitted item–unit pairings, and five quantities per pairing. With no timer, one empty state, ten quantity-waiting states, and thirty approval-waiting states give 41 states and a 6-bit fixed-width code for one slot.

With timing, there are 40 active order candidates, two question stages (first question and retry), two active question labels, and 14,000 timing states. At 1 ms resolution, onset verification has 5,140 possible remaining-time values and recognition in progress has 8,860. The 140 ms overlap extends the former range and postpones the earliest entry into the latter. One slot adds 40 deferred candidates and one empty state. Two slots have an additional FIFO order whenever both are deferred.

**N₁ = 40 × 2 × 2 × 14,000 + 40 + 1 = 2,240,041**  
**N₂ = N₁² + 40² = 5,017,783,683,281**

Subsequent quantity or assent probes, expiry timing, event type, and FIFO resumption distinguish the model's states. Dense indices give fixed-width codes of ⌈log₂ N₁⌉ = 22 bits and ⌈log₂ N₂⌉ = 43 bits. Slot-to-customer bindings and the order of simultaneous expiries are fixed. The input layer must ensure that reuse of the two question labels cannot bind an old response to a new question. Audio buffers, ID generation, committed order history, and logs require separate storage.

## 4 Offline recognition and deadlines

### 4.1 Onset versus completion

A response must begin before 5 s after the question. A timely onset permits recognition up to 9 s after the question. The onset detector requires 140 ms of continuous activity, so the controller keeps the original question available for that additional interval to evaluate the backdated onset. An actual recording placed at 4.96 s and detected at 5.10 s was bound to its original question. One remeasurement completed at 9.687 s, so registration was withheld. Responses beginning at or after 5 s did not approve the expired question.

### 4.2 Execution cost and local ASR

| Measurement | Repetitions | Median | p95 | Peak RSS |
|---|---:|---:|---:|---:|
| Hold, reissue, stale rejection and approval | 500 | 0.80 ms | 1.08 ms | 13.38 MiB |
| Two Small decodes plus the control cycle | 10 | 3.58 s | 3.87 s | 602.23 MiB |

Python socket access was blocked on x86-64. Engine source and data occupied 55,529 bytes; Small model files occupied 486,212,372 bytes. Model loading took 2.36 s, measured separately. The ASR measurement repeated a 1.64 s clip. The table gives process peak RSS and excludes complete capture-to-actuation latency.

| Recognition policy | Approvals by 9 s | Median / p95 | Incorrect approvals on controls |
|---|---:|---:|---:|
| Small only | 7/8 | 3.445 s / 3.758 s | 0/5 |
| Tiny first | 8/8 | 0.535 s / 0.638 s | 0/5 |
| Tiny first with budgeted Small fallback | 8/8 | 0.535 s / 0.638 s | 0/5 |

The second experiment reused the same recorded assent eight times, with input ready at 5.25 s. One Small result arrived at 9.008 s. The Tiny-first policies did not invoke Small on the positive fixture. Negative inputs included refusal, cancellation and noise. Decoding with and without a prompt uses the same model and does not provide statistically independent evidence.

In a separate model comparison, Small and Tiny recognized a 140 ms cut of one recorded assent; Base missed it. Tiny mistranscribed a quantity and produced spurious text on noise. Short-assent routing reduced the median from 3.42 s to 0.61 s in a separate hybrid replay, while keeping both models loaded increased peak RSS from 602 to 680 MiB.

## 5 Worker contention and durable execution

### 5.1 One worker and two guests

Actual PCM segments were submitted to one local worker with a wall-clock offset. Small recovered A’s quantity reply, which Tiny missed. B answered a different pending question with an assent. The fallback budget of 3.868 s was derived by rounding upward to milliseconds the Small two-pass-only p95 of 3.8675 s over ten repetitions of the 1.64 s clip in Section 4.2. The combined rule-and-ASR p95 shown there is rounded to 3.87 s.

| A's fallback policy near the deadline | A's outcome | B's queue wait | B's completion |
|---|---|---:|---|
| Always decode with Small | Quantity decoded at 9.786 s; deadline missed | 4.636 s | 10.367 s; deadline missed |
| Check remaining budget | Small skipped; approval held | 0.571 s | 6.196 s; approved |

Earlier in the timeline, both policies recovered A's quantity and generated a new confirmation question. A still needed to approve the revised order. Each scheduling condition was executed once; the percentile used as the budget is an estimate, not a worst-case guarantee.

### 5.2 Voice approval and recovery

A recorded assent was decoded twice with Tiny. Under the replay clock, onset was 4.96 s, detection was 5.10 s, and completion was 5.936 s. The controller stored the approved order and an ID derived from the session, dialogue and question in SQLite. A separate mock registry made the approval ID unique and returned the same order number on retries.

| Process termination point | Restart behavior | Final registrations |
|---|---|---:|
| Before approval storage | Original approval input must be replayed | 1 after replay |
| After approval storage and before registration | Resume from the durable approval | 1 |
| After registration but before delivering its reply | Return the existing order number on retry | 1 |

Nine integration scenarios included stale questions, expired recognition, speaker mismatch, unknown speaker, and disagreement between passes. None of those five controls created an approval record or order. Two valid approvals from distinct sessions with identical order content produced two orders. Termination was delivered to actual child processes. Audio was decoded once and the resulting record was replayed for each fault location.

## 6 Discussion and conclusion

The relation minimality result applies to the ten scenes and their fixed observations. The 22- and 43-bit results apply to the specified bounded state codes. The rule engine size represents an implementation measurement; local speech recognition, durable storage and the full runtime have separate costs.

The division between perception and control makes failure modes inspectable. A small recognizer handled short assent quickly in these samples and could miss a quantity reply. An unclear speaker can be recorded alongside a recognized word while the order remains pending. Durable approval and actual registration remain distinct events. Recovery after the durable boundary was demonstrated; interruption before it requires upstream input and question-state replay.

The experiments were conducted in Korean. The questions about speaker, addressee and reply target are applicable to other languages, but cross-language generalization requires additional data. The scripts were investigator-constructed and the audio trials used a limited set of recordings, with speaker and addressee supplied as test inputs. Repeated decoding does not estimate recognition rates across people or environments. The recovery tests used SQLite, a mock order registry and process termination; power loss, storage damage and physical actuation were outside the tested conditions.

Comparative cognition offers possible follow-on tasks, such as testing whether role reversal changes the target of a response. No neural or genetic mechanism was evaluated here. Defining an interaction and its failure conditions makes it possible to measure its required relations, state width, time costs and recovery record separately. Explicit action conditions also make it possible to trace and retest how a probabilistic interpretation became an action.

## References

[1] Clark, H. H., & Brennan, S. E. (1991). Grounding in communication. *Perspectives on Socially Shared Cognition*, 127–149. https://doi.org/10.1037/10096-006

[2] Trevisan, L. (2014). *Notes on the Myhill–Nerode Theorem*. Stanford CS103. https://theory.stanford.edu/~trevisan/cs103-14/lecture15.pdf

[3] Radford, A., et al. (2023). Robust Speech Recognition via Large-Scale Weak Supervision. *PMLR*, 202, 28492–28518. https://proceedings.mlr.press/v202/radford23a.html

[4] Fielding, R., Nottingham, M., & Reschke, J. (2022). *HTTP Semantics*. RFC 9110, §9.2.2. https://www.rfc-editor.org/info/rfc9110/

## Reproducibility

The companion materials include scripted cases, executable state-count checks, raw timing results and process-termination tests. Source audio and model weights are outside the release package.
