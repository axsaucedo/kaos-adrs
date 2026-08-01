# Stage 13 — Regulatory evidence requirements (EU AI Act)

> Deep-research output (ChatGPT deep research, imported 2026-08-01) produced from [`deep-research-prompts/13-eu-ai-act-evidence.md`](./deep-research-prompts/13-eu-ai-act-evidence.md). Part of the [research plan](./0-research-plan.md). Citations appear as opaque `citeturn...` tokens from the research tool rather than resolvable URLs; load-bearing novel claims (new benchmarks, version-specific behavior, enacted regulation numbers) should be spot-verified against primary sources before being relied on in an ADR, and claims flagged for spike verification are validated, not trusted.

# Engineering Evidence Specification for High-Risk Agentic AI Under the EU AI Act

## Scope, status, and design posture

**Purpose.** This report is engineering research for designing portable `xai` decision-ledger and explanation-packet templates. It is **not legal advice, a conformity assessment, a compliance opinion, or EU AI Act certification**. The proposed fields distinguish:

- **Textual requirement** — information expressly required by the legislation.
- **Engineering translation** — a record needed, in a multi-step agent system, to make the textual requirement practically demonstrable.
- **Recommended assurance field** — useful evidence that is not itself expressly mandated as a named field.

The AI Omnibus entered into force on **27 July 2026**. As of **1 August 2026**, the relevant amended timetable is:

| Regime | Relevant application or enforcement date | Engineering implication |
|---|---:|---|
| GPAI provider obligations | Applicable since 2 August 2025 | GPAI documentation should already be available from in-scope model providers. |
| Commission/AI Office GPAI enforcement powers | 2 August 2026 | Model documentation, evaluation, incident, and systemic-risk evidence becomes directly enforceable from the following day. |
| Annex III high-risk systems | 2 December 2027 | Stand-alone systems in areas such as employment, education, credit, essential services, law enforcement, migration, and justice receive the extended implementation period. |
| Annex I product-related high-risk systems | 2 August 2028 | Product-integrated systems follow the later date and may also be governed by sector-specific product legislation. |

These dates are confirmed by the enacted Regulation (EU) 2026/1744 and the Commission’s current AI Act implementation pages. citeturn15search1turn20search3turn20search6

The resulting evidence architecture should have three separable layers:

```text
Agent event ledger
    Fine-grained, append-oriented records of observable execution events.

Decision ledger
    One normalized record joining the events, versions, factors, policies,
    human interventions, and outcome that produced a consequential decision.

Explanation packet
    A redacted, affected-person-facing projection of the decision record,
    expressed in clear language and excluding irrelevant or protected material.
```

This separation matters because the AI Act requires automatic logging and deployer-facing information, while Article 86 creates a narrower affected-person explanation right. A regulator, deployer, reviewer, and affected person do not necessarily receive the same view of the same evidence.

### Applicability boundaries

Articles 12–15 are requirements for high-risk AI systems generally. Article 86 is materially narrower: it concerns a person affected by a deployer’s decision that is based on the output of an **Annex III** high-risk system, except systems under Annex III point 2 concerning critical infrastructure, where the decision produces legal or similarly significant effects and is considered by the person to adversely affect health, safety, or fundamental rights. Article 86 also yields where an equivalent explanation right is already provided under other Union law. citeturn6view0turn6view1

Accordingly:

```yaml
article_86_applicability:
  high_risk_basis:
    allowed: ["annex_III"]
    excluded: ["annex_III_point_2"]
    not_automatically_covered: ["annex_I"]
  decision_conditions:
    based_on_ai_output: true
    legal_or_similarly_significant_effect: true
    claimed_adverse_effect_domain:
      - health
      - safety
      - fundamental_rights
  superseded_or_restricted_by_other_law: possible
```

`xai` should support an explanation packet for any decision, but must not label every packet an “Article 86 explanation.” The packet should carry an explicit applicability determination and legal-basis reference.

### No chain-of-thought dependency

Nothing in Articles 12, 13, 14, or 86 expressly requires preservation or disclosure of private chain-of-thought. Article 13 instead refers to information enabling deployers to interpret outputs and, where applicable, the system’s technical capabilities to provide information relevant to explaining those outputs. Article 86 asks for the system’s role and the main elements of the individual decision. citeturn19view3turn6view0

The evidence model should therefore be based on:

```text
observable inputs
retrieved evidence
tool calls and returned facts
policy and rule evaluations
model and component versions
output candidates and selected outputs
human interventions
decision factors
counterfactual tests
known limitations
```

It should not require hidden token-level reasoning, scratchpads, or private model deliberation.

## Automatic logging and traceability

### What Article 12 actually requires

Article 12 requires high-risk systems to be technically capable of automatically recording events over the system’s lifetime. The events must support:

1. identifying situations that may result in the system presenting a risk or constitute a substantial modification;
2. post-market monitoring; and
3. monitoring of operation by deployers under Article 26(5). citeturn4view0turn19view4

The Act does **not** provide a generally applicable, exhaustive list of event types for ordinary agentic systems. It gives a specific minimum list only for certain remote-biometric-identification systems: recording the period of use, reference database, input data that led to a match, and the persons who verified the result. citeturn4view0

Therefore, the following agent-event taxonomy is an **engineering translation** of Article 12’s purposes, not a claim that the Act names each event.

### Required event granularity for an agentic system

The atomic record should be one **policy-relevant or decision-relevant state transition**, rather than one record for an entire conversation or one record for every latent model state.

The “Auditable Agents” framing supports treating tool invocations, external requests, file operations, database queries, approvals, and delegation events as relevant actions, while explicitly distinguishing them from every internal latent state. It also identifies retries, fallbacks, approvals, and delegation handoffs as lifecycle phases that are often lost in conventional traces. citeturn21view4

A defensible minimum taxonomy is:

| Event class | Emit a record when | Required reconstruction value |
|---|---|---|
| `execution.started` / `execution.ended` | An agent run begins or reaches a terminal state | Establishes execution boundary, purpose, initiating principal, and completion status. |
| `decision.started` / `decision.finalized` | Work begins on an individual consequential decision and when the disposition becomes effective | Creates the join point between trace and decision. |
| `model.inference` | A model call produces information subsequently consumed by the agent or decision function | Pins provider, model, version, configuration, input evidence reference, output reference, and uncertainty indicators. |
| `retrieval.query` / `retrieval.result` | Data, documents, memories, or records are requested or returned | Shows which evidence entered the decision and from where. |
| `tool.request` / `tool.result` | A tool, API, database, file system, messaging service, or external system is invoked | Reconstructs parameters, authorization, result, error, and side effects. |
| `external.effect.proposed` / `external.effect.committed` | The agent proposes or performs an action that changes external state | Separates recommendation from irreversible action. |
| `delegation.created` / `delegation.returned` | Responsibility passes between agents, skills, services, or humans | Preserves the causal and responsibility chain. |
| `policy.evaluated` | A rule, guardrail, permission, eligibility criterion, or risk policy is evaluated | Makes post-hoc policy checking possible. |
| `control.blocked` / `control.allowed` | A runtime gate blocks, permits, or modifies an operation | Distinguishes prevented attempts from completed actions. |
| `retry`, `fallback`, `replan` | The system repeats or changes its path after an error, block, or low-confidence result | Prevents a successful final action from concealing earlier blocked or failed paths. |
| `oversight.requested` / `oversight.responded` | A human review is triggered or completed | Supports Article 14 evidence. |
| `override`, `reverse`, `stop` | A human or control component changes or terminates the AI path | Proves intervention authority was technically effective. |
| `anomaly.detected` | Drift, out-of-distribution input, unexpected performance, policy failure, or system malfunction is detected | Supports monitoring and risk investigation. |
| `risk.notification` / `use.suspended` | A deployer or provider identifies a risk and notifies relevant parties or suspends use | Supports Article 26(5) evidence. |
| `incident.opened` / `incident.corrective_action` / `incident.closed` | A harmful or potentially harmful operational event is managed | Connects trace evidence to post-market monitoring. |
| `component.changed` | A model, prompt template, tool, policy, retrieval index, threshold, routing rule, or system configuration changes | Enables substantial-modification and version analysis. |
| `evidence.redacted` / `evidence.deleted` | Content is transformed, restricted, or deleted under the retention policy | Preserves proof of lawful evidence handling without retaining the deleted content. |

