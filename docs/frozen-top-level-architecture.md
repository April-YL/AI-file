# Frozen Top-Level Architecture

This document is the frozen target architecture contract for the AI QC Agent.
It is the single top-level architecture reference for future implementation
mapping and alignment work.

This document is not a redesign proposal. It does not introduce new layers,
new execution paths, or refactor instructions. It formalizes the final agreed
architecture contract only.

## Frozen Architecture

```text
INPUT
  ↓
ORCHESTRATOR
  ↓
INGEST ENGINE
   ├─ deterministic parsing
   ├─ IDENTIFIER (semantic sub-layer)
   └─ ingest confidence
  ↓
STANDARDIZED MODEL DRAFT
  ↓
EARLY VALIDATION LOOP
  ↓
STANDARDIZED MODEL
  ↓
RULE ENGINE
  ↓
DECISION GATE
  ↓
CONTROL PLANE (SINGLETON)
  ↓
FINDING MODEL
  ↓
REPORT (Presentation / Delivery Layer)
```

```text
LLM ROUTER (INFRASTRUCTURE LAYER)

- used by INGEST IDENTIFIER
- used by CONTROL PLANE REASONER
- used by FALLBACK
- owns token control, caching, tracing, budget management, and model routing
```

## Module Responsibilities

### Orchestrator

The Orchestrator owns execution flow and run-state progression.

Responsibilities:

- Accept the input handoff from the system entry point.
- Advance the single runtime pipeline in the defined order.
- Coordinate stage execution without making audit decisions.
- Preserve the single execution chain.

The Orchestrator must not produce business findings, change rule outcomes, or
perform semantic reasoning.

### Ingest Engine

The Ingest Engine owns workpaper understanding and standardized model creation.

Responsibilities:

- Perform deterministic parsing of input workbooks or other supported inputs.
- Extract sheets, fields, sections, tables, records, and source references.
- Run the embedded Identifier semantic sub-layer when gated.
- Produce ingest confidence signals.
- Produce the Standardized Model Draft.

The Ingest Engine must not generate final findings or determine audit
conclusions.

### Identifier

The Identifier is an embedded semantic sub-layer inside the Ingest Engine.

Responsibilities:

- Assist sheet, field, section, and table identification.
- Support noisy data parsing and ambiguous mapping clarification.
- Detect possible missing objects during ingest.
- Provide semantic enrichment needed to form the standardized model.

The Identifier may use the LLM Router when gated. The Identifier must not
produce PASS, FAIL, WARN, or final findings. It must not modify rule results.

### Early Validation Loop

The Early Validation Loop validates model readiness before deterministic rule
execution.

Responsibilities:

- Check structural completeness of the Standardized Model Draft.
- Check ingest confidence and model usability.
- Identify whether the model is ready for the Rule Engine.

The Early Validation Loop is not an audit decision layer. It must not generate
findings, assign severity, or produce business conclusions.

### Rule Engine

The Rule Engine is the deterministic truth source.

Responsibilities:

- Execute deterministic QC rules.
- Evaluate structured data, fields, thresholds, reconciliations, and rule
  conditions.
- Produce deterministic rule outputs.

The Rule Engine must not call LLMs. It must not depend on LLM reasoning for
deterministic conclusions. It must not modify ingest data.

### Decision Gate

The Decision Gate organizes and locks rule outputs before control-plane
handling.

Responsibilities:

- Preserve deterministic rule outputs.
- Mark conflicts, ambiguity, and uncertainty for Control Plane evaluation.
- Prepare rule outputs for impact modeling.

The Decision Gate must not override rule results, invoke LLMs directly, or
perform presentation logic.

### Control Plane

The Control Plane is the singleton decision authority for routing, fallback,
and reasoner triggering.

Responsibilities:

- Evaluate ambiguity policy.
- Decide whether post-rule semantic reasoning is required.
- Decide fallback routing.
- Decide skip logic.
- Preserve rule authority.

The Control Plane must not modify deterministic rule results. It must not
modify the standardized model. No distributed policy layer may override the
Control Plane.

### Finding Model

The Finding Model is the only impact carrier.

Responsibilities:

