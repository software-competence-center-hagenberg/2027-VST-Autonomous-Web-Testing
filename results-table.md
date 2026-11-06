# Aggregated Results

This file summarizes the results of all 300 runs (15 scenarios × 4
configurations × 5 runs). It is the data behind the main results table in the
paper.

- **Configurations:** `bo` = Browser Only, `sh` = Four Agent (shared history),
  `sb` = Four Agent (state-based), `ag` = AutoGen Playwright (previous work,
  re-run with the same model).
- **Scenarios:** `S1`–`S9` simple, `C10`–`C12` complex, `N13`–`N15` negative
  (expected behavior: the agent stops and reports failure).
- **Passed Runs:** ground truth from manual evaluation. For positive scenarios
  (S, C) a run passes when the test was correctly executed; for negative
  scenarios (N) a run passes when the agent correctly stopped and reported
  failure.
- **Reported Success:** what the agent system itself claimed. For positive
  scenarios this should match the manual pass; for negative scenarios it
  should be ~0, so any non-zero value is a hallucination.
- **#LLM Calls:** total number of LLM invocations, including the internal
  `browser-use` calls.
- **#Tokens:** total prompt and completion tokens across all LLM invocations.

## Per-Scenario Results

`Passed Runs` and `Reported Success` are counts out of the 5 runs per
scenario; `#LLM Calls` and `#Tokens` are averages over the 5 runs.

| Scenario | Config | Passed | Reported | #LLM Calls | #Tokens |
| -------- | ------ | ------ | -------- | ---------- | ------- |
| S1 | bo | 5/5 | 5/5 | 3.2 | 24,636 |
| S1 | sh | 5/5 | 5/5 | 15.4 | 46,809 |
| S1 | sb | 5/5 | 5/5 | 19.2 | 112,201 |
| S1 | ag | 5/5 | 5/5 | 14.6 | 25,486 |
| S2 | bo | 5/5 | 5/5 | 4.6 | 39,586 |
| S2 | sh | 5/5 | 5/5 | 33.8 | 131,432 |
| S2 | sb | 5/5 | 5/5 | 23.8 | 144,060 |
| S2 | ag | 5/5 | 5/5 | 21.0 | 58,775 |
| S3 | bo | 5/5 | 5/5 | 3.8 | 31,619 |
| S3 | sh | 5/5 | 5/5 | 15.2 | 56,370 |
| S3 | sb | 5/5 | 5/5 | 14.6 | 81,403 |
| S3 | ag | 5/5 | 5/5 | 17.8 | 41,202 |
| S4 | bo | 5/5 | 5/5 | 3.4 | 26,361 |
| S4 | sh | 5/5 | 5/5 | 17.2 | 58,857 |
| S4 | sb | 5/5 | 5/5 | 15.0 | 88,442 |
| S4 | ag | 5/5 | 5/5 | 17.0 | 36,668 |
| S5 | bo | 5/5 | 5/5 | 4.0 | 33,411 |
| S5 | sh | 5/5 | 5/5 | 19.2 | 66,750 |
| S5 | sb | 5/5 | 5/5 | 17.0 | 110,715 |
| S5 | ag | 5/5 | 5/5 | 17.0 | 37,405 |
| S6 | bo | 5/5 | 5/5 | 4.6 | 37,739 |
| S6 | sh | 5/5 | 5/5 | 15.6 | 52,814 |
| S6 | sb | 5/5 | 5/5 | 18.6 | 123,673 |
| S6 | ag | 5/5 | 5/5 | 17.0 | 35,356 |
| S7 | bo | 5/5 | 5/5 | 2.6 | 18,734 |
| S7 | sh | 5/5 | 5/5 | 7.4 | 18,478 |
| S7 | sb | 5/5 | 5/5 | 7.0 | 30,500 |
| S7 | ag | 4/5 | 5/5 | 12.2 | 27,347 |
| S8 | bo | 5/5 | 5/5 | 2.8 | 21,247 |
| S8 | sh | 5/5 | 5/5 | 7.6 | 20,814 |
| S8 | sb | 5/5 | 5/5 | 7.0 | 27,766 |
| S8 | ag | 5/5 | 5/5 | 13.8 | 30,329 |
| S9 | bo | 5/5 | 5/5 | 4.0 | 32,699 |
| S9 | sh | 5/5 | 5/5 | 13.4 | 45,314 |
| S9 | sb | 5/5 | 5/5 | 13.4 | 70,050 |
| S9 | ag | 5/5 | 5/5 | 17.0 | 37,783 |
| C10 | bo | 4/5 | 5/5 | 23.2 | 255,967 |
| C10 | sh | 2/5 | 2/5 | 181.0 | 2,056,455 |
| C10 | sb | 3/5 | 3/5 | 90.2 | 706,512 |
| C10 | ag | 3/5 | 3/5 | 46.2 | 493,058 |
| C11 | bo | 5/5 | 5/5 | 8.4 | 80,492 |
| C11 | sh | 5/5 | 5/5 | 52.0 | 234,385 |
| C11 | sb | 5/5 | 5/5 | 50.4 | 363,230 |
| C11 | ag | 5/5 | 5/5 | 17.8 | 61,592 |
| C12 | bo | 5/5 | 5/5 | 5.4 | 48,598 |
| C12 | sh | 5/5 | 5/5 | 26.0 | 99,595 |
| C12 | sb | 0/5 | 1/5 | 66.2 | 456,998 |
| C12 | ag | 5/5 | 5/5 | 17.0 | 50,108 |
| N13 | bo | 5/5 | 0/5 | 3.0 | 23,558 |
| N13 | sh | 5/5 | 0/5 | 7.0 | 15,159 |
| N13 | sb | 5/5 | 0/5 | 7.0 | 32,145 |
| N13 | ag | 5/5 | 0/5 | 17.0 | 31,400 |
| N14 | bo | 5/5 | 0/5 | 4.4 | 38,570 |
| N14 | sh | 4/5 | 0/5 | 11.6 | 40,558 |
| N14 | sb | 5/5 | 0/5 | 7.0 | 29,125 |
| N14 | ag | 5/5 | 0/5 | 16.2 | 33,173 |
| N15 | bo | 4/5 | 1/5 | 3.6 | 30,167 |
| N15 | sh | 3/5 | 2/5 | 17.6 | 65,116 |
| N15 | sb | 5/5 | 0/5 | 15.0 | 85,476 |
| N15 | ag | 2/5 | 3/5 | 19.4 | 52,470 |