Providers’ post-market monitoring must actively and systematically collect, document, and analyse relevant system-performance data throughout the system’s lifetime and, where relevant, interactions with other AI systems. Deployers must monitor operation in accordance with instructions and must inform relevant parties and suspend use without undue delay where they have reason to consider that use may present a risk. citeturn19view2turn19view3

### Agent-event record

```yaml
AgentEvent:
  schema_version: string

  identity:
    event_id: string
    event_type: string
    occurred_at: datetime
    observed_at: datetime
    emitted_at: datetime
    environment: production | staging | test
    jurisdiction_context: [string]

  topology:
    trace_id: string
    span_id: string
    parent_span_id: string | null
    execution_id: string
    decision_id: string | null
    conversation_id: string | null
    attempt_number: integer
    lifecycle_phase:
      enum:
        - intake
        - evidence_collection
        - planning
        - execution
        - verification
        - human_review
        - finalization
        - notification
        - appeal
        - monitoring
    causation_event_ids: [string]
    correlation_ids: [string]

  actor:
    actor_type: user | agent | model | tool | service | reviewer | administrator
    actor_id: string
    principal_id: string | null
    operator_organization_id: string
    delegation_id: string | null
    delegated_scope_ref: string | null
    authority_basis_ref: string | null

  component:
    system_id: string
    system_version: string
    agent_id: string | null
    agent_version: string | null
    model_provider: string | null
    model_id: string | null
    model_version_or_snapshot: string | null
    tool_id: string | null
    tool_version: string | null
    prompt_template_id: string | null
    prompt_template_version: string | null
    policy_bundle_id: string | null
    policy_bundle_version: string | null
    retrieval_index_id: string | null
    retrieval_index_version: string | null

  action:
    operation: string
    intended_purpose: string
    target_type: string | null
    target_ref: string | null
    external_side_effect: boolean
    side_effect_class: none | reversible | compensatable | irreversible
    request_evidence_ref: string | null
    response_evidence_ref: string | null
    request_digest: string | null
    response_digest: string | null
    normalized_parameters: object
    result_status: proposed | allowed | blocked | succeeded | failed | cancelled
    error_code: string | null

  data_lineage:
    input_artifact_refs: [string]
    output_artifact_refs: [string]
    source_system_refs: [string]
    subject_tokens: [string]
    data_categories: [string]
    special_category_indicator: boolean
    provenance_complete: boolean
    redaction_manifest_ref: string | null

  policy:
    policy_refs: [string]
    policy_inputs: object
    verdict: comply | violate | warn | not_applicable | undecidable
    triggered_rules: [string]
    threshold_values: object
    control_action: none | allow | block | transform | escalate
    exception_or_waiver_ref: string | null

  monitoring:
    confidence_or_quality_metrics: object
    expected_operating_range_ref: string | null
    anomaly_flags: [string]
    risk_flags: [string]
    drift_metrics: object
    monitoring_rule_refs: [string]

  integrity:
    canonicalization_method: string
    record_digest: string
    previous_record_digest: string | null
    batch_digest: string | null
    signature: string | null
    signer_ref: string | null
    timestamp_authority_ref: string | null

  privacy:
    content_mode: omitted | derived_only | tokenized | encrypted_reference | inline
    processing_purpose_ref: string
    legal_basis_ref: string | null
    access_class: string
    retention_class: string
    delete_at: datetime | null
    legal_hold_ref: string | null
```

### Completeness and gap records

A record can be faithfully formatted while still omitting entire actions. The “Auditable Agents” framework therefore distinguishes action coverage from record fidelity and recommends explicit phase-entry and phase-exit markers to distinguish “did not occur” from “occurred but was not recorded.” citeturn21view4

Add a run-level coverage record:

```yaml
TraceCoverageRecord:
  execution_id: string
  expected_event_classes: [string]
  observed_event_counts: object
  phase_entry_markers: [string]
  phase_exit_markers: [string]
  missing_phase_markers: [string]
  telemetry_dropped_count: integer
  sampling_applied: boolean
  sampling_rule_ref: string | null
  exporter_failures: [object]
  provider_trace_gaps: [object]
  coverage_assessment:
    action_coverage: number
    lifecycle_coverage: number
    record_fidelity: number
    policy_decidability: number
  assessed_at: datetime
```

For consequential decisions, sampling should not remove decision-relevant events. Sampling metadata must itself be recorded; otherwise, absence of an event cannot be distinguished from telemetry loss.

### Retention expectations

Article 12’s “over the lifetime” language concerns the system’s **logging capability and monitoring coverage**. It does not mean every raw event payload must necessarily be retained for the entire product lifetime.

Providers and deployers must keep automatically generated logs under their control for a period appropriate to the system’s intended purpose and for **at least six months**, unless applicable Union or national law—particularly personal-data law—provides otherwise. citeturn7view0turn7view1turn15search7

A suitable retention model is:

| Evidence class | Engineering retention rule |
|---|---|
| Structured automatic event records supporting a decision | At least six months where Articles 19 or 26(6) apply, unless another applicable law changes the period; extend where sector law, complaints, limitation periods, investigations, or documented risk needs require it. |
| Raw prompt, retrieved document, or tool-response payload | Do not equate with the Article 12 log. Retain only where necessary and for the shortest defensible period; otherwise retain a digest, source reference, extracted decision facts, and redaction manifest. |
| Decision record and oversight disposition | Retain for the applicable operational, sector, challenge, and evidence period determined by legal review; it should not expire before the events needed to interpret it. |
| Model, policy, tool, threshold, and configuration snapshots | Retain or make retrievable for as long as any retained decision refers to them. |
| Integrity anchors, batch digests, and non-personal aggregate monitoring metrics | May be retained longer if they are genuinely non-identifying and serve integrity or lifecycle monitoring purposes. |
| Deletion and redaction records | Retain as non-content metadata sufficient to prove what category was deleted, when, under which rule, and by whom. |

