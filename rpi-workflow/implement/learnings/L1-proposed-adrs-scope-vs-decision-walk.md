# L1 — proposed-adrs defines scope; decisions are walked during ADR creation

Observed in this effort's own ADR stage (2026-08-30): the gate doc `proposed-adrs.md` was written with the decisions already mapped to options *and recommendations*, and the user then decided everything in one review of the gate doc. The ADR was written afterwards as a record of taken decisions, with tradeoffs only summarised. It worked here because the decisions happened to be clear, but it is not the intended workflow.

Intended workflow, to be encoded in the `rpi-adrs` skill:

1. `proposed-adrs.md` defines the **scope only**: which ADRs will exist, what each covers, and which decisions each will map. No options, no recommendations yet. The user approves the scope.
2. During **ADR creation**, the decisions are walked **one by one**: each decision is presented with its options, tradeoffs (pros/cons on each), and a recommendation; the user takes the recommendation or overrides; the ADR records the choice with its tradeoffs. Only then move to the next decision.
3. The stage closes with the caveats summary as before.

Why it matters: front-loading recommendations into the gate doc collapses two review moments into one, and the ADR ends up missing the pros/cons that make the decision auditable later. The gate should be cheap to approve (scope), and the expensive judgement (tradeoffs) should live where it is recorded (the ADR).
