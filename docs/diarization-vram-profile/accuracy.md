# Diarization Accuracy (Phase A.3)

DER computed with `pyannote.metrics.DiarizationErrorRate(collar=0.25, skip_overlap=False)`.

Reference for each file: fp32/bs=16/unlimited/r=0 (chosen per Phase A finding that bs=16 saturates throughput).

Tiers: **T1** DER ≤ 1 %, **T2** DER ≤ 3 %, **T3** DER > 3 % or speaker-count mismatch.


| file | cap | bs | mp | ref_spk | hyp_spk | DER | tier |
|---|---|---:|---|---:|---:|---:|:---:|
| 0.5h_1899s | unl | 1 | off | 4 | 4 | 0.0007 | **T1** |
| 0.5h_1899s | unl | 1 | on | 4 | 2 | 0.3332 | **T3** |
| 0.5h_1899s | unl | 4 | off | 4 | 4 | 0.0000 | **T1** |
| 0.5h_1899s | unl | 4 | on | 4 | 2 | 0.3332 | **T3** |
| 0.5h_1899s | unl | 8 | off | 4 | 4 | 0.0000 | **T1** |
| 0.5h_1899s | unl | 8 | on | 4 | 2 | 0.3332 | **T3** |
| 0.5h_1899s | unl | 16 | off | 4 | 4 | 0.0000 | **T1** *(reference)* |
| 0.5h_1899s | unl | 16 | on | 4 | 2 | 0.3332 | **T3** |
| 0.5h_1899s | unl | 32 | off | 4 | 4 | 0.0000 | **T1** |
| 0.5h_1899s | unl | 32 | on | 4 | 2 | 0.3332 | **T3** |
| 0.5h_1899s | unl | 64 | off | 4 | 4 | 0.0000 | **T1** |
| 0.5h_1899s | unl | 64 | on | 4 | 2 | 0.3332 | **T3** |
| 0.5h_1899s | unl | 128 | off | 4 | 4 | 0.0000 | **T1** |
| 0.5h_1899s | unl | 128 | on | 4 | 2 | 0.3332 | **T3** |
| 2.2h_7998s | unl | 1 | off | 3 | 3 | 0.0000 | **T1** |
| 2.2h_7998s | unl | 1 | on | 3 | 2 | 0.2693 | **T3** |
| 2.2h_7998s | unl | 4 | off | 3 | 3 | 0.0000 | **T1** |
| 2.2h_7998s | unl | 4 | on | 3 | 2 | 0.2693 | **T3** |
| 2.2h_7998s | unl | 8 | off | 3 | 3 | 0.0000 | **T1** |
| 2.2h_7998s | unl | 8 | on | 3 | 2 | 0.2693 | **T3** |
| 2.2h_7998s | unl | 16 | off | 3 | 3 | 0.0000 | **T1** *(reference)* |
| 2.2h_7998s | unl | 16 | on | 3 | 2 | 0.2693 | **T3** |
| 2.2h_7998s | unl | 32 | off | 3 | 3 | 0.0000 | **T1** |
| 2.2h_7998s | unl | 32 | on | 3 | 2 | 0.2693 | **T3** |
| 2.2h_7998s | unl | 64 | off | 3 | 3 | 0.0000 | **T1** |
| 2.2h_7998s | unl | 64 | on | 3 | 2 | 0.2693 | **T3** |
| 2.2h_7998s | unl | 128 | off | 3 | 3 | 0.0000 | **T1** |
| 2.2h_7998s | unl | 128 | on | 3 | 2 | 0.2693 | **T3** |