A field-level retention dependency should be enforced:

```yaml
retention_dependency:
  decision_record_expires_at: datetime
  supporting_event_expires_at: ">= decision_record_expires_at"
  referenced_configuration_expires_at: ">= decision_record_expires_at"
  raw_content_expires_at: "independent, necessity-based"
  integrity_anchor_expires_at: ">= max(supporting records)"
```

## Deployer transparency and human oversight

### Deployer information package

Article 13 requires high-risk systems to be sufficiently transparent to enable deployers to interpret outputs and use the system appropriately. Instructions must be concise, complete, correct, clear, relevant, accessible, and comprehensible. citeturn4view0

The deployer-facing package should be a versioned system record rather than a static prose manual:

```yaml
DeployerInformationPackage:
  package_id: string
  package_version: string
  effective_from: datetime
  provider:
    legal_name: string
    contact: string
    system_identifier: string

  intended_use:
    intended_purpose: string
    covered_decision_types: [string]
    intended_users: [string]
    intended_subject_populations: [string]
    prohibited_uses: [string]
    reasonably_foreseeable_misuses: [string]
    operating_environment_assumptions: [string]

  capabilities_and_limits:
    supported_tasks: [string]
    autonomous_capabilities: [string]
    tool_and_external_action_capabilities: [string]
    known_limitations: [string]
    known_failure_modes: [string]
    out_of_scope_inputs: [string]
    expected_lifetime: string
    maintenance_and_update_requirements: [string]

  performance:
    accuracy_metrics:
      - metric_name: string
        value_or_range: number | string
        test_population: string
        test_date: date
        version: string
    robustness_metrics: [object]
    cybersecurity_characteristics: [object]
    group_specific_performance: [object]
    known_conditions_affecting_performance: [string]
    uncertainty_interpretation: string

  data_requirements:
    input_specifications: [object]
    data_quality_requirements: [string]
    representativeness_requirements: [string]
    relevant_training_data_information: [object]
    relevant_validation_data_information: [object]
    relevant_testing_data_information: [object]

  output_interpretation:
    output_types: [string]
    score_or_label_semantics: [object]
    threshold_meanings: [object]
    explanation_capabilities: [string]
    warnings_and_uncertainty_indicators: [string]
    conditions_requiring_disregard: [string]

  agentic_architecture:
    model_inventory: [object]
    tool_inventory: [object]
    delegation_topology: [object]
    memory_and_retrieval_components: [object]
    external_dependencies: [object]
    maximum_autonomy_boundary: string
    irreversible_action_controls: [object]

  human_oversight:
    required_oversight_roles: [string]
    qualification_requirements: [string]
    escalation_triggers: [object]
    information_to_show: [string]
    available_interventions: [string]
    stop_procedure: string
    override_and_reversal_procedure: string
    automation_bias_warning: string

  logging:
    generated_event_types: [string]
    log_access_method: string
    log_interpretation_guide: string
    storage_and_export_format: [string]
    clock_and_identifier_semantics: string
    known_observability_gaps: [string]

  changes:
    predetermined_changes: [object]
    change_notification_process: string
    compatibility_policy: string
```

This reflects Article 13’s express categories: intended purpose; accuracy, robustness, and cybersecurity; foreseeable risks and misuse; explanation capabilities; performance for relevant persons or groups; input and dataset information; output interpretation; predetermined changes; human-oversight measures; computational and hardware requirements; expected lifetime and maintenance; and mechanisms for collecting, storing, and interpreting logs. citeturn19view3turn4view1

For an agent, “system capabilities” should explicitly include which tools it can invoke, which external effects it can cause, whether it may delegate, and which actions require confirmation. Otherwise a deployer cannot realistically understand the system’s autonomy boundary.

### Human-oversight design requirements

Article 14 requires effective human oversight appropriate to the system’s risks, level of autonomy, and context. The system and associated measures must enable the overseer, as appropriate, to:

- understand the system’s capabilities and limitations;
- monitor its operation and detect anomalies, dysfunctions, and unexpected performance;
- remain aware of automation bias;
- interpret outputs correctly;
- decide not to use the system or disregard, override, or reverse its output; and
- intervene or stop the system safely. citeturn4view1turn4view2

Deployers must assign oversight to people with the necessary competence, training, authority, and support. citeturn19view1

A system that displays a warning but gives the reviewer no time, evidence, authority, or effective stop mechanism should not be treated by the template as having demonstrated effective oversight.

### Oversight-event record

Article 14 does not literally enumerate fields such as “response time” or “final disposition.” Capturing them is an engineering method of demonstrating that oversight was available and effective.

```yaml
HumanOversightRecord:
  oversight_id: string
  decision_id: string
  execution_id: string
  trigger_event_id: string

  trigger:
    trigger_type:
      enum:
        - mandatory_pre_action_review
        - low_confidence
        - policy_exception
        - high_impact_action
        - anomaly
        - conflicting_evidence
        - out_of_distribution
        - user_request
        - random_quality_sample
        - appeal
        - incident
    trigger_rule_ref: string
    measured_value: number | string | null
    threshold: number | string | null
    triggered_at: datetime
    urgency_class: string
    response_deadline: datetime | null

  reviewer_assignment:
    reviewer_ref: string
    organization_ref: string
    role: string
    competence_profile_ref: string
    training_status_ref: string
    authorization_scope_ref: string
    conflict_of_interest_check: pass | fail | not_applicable
    assigned_at: datetime
    accepted_at: datetime | null

  information_presented:
    interface_version: string
    presentation_timestamp: datetime
    decision_summary_ref: string
    proposed_outcome: object
    decisive_factor_refs: [string]
    source_evidence_refs: [string]
    uncertainty_and_quality_metrics: object
    known_limitations: [string]
    policy_results: [object]
    alternative_options: [object]
    prior_agent_steps_ref: string
    omitted_information: [object]
    display_snapshot_digest: string
    automation_bias_notice_shown: boolean

  authority_available:
    can_approve: boolean
    can_reject: boolean
    can_modify: boolean
    can_disregard_output: boolean
    can_override: boolean
    can_reverse: boolean
    can_stop_execution: boolean
    can_suspend_system: boolean
    can_request_more_information: boolean
    can_escalate: boolean

  reviewer_action:
    action:
      enum:
        - approve
        - reject
        - modify
        - disregard
        - override
        - reverse
        - stop
        - suspend
        - request_more_information
        - escalate
        - abstain
    action_at: datetime
    target_event_or_output_ref: string
    reason_codes: [string]
    reviewer_statement: string | null
    additional_evidence_refs: [string]
    authority_exercised: string

  timing:
    queue_latency_ms: integer
    review_duration_ms: integer
    trigger_to_action_ms: integer
    deadline_met: boolean | null

  final_disposition:
    outcome: object
    effective_at: datetime
    ai_output_adopted:
      enum: [fully, partly, no, not_applicable]
    differences_from_ai_proposal: [object]
    downstream_action_refs: [string]
    subject_notified_at: datetime | null
    follow_up_required: boolean
    follow_up_ref: string | null

  integrity:
    record_digest: string
    signature: string | null
```

