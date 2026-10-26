# Z-QEA Decision Receipt — trivalent CI decisions with sealed receipts

> Your pipeline returns **1**, **0**, or **REFUSED** — with the statistical
> band declared *before* the data, and a sealed post-quantum receipt
> (SHA3-256 chain, optional ML-DSA-44 signature) for every verdict.

## Why

CI lies. A flaky test suite at 64 runs passes sometimes and fails others,
and the checkmark pretends it knows. Modern pipelines force binary
yes/no on statistical evidence. This Action makes the honest third answer
a first-class citizen: if the evidence falls inside the declared noise
band, the pipeline **refuses to decide** and says why.

## Use

```yaml
- name: Gate the canary with declared confidence
  uses: SerenaSolutions/decision-receipt@v1
  with:
    decision-file: canary.json        # {"metric": 0.987, "shots": 2048,
                                      #  "epsilon": 0.05, "threshold": 0.95}
    family: '2'                       # Bonferroni family of joint decisions
    prev-receipt: receipts/last.receipt.json   # chains the history
    signing-key: ${{ secrets.ZQEA_KEY }}       # optional ML-DSA-44
```

Outputs: `verdict` (`1`/`0`/`REFUSED`), `reason`, `receipt` (sealed JSON),
`seal`. A REFUSED verdict exits 1 — an honest refusal is never a silent pass.

## What the receipt proves

- The rule (one-sided Hoeffding band, Bonferroni-corrected) was declared
  **before** the evidence was read.
- The verdict and its reason, sealed with SHA3-256 over a canonical form.
- Chaining: the previous receipt's seal is *re-verified* before chaining;
  a tampered history is refused with `CHAIN_BROKEN`, never silently trusted.
- Optional post-quantum signature (ML-DSA-44, FIPS 204).

## Verify it yourself

Every seal is `SHA3-256(json.dumps(payload, sort_keys=True,
ensure_ascii=True, default=str))` with the `selo_sha3_256` field removed.
Two lines of Python on any machine re-verify any receipt in this repo.

## Use cases

- Flaky-test gating with declared confidence instead of retry roulette
- Canary / rollout decisions (error-rate vs threshold with a real margin)
- ML evaluation gates where "cannot decide" is the honest answer
- Regulated pipelines that must show *why* a decision was made

## License

MIT. Author: Maria Clara dos Anjos (SerenaSolutions). Part of the
Z-QEA receipt ecosystem: decision language, receipt chain, and sealed
hardware receipts — no claim without a receipt.