- Carry deterministic findings.
- Carry semantic findings when allowed by the Control Plane.
- Carry ingest risks.
- Carry manual review routes.
- Provide the only structured impact object consumed by reporting and delivery.

All system outputs that affect review or delivery must pass through the
Finding Model.

### Report

The Report is the Presentation / Delivery Layer.

Responsibilities:

- Format findings.
- Export delivery artifacts.
- Render reviewer-facing views.
- Present annotations and structured outputs.

The Report must not modify findings. It must not recalculate severity. It must
not influence system decisions.

### LLM Router

The LLM Router is an infrastructure layer, not a pipeline stage.

Responsibilities:

- Provide the only governed LLM access path.
- Serve the Ingest Identifier when gated.
- Serve the Control Plane Reasoner when gated.
- Serve fallback behavior when gated.
- Own token control.
- Own caching.
- Own tracing.
- Own budget management.
- Own model routing.
- Own prompt and version control metadata.

The LLM Router must not own business logic or audit decisions.

## System Principles (Non-Negotiable)

### Single Execution Chain Principle

The system has one runtime execution pipeline only. There must be no parallel
pipelines and no separate data, decision, or LLM execution flows in the system
structure.

### LLM Infrastructure Principle

LLM is infrastructure, not a pipeline stage. LLM behavior is accessed only
through the LLM Router and must not own deterministic business logic.

### Control Plane Singleton Principle

The Control Plane is the singleton decision authority for routing, fallback,
and reasoner triggering. There must be no distributed policy logic that
competes with or bypasses the Control Plane.

### Ingest Semantic Ownership Principle

Ingest owns semantic understanding. The Identifier must remain inside the
Ingest Engine as its semantic sub-layer. The Identifier cannot produce final
findings.

### Rules As Truth Principle

Rules are the deterministic truth source. Rule outputs must not be modified by
LLM, Report, Identifier, Control Plane, or any presentation layer.

### Finding Model Ownership Principle

The Finding Model is the only impact carrier. Review-impacting outputs must be
represented through the Finding Model before reaching report or delivery
surfaces.

### Report Isolation Principle

Report is presentation and delivery only. Report must not modify findings,
recalculate severity, or influence upstream system decisions.

## LLM Router as Infrastructure Layer

The LLM Router is not part of the main execution pipeline. It is a shared
infrastructure service used by authorized stages under gated conditions.

The LLM Router may be used by:

- Ingest Identifier during the ingest phase.
- Control Plane Reasoner during the decision phase.
- Fallback handling during degraded paths.

The LLM Router owns:

- Token control.
- Trace capture.
- Cache behavior.
- Budget management.
- Model routing.
- Prompt and version metadata.

The LLM Router must not become a business decision stage. It must not own rule
logic, finding authority, or severity authority.

## Execution Flow vs Observability Views

The system has one execution flow only:

```text
INPUT
  ↓
ORCHESTRATOR
  ↓
INGEST ENGINE
  ↓
STANDARDIZED MODEL DRAFT
  ↓
EARLY VALIDATION LOOP
  ↓
STANDARDIZED MODEL
  ↓
RULE ENGINE
  ↓
DECISION GATE
  ↓
CONTROL PLANE
  ↓
FINDING MODEL
  ↓
REPORT
```

Data flow, decision flow, and LLM flow are not separate pipelines. They are
observability perspectives on the same single execution chain.

Observability perspectives:

- Data view: how input becomes a standardized model.
- Decision view: how deterministic rule outputs are locked and routed.
- LLM usage view: where authorized LLM infrastructure is used and traced.

These views must not be implemented as separate runtime pipelines.

## Hard Constraints (Freeze Rules)

- No new layers are allowed.
- No architectural changes are allowed.
- No code modifications are included in this contract.
- No refactoring actions are included in this contract.
- No pipeline stage may be added, removed, or reordered by this document.
- LLM Router must remain infrastructure, not a pipeline stage.
- Control Plane must remain singleton.
- Identifier must remain inside the Ingest Engine.
- Rules must remain deterministic truth source.
- Finding Model must remain the only impact carrier.
- Report must remain isolated from decision-making.