The `information_presented` block is essential. Merely recording that “a human approved” does not demonstrate that the reviewer had adequate information to interpret and challenge the output.

### Agent escalation semantics

For agentic systems, escalation should be a first-class lifecycle transition:

```yaml
EscalationStateMachine:
  states:
    - autonomous_processing
    - review_required
    - review_queued
    - review_in_progress
    - additional_evidence_requested
    - approved
    - modified
    - rejected
    - stopped
    - suspended
    - expired_without_review
  required_transition_fields:
    - source_state
    - destination_state
    - timestamp
    - initiating_actor
    - trigger_or_reason
    - evidence_available
    - authority_used
```

An expired or unanswered review must have an explicit fail-safe disposition. Silence should not be encoded as implicit approval unless the applicable risk design and legal review expressly permit it.

For certain biometric-identification systems, Article 14 separately requires verification by at least two appropriately competent, trained, and authorised people, subject to limited exceptions. This is not a general two-reviewer requirement for all high-risk systems. citeturn4view2

## Individual explanation packet

### Article 86 target

Where Article 86 applies, the deployer must provide a clear and meaningful explanation of:

1. **the role of the AI system in the decision-making procedure; and**
2. **the main elements of the decision taken.** citeturn6view0

Recital 171 describes the relevant situation as one in which a decision is based mainly on the output of an Annex III high-risk system and indicates that the explanation should provide a basis from which the affected person can exercise their rights. citeturn6view1

A raw OpenTelemetry trace, list of tokens, generic model card, or global feature-importance chart would not by itself satisfy the engineering objective. The packet must be specific to the individual decision and intelligible without access to the internal production system.

### Affected-person schema

```yaml
ExplanationPacket:
  schema_version: string
  packet_id: string
  generated_at: datetime
  language: string
  format: markdown | json | html
  accessibility_profile: string

  applicability:
    asserted_basis:
      enum:
        - EU_AI_Act_Article_86
        - GDPR
        - sector_law
        - organizational_policy
        - voluntary
    article_86_status:
      enum:
        - applies
        - does_not_apply
        - uncertain
        - superseded_by_other_union_right
    high_risk_classification_ref: string
    annex_III_category: string | null
    annex_III_point_2_exclusion: boolean
    significant_effect_basis: string | null
    determination_owner: string

  parties:
    affected_person_reference: string
    deployer_name: string
    deployer_contact: string
    decision_owner_role: string
    review_or_appeal_contact: string | null

  decision:
    decision_id: string
    decision_date: datetime
    decision_type: string
    final_outcome_plain_language: string
    effective_consequence: string
    legal_or_similarly_significant_effect: string | null

  ai_role:
    system_name: string
    system_version: string
    role_type:
      enum:
        - information_retrieval
        - evidence_extraction
        - scoring
        - ranking
        - classification
        - recommendation
        - eligibility_determination
        - action_selection
        - action_execution
        - mixed
    role_description_plain_language: string
    degree_of_reliance:
      enum:
        - sole_basis
        - predominant_basis
        - material_input
        - supporting_input
        - no_material_role
    stages_where_used: [string]
    human_involvement:
      reviewer_role: string | null
      review_stage: string | null
      authority_available: [string]
      action_taken: string | null
      ai_output_changed: boolean | null

  main_elements:
    decisive_factors:
      - factor_id: string
        plain_language_name: string
        value_or_category_used: string
        source_description: string
        source_date: date | null
        direction_of_effect:
          enum: [favored, disfavored, neutral, mixed]
        materiality:
          enum: [decisive, major, supporting]
        quality_or_uncertainty_note: string | null
        contested_by_person: boolean | null
    rules_and_thresholds:
      - plain_language_rule: string
        policy_or_rule_ref: string
        threshold_or_condition: string | null
        result: string
    evidence_timeline:
      - timestamp: datetime
        event_description: string
        actor_type: string
        evidence_ref: string | null
    interaction_effects:
      - description: string
        involved_factor_ids: [string]
    excluded_or_non_decisive_information:
      - description: string
        why_not_used: string

  counterfactuals:
    status:
      enum:
        - tested
        - not_tested_not_reliable
        - not_applicable
    tests:
      - changed_factor: string
        original_value: string
        alternative_value_or_range: string
        other_factors_held_constant: [string]
        resulting_outcome: string
        stability_note: string
        test_method_ref: string
    warning: string

  limitations:
    known_system_limitations: [string]
    data_quality_limitations: [string]
    observability_gaps: [string]
    uncertainty_statement: string
    explanation_method_limitations: [string]
    information_withheld:
      - category: string
        reason: string
        effect_on_explanation: string

  correction_and_review:
    how_to_correct_input_data: string | null
    how_to_submit_additional_evidence: string | null
    how_to_request_human_review: string | null
    how_to_contest_decision: string | null
    review_deadline: datetime | null
    available_contact_methods: [string]
    complaint_or_regulator_information: string | null

  provenance:
    decision_record_digest: string
    supporting_event_range: object
    model_snapshot_ref: string
    policy_snapshot_ref: string
    explanation_generator_version: string
    human_validation_status: string
```

### What “main elements” should mean in the template

The legal text does not prescribe a particular explanation technique. For engineering purposes, “main elements” should be represented as the smallest set of observable factors, rules, interactions, and human interventions needed to understand why this outcome occurred.

Every listed factor should answer:

```text
What information was used?
Where did it come from?
Was it accepted as accurate?
How did it affect the decision?
Was it decisive or merely supporting?
Which rule or threshold made it relevant?
Did a human adopt, change, or reject the AI-derived result?
```

A field should not be presented as “decisive” merely because a global attribution method assigned it a high weight. The factor must be connected to the actual decision path, applicable policy, and outcome.

### Counterfactual evidence

Article 86 does not expressly require counterfactual testing. It is nevertheless a strong **recommended assurance field** because a validated counterfactual can make the role of a main element understandable:

```yaml
counterfactual_example:
  statement: >
    The income-verification discrepancy was a major factor.
    When the discrepancy flag was removed in the recorded decision configuration,
    while the other recorded factors were held constant, the case moved from
    automatic rejection to mandatory human review.
  limitations:
    - This test describes the recorded system version.
    - It does not guarantee the outcome of a new application.
    - Stochastic components were tested across a documented evaluation batch.
```

Counterfactuals must not imply exact causal certainty when the system is stochastic, when inputs interact, or when a human retains discretion. The packet should report the test method, held-constant assumptions, version, repetitions, and stability.

### Review and appeal metadata

Article 86 itself is an explanation right, not a complete universal appeal procedure. Review, contestation, rectification, and complaint rights may arise from GDPR, sector law, national law, contractual arrangements, or deployer policy. The template should carry those routes without mislabeling their source.

Where GDPR Article 22 applies, safeguards include at least the right to obtain human intervention, express a point of view, and contest the decision in the contract- or consent-based exceptions. GDPR Article 15 may also require meaningful information about automated-decision logic, significance, and envisaged consequences. citeturn18view2turn18view3

### Information that should not appear

The affected-person packet should not ordinarily contain:

```text
private chain-of-thought
unrelated personal data about other people
credentials, secrets, or security-sensitive control details
entire retrieved documents where only one fact was relevant
raw internal reviewer notes unrelated to the decision basis
generic feature importance unrelated to this individual decision
unsupported causal claims
trade-secret material where a meaningful, lawful abstraction is available
```

Omissions must be described sufficiently to show whether they limit the explanation. “Confidential” should not be used as an unexplained blanket placeholder.

## GPAI supply-chain evidence

### GPAI provider duties relevant to a high-risk system

A GPAI model and the downstream agentic AI system integrating it occupy different levels of the supply chain.

GPAI providers must maintain technical documentation covering training, testing, and evaluation and make it available to the AI Office and competent authorities. They must also supply downstream system providers with information sufficient to understand the model’s capabilities and limitations and to support downstream AI Act obligations. They must maintain an EU-copyright policy and publish a sufficiently detailed training-content summary using the AI Office template. citeturn22view2

Annex XII requires downstream information including intended tasks and integration types, acceptable-use policies, release and distribution methods, hardware and software interactions, software versions, architecture and parameters, input/output modalities and formats, licensing, integration means, maximum input sizes or context windows, and training/testing/validation data type, provenance, and curation information. citeturn22view4

The GPAI record ingested by `xai` should therefore be:

```yaml
ModelSupplyChainRecord:
  record_id: string
  captured_at: datetime

  provider:
    provider_name: string
    provider_contact: string
    provider_role_assertion: string
    EU_representative_ref: string | null

  model:
    model_id: string
    model_family: string
    exact_version_or_snapshot: string
    release_date: date
    distribution_method: string
    license: string
    open_source_status: string
    systemic_risk_status:
      enum: [designated, presumed, not_designated, unknown]

  intended_integration:
    intended_tasks: [string]
    integration_types: [string]
    acceptable_use_policy_ref: string
    prohibited_use_refs: [string]
    relevant_system_categories: [string]

  technical_characteristics:
    architecture_description_ref: string | null
    parameter_count_or_class: string | null
    input_modalities: [string]
    output_modalities: [string]
    input_formats: [string]
    output_formats: [string]
    context_window_or_max_input: string
    relevant_software_versions: [object]
    hardware_requirements: [object]
    tool_calling_characteristics: [object]

  data_information:
    training_data_types: [string]
    training_data_provenance_summary_ref: string
    curation_method_summary_ref: string
    testing_data_summary_ref: string
    validation_data_summary_ref: string
    public_training_content_summary_ref: string
    copyright_policy_ref: string

  evaluation:
    evaluation_report_refs: [string]
    capabilities: [object]
    limitations: [object]
    known_failure_modes: [object]
    adversarial_test_refs: [string]
    safety_evaluation_refs: [string]
    relevant_group_performance_refs: [string]
    benchmark_applicability_notes: [string]

  lifecycle:
    update_policy_ref: string
    deprecation_policy_ref: string
    known_incident_feed_ref: string
    version_change_history: [object]
    documentation_last_checked_at: datetime

  documentary_integrity:
    source_document_refs: [string]
    source_document_digests: [string]
    source_effective_dates: [date]
    code_of_practice_claim: string | null
    harmonised_standard_claim: string | null
```

For every decision, the ledger should pin the actual model reference used:

```yaml
DecisionModelBinding:
  decision_id: string
  provider_model_id: string
  provider_reported_version: string
  observed_endpoint_or_deployment_id: string
  deployment_configuration_digest: string
  adapter_or_fine_tune_ref: string | null
  system_prompt_template_version: string
  retrieval_configuration_version: string
  routing_policy_version: string
  provider_documentation_snapshot_digest: string
```

A model-family name such as “Model X” is insufficient where the hosted provider may update behavior behind an endpoint. The evidence record should distinguish provider-reported version, deployer-observed endpoint, local adapter or fine-tune, system configuration, and documentation snapshot.

### Open-source GPAI exception

For qualifying freely and openly licensed GPAI models with publicly available weights, architecture information, and usage information, the Article 53(1)(a) and (b) documentation obligations are subject to an exception. That exception does not apply to GPAI models with systemic risk, and it does not eliminate the copyright-policy or public training-summary duties. citeturn22view2

The ledger should never infer that “open source” means “all GPAI duties are inapplicable”:

```yaml
open_source_exception_assessment:
  license_allows_access_use_modification_distribution: boolean
  weights_publicly_available: boolean
  architecture_information_public: boolean
  usage_information_public: boolean
  systemic_risk_model: boolean
  exempted_duties:
    article_53_1_a: boolean
    article_53_1_b: boolean
  duties_not_exempted:
    copyright_policy: true
    training_content_summary: true
```

### Systemic-risk GPAI evidence

Providers of GPAI models with systemic risk have additional obligations involving model evaluation, documented adversarial testing, systemic-risk assessment and mitigation, serious-incident tracking and reporting with corrective measures, and adequate cybersecurity protection. citeturn9view1

A downstream high-risk system should not copy all provider evidence into every decision packet. It should retain:

```yaml
SystemicRiskDependencyRecord:
  model_record_ref: string
  relevant_risk_categories: [string]
  provider_evaluation_refs: [string]
  relevant_mitigations: [object]
  integration_assumptions: [string]
  deployer_controls_compensating_for_model_limits: [object]
  known_incidents_relevant_to_deployment: [object]
  provider_corrective_action_status: [object]
  last_reviewed_at: datetime
```

### Interaction with high-risk-system evidence

GPAI documentation is **supply-chain baseline evidence**, not a substitute for deployment evidence.

It can support:

```text
model identity and intended capabilities
known limitations
integration requirements
input/output constraints
training and evaluation provenance
known incidents and systemic risks
acceptable-use restrictions
version and update management
```

It ordinarily cannot prove:

```text
which data was used in a particular decision
which tools the agent invoked
which policy checks ran
whether a reviewer saw adequate information
whether an output was overridden
why a specific consequential outcome became effective
```

Those facts must come from the downstream system and deployer ledger.

Where a high-risk provider depends on a third-party model, tool, or component, the AI Act anticipates written arrangements specifying the information, capabilities, technical access, and assistance needed for the high-risk provider to comply. citeturn7view0

A procurement-ready evidence profile should include:

```yaml
ThirdPartyEvidenceContractProfile:
  component_id: string
  supplier_id: string
  required_version_identifier: boolean
  required_change_notifications: boolean
  required_capability_and_limitation_docs: boolean
  required_incident_notifications: boolean
  required_log_access_or_export: boolean
  required_evaluation_evidence: boolean
  required_retention_support: boolean
  required_regulatory_assistance: boolean
  evidence_delivery_SLA: string
  termination_and_deprecation_support: string
```

The GPAI Code of Practice may be used to demonstrate compliance pending harmonised standards, but it should be recorded as a provider claim and documentary input rather than treated by `xai` as certification. Harmonised standards can create a presumption of conformity only to the extent that they cover the relevant obligations and are referenced through the applicable EU standardisation process. citeturn22view2turn20search14

## GDPR-aware redaction and retention

### Core design constraint