## Aggregates by Scenario Category

`Passed` and `Reported` are totals over the 15 runs in the category (5 runs ×
3 scenarios); `#LLM Calls` and `#Tokens` are averages over those 15 runs.

| Category | Config | Passed | Reported | #LLM Calls | #Tokens |
| -------- | ------ | ------ | -------- | ---------- | ------- |
| Simple (S1–S9) | bo | 45/45 | 45/45 | 3.7 | 29,559 |
| Simple (S1–S9) | sh | 45/45 | 45/45 | 15.5 | 55,293 |
| Simple (S1–S9) | sb | 45/45 | 45/45 | 13.4 | 87,646 |
| Simple (S1–S9) | ag | 44/45 | 45/45 | 16.4 | 36,706 |
| Complex (C10–C12) | bo | 14/15 | 15/15 | 12.3 | 128,353 |
| Complex (C10–C12) | sh | 12/15 | 12/15 | 86.3 | 796,811 |
| Complex (C10–C12) | sb | 8/15 | 9/15 | 68.9 | 508,913 |
| Complex (C10–C12) | ag | 13/15 | 13/15 | 27.0 | 201,586 |
| Negative (N13–N15) | bo | 14/15 | 1/15 | 3.7 | 30,765 |
| Negative (N13–N15) | sh | 12/15 | 2/15 | 11.7 | 40,278 |
| Negative (N13–N15) | sb | 15/15 | 0/15 | 9.7 | 48,915 |
| Negative (N13–N15) | ag | 12/15 | 3/15 | 17.5 | 39,014 |

## Overall (all 15 scenarios, 75 runs per configuration)

`Passed` and `Reported` are totals over all 75 runs; `#LLM Calls` and `#Tokens`
are averages over the 75 runs.

| Config | Passed | Reported | #LLM Calls | #Tokens |
| ------ | ------ | -------- | ---------- | ------- |
| bo | 73/75 | 61/75 | 5.4 | 49,559 |
| sh | 69/75 | 59/75 | 29.3 | 200,594 |
| sb | 68/75 | 54/75 | 24.8 | 164,153 |
| ag | 69/75 | 61/75 | 18.7 | 70,143 |

## Reported Success vs. Manual Evaluation (Hallucination Analysis)

The agent's own verdict (reported success) is compared against the manual
ground truth.

- **False positive (hallucination):** the agent reported success, but the run
  was actually incorrect (manual = fail). For negative scenarios this means the
  agent claimed success on a test that was supposed to fail.
- **False negative (gave up):** the agent reported failure, but the run was
  actually correct (manual = pass). This only applies to positive scenarios.

| Config | False Positives (hallucinations) | False Negatives (gave up) |
| ------ | -------------------------------- | ------------------------- |
| bo | 2 (C10, N15) | 0 |
| sh | 2 (N15, N15) | 0 |
| sb | 1 (C12) | 0 |
| ag | 4 (S7, N15, N15, N15) | 0 |

In total, nine runs reported success despite an incorrect execution. Six
occurred in `N15` (one `bo`, two `sh`, and three `ag` runs), where the agents
corrected the invalid phone number and then reported success. The remaining
cases are one `bo` run of `C10`, one `sb` run of `C12`, and one `ag` run of
`S7`, in which the agents incorrectly assessed the resulting application state.