AI Act logging does not displace GDPR. GDPR requires purpose limitation, data minimisation, storage limitation, integrity and confidentiality, and accountability. Personal data must be adequate, relevant, and limited to what is necessary, and identifiable data must not be kept longer than necessary for the processing purpose. citeturn17view0turn17view1turn17view2

GDPR Article 25 requires data-protection safeguards, including effective minimisation and measures such as pseudonymisation, to be integrated by design and default. Article 32 requires security appropriate to risk, including, where appropriate, pseudonymisation, encryption, resilience, and regular testing of security measures. citeturn16view2turn18view0

The correct engineering question is therefore not:

> “How can we save every prompt in case an auditor asks?”

It is:

> “What is the minimum structured evidence that allows the relevant action, decision, policy result, and human intervention to be reconstructed, while retaining raw personal content only where that content is demonstrably necessary?”

### Redaction-aware evidence envelope

```yaml
EvidenceArtifact:
  artifact_id: string
  artifact_type:
    enum:
      - prompt
      - message
      - retrieved_document
      - database_result
      - tool_request
      - tool_response
      - model_output
      - reviewer_input
      - decision_factor
      - attachment
      - external_record

  provenance:
    source_type: string
    source_system_ref: string
    source_record_ref: string | null
    collected_at: datetime
    effective_date: date | null
    generated_by_event_id: string | null

  decision_relevance:
    decision_id: string | null
    relevance:
      enum: [decisive, supporting, context_only, rejected, irrelevant]
    relevance_reason_code: string
    factor_refs: [string]
    used_by_event_ids: [string]

  personal_data:
    contains_personal_data: boolean
    data_subject_tokens: [string]
    personal_data_categories: [string]
    special_category_indicator: boolean
    criminal_data_indicator: boolean
    third_party_data_indicator: boolean
    child_data_indicator: boolean

  processing:
    purpose_ref: string
    legal_basis_ref: string | null
    necessity_justification: string
    controller_ref: string
    processor_refs: [string]
    transfer_or_residency_ref: string | null

  representation:
    content_mode:
      enum:
        - omitted
        - structured_facts_only
        - irreversible_aggregate
        - pseudonymized
        - encrypted_vault_reference
        - inline_redacted
        - inline_full
    normalized_facts: [object]
    content_digest: string | null
    encrypted_content_ref: string | null
    encryption_key_ref: string | null
    content_length: integer | null

  redaction:
    redaction_applied: boolean
    redaction_policy_ref: string
    redacted_categories: [string]
    redaction_operations:
      - field_or_range_ref: string
        transformation:
          enum:
            - remove
            - mask
            - tokenize
            - generalize
            - truncate
            - replace_with_category
        reason: string
    redacted_digest: string | null
    redaction_quality_status: string

  access:
    access_class: string
    authorized_roles: [string]
    disclosure_constraints: [string]
    access_log_ref: string

  retention:
    retention_class: string
    retention_purpose: string
    retain_until: datetime
    review_at: datetime | null
    legal_hold_ref: string | null
    deletion_method: string
    deletion_event_id: string | null

  integrity:
    artifact_digest: string
    signature: string | null
```

### What to retain by default

A minimised decision record should preferentially retain:

| Evidence | Preferred representation |
|---|---|
| Identity of the data source | Stable source-system and source-record references, with access controls. |
| Fact actually used in the decision | Normalized fact, category, date, provenance, and quality status. |
| Relevant section of a document | A narrowly scoped excerpt or structured extraction, not the entire document, where the excerpt itself is necessary. |
| Prompt or tool request | Template/version, normalized parameters, purpose, digest, and relevant structured facts. |
| Model response | Selected output, relevant alternative output metadata, uncertainty, digest, and model binding. |
| Policy evaluation | Policy/version, input facts, threshold, result, and control action. |
| Human review | What the reviewer was shown, available authority, action, timing, and disposition. |
| Full source content needed for dispute resolution | Encrypted, separately controlled vault reference with its own shorter review and deletion schedule. |
| Deleted content | Deletion event, category, policy basis, date, and prior digest—not a recoverable copy. |

### What not to retain by default

```text
entire chat histories unrelated to the decision
every retrieval result rather than the items actually consumed
full database rows where only one field was relevant
API credentials, bearer tokens, cookies, or connection strings
hidden model scratchpads or chain-of-thought
unrelated personal information about colleagues or family members
special-category data merely because it appeared in a prompt
unredacted attachments where extracted facts suffice
duplicate copies of the same personal payload in multiple telemetry systems
raw reviewer screen recordings where a display manifest is sufficient
```

A content digest should not automatically be treated as anonymous. Where a digest can be matched against known or low-entropy values, or where a person remains linkable through surrounding identifiers, it remains at least pseudonymous evidence. GDPR defines pseudonymisation as requiring separately held additional information and technical and organisational controls; it does not equate pseudonymisation with removal from GDPR’s scope. citeturn17view0

### Two-tier content model

```yaml
evidence_storage_tiers:
  structured_ledger:
    contains:
      - event metadata
      - normalized decision factors
      - provenance
      - policy results
      - versions
      - digests
      - redaction manifests
      - oversight actions
    retention:
      basis: AI_Act_plus_sector_and_dispute_requirements

  restricted_content_vault:
    contains:
      - narrowly justified raw prompts
      - necessary document excerpts
      - necessary tool payloads
      - attachments required for review
    controls:
      - separate encryption keys
      - stronger role restrictions
      - purpose-bound access
      - access logging
      - shorter default TTL
      - periodic necessity review
```

The explanation packet should normally be generated from the structured ledger. Access to the raw-content vault should be exceptional and purpose-bound.

### Retention decision record

```yaml
RetentionDecision:
  evidence_class: string
  processing_purpose: string
  AI_Act_log_status: in_scope | out_of_scope | uncertain
  minimum_period_basis: string | null
  sector_law_basis: string | null
  GDPR_necessity_assessment: string
  complaint_or_claim_period_basis: string | null
  chosen_period: string
  identifiable_period: string
  pseudonymized_period: string | null
  aggregation_or_anonymization_at: datetime | null
  deletion_at: datetime
  periodic_review_frequency: string
  approvers:
    - system_owner
    - legal_or_compliance_owner
    - privacy_owner
  last_reviewed_at: datetime
```

The six-month AI Act floor should not be blindly copied to every artifact. It applies to automatically generated logs under the provider’s or deployer’s control, subject to other applicable law. It does not create a general instruction to retain all raw context for six months. citeturn15search7

### DPIA and significant decisions

A GDPR data-protection impact assessment is required where processing using new technologies is likely to result in high risk to people’s rights and freedoms. GDPR specifically identifies systematic and extensive automated evaluation of personal aspects on which legally or similarly significantly affecting decisions are based. The DPIA must assess processing purposes, necessity and proportionality, risks, and safeguards. citeturn18view1

The evidence profile should therefore link to, but not duplicate, the DPIA:

```yaml
PrivacyGovernanceBinding:
  DPIA_ref: string | null
  DPIA_version: string | null
  covered_processing_activity_ref: string
  approved_data_categories: [string]
  prohibited_data_categories: [string]
  approved_retention_classes: [string]
  approved_recipients: [string]
  international_transfer_controls_ref: string | null
  residual_risk_status: string
  last_material_change_review: date
```

Changes to model, tool access, purpose, subject population, data sources, autonomy, or retention should trigger an assessment of whether the existing DPIA and AI risk-management evidence remain valid.

## Standards assessment and proposed minimum

### AAS-1 assessment

AAS-1 v0.1 was published in May 2026 as a draft for public comment. It describes a per-action Class A record with an event ID, agent and principal references, action type and hashes, tool and model information, policy references and results, timestamping, and a signature. It also describes batch, continuous-stream, determination, and engagement classes. citeturn21view0turn21view1

Its twelve assertions include existence, completeness, accuracy, authorisation, cutoff, classification, presentation, identity, provenance, reproducibility, policy compliance, and separation of agent action from operator override. Its verification procedures include hash-chain traversal, Merkle-root recomputation, count reconciliation, identity and signature validation, timestamp checking, and source-data digest checks. citeturn21view2

#### Elements worth adopting

```yaml
AAS1_elements_to_adopt:
  - one portable record per consequential or policy-relevant action
  - actor and principal separation
  - explicit model and tool provenance
  - policy references and policy verdict
  - input and output digests
  - canonical serialization
  - append-oriented sequencing
  - optional hash chaining
  - optional batch digest or Merkle commitment
  - signatures or attestations at trust boundaries
  - independent verification procedures
  - explicit completeness and authorisation assertions
  - separation of agent action from human override
```

These align well with Article 12 traceability and Article 14 oversight evidence.

#### Elements to adapt rather than hard-code

```yaml
AAS1_elements_to_adapt:
  identity:
    AAS1: AIS-1_DID
    proposed_xai: pluggable_actor_identifier
    rationale: >
      Support DIDs, workload identities, cloud service identities,
      employee directory references, certificates, and local pseudonymous IDs.

  event_identifier:
    AAS1: ULID
    proposed_xai: opaque_unique_id_plus_trace_span_ids
    rationale: >
      Preserve interoperability with OpenTelemetry and OpenInference;
      do not make one ID format mandatory.

  reproducibility:
    AAS1: sufficient_state_for_re_derivation
    proposed_xai:
      - versioned_replay_envelope
      - deterministic_components_identified
      - stochastic_parameters_recorded
      - replay_limitations_declared
      - counterfactual_stability_reported
    rationale: >
      Exact output reproduction may be impossible for hosted,
      updated, stochastic, or externally stateful components.

  prompt_context:
    AAS1: provenance_field
    proposed_xai:
      - prompt_template_version
      - normalized_relevant_inputs
      - digest
      - encrypted_content_reference_when_necessary
      - redaction_manifest
    rationale: >
      Provenance must not become an instruction to retain every raw prompt.

  integrity:
    AAS1: signatures_and_hashes
    proposed_xai: risk_tiered_integrity_profile
    rationale: >
      Local append-only storage, hash-chained batches, or signed records
      may be selected according to threat model and verification needs.
```

#### Limitations as a regulatory input

AAS-1 should not be represented as an EU harmonised standard or as creating a presumption of conformity. The public material labels v0.1 a draft, and its roadmap states that v0.1 includes the Class A JSON Schema while schemas for Classes B, C, D, and E are planned for v0.2. citeturn21view2

Its assertions are useful assurance criteria, but labels such as “audit-grade” are claims of the draft standard rather than EU regulatory findings. Only applicable harmonised standards referenced through the EU framework can provide the relevant presumption of conformity to the extent of their coverage. citeturn20search14

### “Auditable Agents” assessment

The “Auditable Agents” paper proposes five dimensions:

| Dimension | Direct schema consequence |
|---|---|
| Action recoverability | Record policy-relevant actions and enough normalized parameters/results to reconstruct them. |
| Lifecycle coverage | Record starts, ends, retries, fallbacks, approvals, delegations, errors, and gaps as explicit phases. |
| Policy checkability | Record policy version, required inputs, verdict, control action, and an `undecidable` outcome when evidence is missing. |
| Responsibility attribution | Record principal, initiating actor, executing agent, delegated agent or skill, tool, service, and human intervention chain. |
| Evidence integrity | Provide append-only controls, hash chaining, signatures, or equivalent integrity mechanisms according to the threat model. |

The paper treats evidence integrity on an ordinal scale from no protection, through append-only and hash-chained records, to signed records. It also emphasizes that a single omitted field can make an entire policy mechanically undecidable. citeturn22view0

Privacy is treated as a constraint on how evidence is collected, retained, and redacted, rather than as an excuse to omit auditability design altogether. citeturn22view1

This is a particularly useful framing for `xai`: the schema should be evaluated not by the number of spans it ingests, but by whether it can answer five questions:

```text
What happened?
In what lifecycle context did it happen?
Can the relevant policy be checked?
Who or what was responsible?
Can the evidence be trusted?
```

The paper is a research framing, not a legal standard, conformity route, or certification mechanism. Its metrics should be exposed as diagnostic coverage indicators rather than regulatory pass/fail labels.

### Proposed minimal decision ledger

The following is the smallest practical field set that should be treated as the `xai` baseline for a consequential high-risk agent decision. “Minimal” means minimal across the legal purposes discussed here, not minimal telemetry volume.

```yaml
DecisionLedgerRecord:
  schema:
    name: xai.decision-ledger
    version: string

  decision_identity:
    decision_id: string
    decision_type: string
    started_at: datetime
    finalized_at: datetime
    effective_at: datetime | null
    status:
      enum:
        - proposed
        - pending_human_review
        - finalized
        - reversed
        - withdrawn
        - suspended
    deployer_id: string
    provider_id: string
    jurisdiction_context: [string]

  regulatory_scope:
    high_risk_status: in_scope | out_of_scope | uncertain
    classification_basis_ref: string
    annex_category: string | null
    article_86_status: applies | does_not_apply | uncertain
    GDPR_automated_decision_status: string
    sector_law_refs: [string]

  execution_binding:
    execution_ids: [string]
    trace_ids: [string]
    relevant_event_ids: [string]
    trace_start_at: datetime
    trace_end_at: datetime
    trace_coverage_ref: string
    known_trace_gaps: [string]

  system_snapshot:
    high_risk_system_id: string
    high_risk_system_version: string
    model_bindings:
      - provider: string
        model_id: string
        model_version_or_snapshot: string
        endpoint_or_deployment_id: string
        adapter_or_fine_tune_ref: string | null
        documentation_snapshot_digest: string
    agent_versions: [object]
    tool_versions: [object]
    prompt_template_versions: [object]
    policy_bundle_version: string
    threshold_configuration_digest: string
    retrieval_index_versions: [object]
    runtime_configuration_digest: string

  subject_and_purpose:
    subject_token: string
    intended_purpose: string
    processing_purpose_ref: string
    input_data_categories: [string]
    special_category_indicator: boolean
    subject_notification_ref: string | null

  evidence_used:
    artifacts:
      - artifact_id: string
        source_ref: string
        normalized_fact: object
        effective_date: date | null
        quality_status: string
        relevance: decisive | supporting | rejected
        digest: string
        content_mode: string
        redaction_manifest_ref: string | null

  agent_actions:
    policy_relevant_event_refs: [string]
    retrieval_event_refs: [string]
    model_inference_event_refs: [string]
    tool_call_event_refs: [string]
    external_effect_event_refs: [string]
    delegation_event_refs: [string]
    retry_and_fallback_event_refs: [string]
    blocked_attempt_event_refs: [string]

  policy_evaluations:
    - policy_id: string
      policy_version: string
      inputs: object
      threshold_or_condition: object
      verdict: comply | violate | warn | not_applicable | undecidable
      control_action: allow | block | transform | escalate | none
      event_ref: string

  attribution:
    decisive_factors:
      - factor_id: string
        name: string
        source_artifact_refs: [string]
        value_used: string
        direction: favored | disfavored | neutral | mixed
        materiality: decisive | major | supporting
        linked_policy_refs: [string]
        evidence_event_refs: [string]
        uncertainty: string | null
    factor_interactions: [object]
    attribution_method_ref: string
    attribution_limitations: [string]

  counterfactual_tests:
    - test_id: string
      factor_changed: string
      original_value: string
      alternative_value: string
      held_constant: [string]
      resulting_outcome: string
      repetitions: integer | null
      stability_result: string
      system_snapshot_digest: string
      limitations: [string]

  human_oversight:
    required: boolean
    oversight_record_refs: [string]
    trigger: string | null
    reviewer_role: string | null
    information_display_digest: string | null
    response_time_ms: integer | null
    authority_available: [string]
    action_taken: string | null
    AI_output_adopted: fully | partly | no | not_applicable
    final_disposition_owner: string

  outcome:
    AI_proposed_outcome: object
    final_outcome: object
    differences_from_AI_proposal: [object]
    legal_or_similarly_significant_effect: string | null
    downstream_effect_event_refs: [string]
    notification_at: datetime | null

  monitoring_and_risk:
    anomaly_flags: [string]
    out_of_distribution_flags: [string]
    known_limitation_refs: [string]
    risk_event_refs: [string]
    incident_ref: string | null
    suspension_or_corrective_action_refs: [string]

  review_and_appeal:
    review_available: boolean
    review_channel_ref: string | null
    appeal_or_contest_channel_ref: string | null
    correction_channel_ref: string | null
    request_received_at: datetime | null
    review_status: string | null
    final_review_disposition_ref: string | null

  privacy_and_retention:
    data_minimisation_profile_ref: string
    DPIA_ref: string | null
    raw_content_vault_refs: [string]
    redaction_manifest_refs: [string]
    retention_class: string
    retain_until: datetime
    legal_hold_ref: string | null
    deletion_event_ref: string | null

  integrity:
    canonicalization_method: string
    record_digest: string
    supporting_event_batch_digest: string
    previous_decision_digest: string | null
    signature: string | null
    signer_ref: string | null
```

### Proposed minimal explanation packet

The affected-person view should be generated as a projection, not by disclosing the full decision ledger:

```yaml
MinimalExplanationPacket:
  packet_id: string
  decision_id: string
  decision_date: datetime
  deployer_name: string
  deployer_contact: string

  applicability:
    explanation_basis: string
    article_86_status: string

  outcome:
    plain_language_decision: string
    practical_effect: string

  AI_role:
    system_name: string
    role_in_procedure: string
    degree_of_reliance: string
    stages_used: [string]

  human_role:
    review_occurred: boolean
    reviewer_role: string | null
    reviewer_authority: [string]
    reviewer_action: string | null
    AI_result_changed: boolean | null

  main_elements:
    - factor: string
      value_or_category_used: string
      source: string
      effect_on_decision: string
      importance: decisive | major | supporting
      uncertainty_or_quality_note: string | null

  rules_applied:
    - rule_plain_language: string
      result: string

  evidence_timeline:
    - time: datetime
      event: string

  counterfactual_summary:
    tested: boolean
    meaningful_changes: [string]
    limitations: [string]

  limitations:
    system_limitations: [string]
    data_limitations: [string]
    missing_or_withheld_information: [string]

  correction_review_and_contest:
    correct_data_method: string | null
    human_review_method: string | null
    contest_method: string | null
    deadline: datetime | null

  provenance:
    decision_record_digest: string
    system_version: string
    explanation_generated_at: datetime
```

### Open questions requiring legal review

1. **Classification and role.** Is the particular deployment an Annex III system, an Annex I product component, outside high-risk classification, or excluded under Article 6? Which organization is provider, deployer, importer, distributor, product manufacturer, or a combination?

2. **Article 86 scope.** Which decisions are legally or similarly significant, when is a decision sufficiently “based on” the AI output, and when does the Annex III point 2 exclusion apply?

3. **Other explanation rights.** Does GDPR, employment law, consumer-credit law, administrative law, social-protection law, medical-device law, or another sector regime provide a parallel or controlling explanation right?

4. **National restrictions and procedure.** Do Member State rules restrict explanation content or impose specific language, timing, identity-verification, complaint, representation, or appeal procedures?

5. **Retention beyond the AI Act minimum.** Which sector rules, limitation periods, litigation holds, public-record obligations, employment files, credit records, medical records, or incident-investigation duties extend or shorten retention?

6. **GDPR lawful basis.** What is the Article 6 basis for evidence logging, and what Article 9 or Article 10 condition applies if special-category or criminal-offence data is processed?

7. **Controller and processor allocation.** Who controls the decision ledger, raw-content vault, telemetry backend, model-provider traces, and explanation service? Are there joint-controller or processor-chain issues?

8. **DPIA and fundamental-rights assessment alignment.** Which processing and deployment changes require a new or updated DPIA, fundamental-rights impact assessment, or consultation with supervisory authorities?

9. **Raw-content necessity.** For each use case, which prompt segments, retrieved evidence, tool responses, and human-review materials must remain available in original form, and which may be reduced to normalized facts, excerpts, digests, or references?

10. **Trade secrets, confidentiality, and third-party rights.** What information may lawfully be withheld from an affected person, and what alternative explanation is needed to remain clear and meaningful?

11. **Human-oversight effectiveness.** What competence, staffing, response time, independence, authority, and fail-safe behavior are adequate for the specific risk and decision context?

12. **Biometric requirements.** Does the use case trigger Article 12’s biometric-specific logging fields or Article 14’s two-person verification rule and its exceptions?

13. **Hosted-model versioning.** What contractual evidence is required from GPAI and tool providers to identify silent updates, obtain evaluation documentation, receive incident notices, and preserve decision-relevant version evidence?

14. **Substantial modification.** Which changes to prompts, tools, autonomy, retrieval, fine-tuning, thresholds, purpose, or subject population could constitute a substantial modification or change provider status?

15. **Current standards and guidance.** Which harmonised standards, common specifications, Commission guidance, GPAI Code commitments, sector standards, or notified-body expectations are operative at the actual deployment or conformity-assessment date?

16. **Assurance wording.** Which labels may the open-source templates use without implying certification, legal compliance, regulatory approval, or a conformity assessment that `xai` does not perform?