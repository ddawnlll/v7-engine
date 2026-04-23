# V7 Documentation Writing Guide

## Purpose

This document defines how V7 markdown documentation should be written.

Its job is to keep the V7 doc set:

- compact
- readable by humans
- efficient for LLM code agents
- low in repetition
- explicit about authority and boundaries
- safe for implementation work

This is a writing and structure guide for documentation authors.
It does not replace architecture, contract, simulation, or implementation authority documents.

---

## Core Position

**V7 docs must be written for execution, not for decoration.**

A V7 document should help a human or LLM agent quickly answer:

1. what this document controls
2. what it does not control
3. what is stable
4. what can change
5. what other docs are authoritative
6. what implementation work is allowed
7. what assumptions are forbidden

If a document does not improve implementation clarity, reduce ambiguity, or reduce change risk, it should usually not exist.

---

## Documentation Goals

Every V7 markdown file should optimize for the following:

### 1. Fast extraction
A reader should understand the document's purpose and authority within seconds.

### 2. Low repetition
A concept should be defined once in its primary authority file and referenced elsewhere.

### 3. Stable boundaries
Each document should make ownership boundaries explicit.

### 4. High constraint density
Important rules, invariants, and forbidden changes should be easy to find.

### 5. LLM readability
The document should be easy for an LLM to chunk, retrieve, and follow safely.

### 6. Local change safety
A change in one concern should ideally require editing one main doc, one main module, one main test surface.

### 7. Token efficiency
A document should carry its own minimum required meaning without re-explaining the whole system.

---

## Primary Writing Principles

### 1. Write for authority, not prose beauty
The document should prioritize precision over literary style.

Prefer:
- direct statements
- short sections
- named rules
- explicit invariants
- explicit non-goals

Do not optimize for:
- narrative flourish
- long introductions
- repeated persuasion
- vague architectural language

### 2. One document, one primary job
Each document should own one concern.

Examples:
- `vision.md` owns strategic direction
- `architecture.md` owns system shape and boundaries
- `configuration.md` owns config policy
- `analysis_request.md` owns engine input contract semantics
- `simulation.md` owns truth-layer semantics

A document may reference adjacent concerns, but it should not absorb them.

### 3. Define scope explicitly
Every important doc should state:

- what is in scope
- what is out of scope
- what the document is allowed to define
- what must be defined elsewhere

This prevents semantic bleed across docs.

### 4. Prefer explicit lists over buried rules
If a rule matters, it should not be hidden inside a paragraph.

Prefer:
- rule lists
- invariant lists
- forbidden-change lists
- required-field lists
- ordering lists

### 5. Stable meaning first, examples second
Define semantics before examples.

An example should clarify a rule, not carry the only explanation of the rule.

### 6. Additive evolution over silent mutation
When docs evolve:
- add new sections
- add new optional fields
- add explicit version notes

Do not silently change the meaning of stable terms.

---

## LLM-Optimized Writing Rules

These rules are especially important for AI-assisted engineering.

### 1. Put the decision-bearing content early
The highest-value information should appear near the top.

Recommended early-order pattern:

1. Purpose
2. Core Position
3. In Scope / Out of Scope
4. Hard Rules / Invariants
5. Structure / Fields / Interfaces
6. Failure / Fallback
7. Links to other docs

Do not hide the real contract or authority near the end.

### 2. Use stable section names across files
Reuse section names when possible.

Preferred headings:
- Purpose
- Core Position
- In Scope
- Out of Scope
- Inputs
- Outputs
- Rules
- Invariants
- Failure / Fallback
- Versioning
- Relationship To Other Documents
- Immediate Next Step
- Bottom Line

This improves retrieval and agent predictability.

### 3. Keep paragraphs short
For LLM readability, most paragraphs should be short and single-purpose.

Good pattern:
- one idea per paragraph
- one rule per bullet
- one semantic block per section

Avoid long paragraphs that mix:
- background
- rules
- exceptions
- examples
- future ideas

### 4. Name constraints explicitly
Do not imply important constraints.

Use phrases like:
- must
- must not
- should
- should not
- in scope
- out of scope
- forbidden
- required
- additive only

### 5. Separate semantic layers clearly
Do not mix these layers casually:
- vision
- architecture
- config
- contract
- implementation plan
- runtime policy
- report output

This is one of the fastest ways to create doc hell and LLM confusion.

### 6. Avoid pronoun-heavy writing
Prefer repeating the real object name over using too many pronouns.

Prefer:
- `AnalysisRequest` must include...
- `DecisionEvent` should not contain...

Over:
- it should include...
- this should not contain...

This reduces ambiguity in retrieval chunks.

### 7. Use semantic repetition, not textual repetition
A doc may restate a concept in shortened form if needed for local clarity.
But it should not re-document the full concept if another authority file already owns it.

Good:
- short reminder + link to primary authority

Bad:
- full redefinition copied from another doc

### 8. Optimize for chunk retrieval
Write so that any 10-30 line chunk still carries meaning.

A chunk should ideally reveal:
- what object is being discussed
- what rule is being applied
- what is allowed or forbidden

Avoid chunks that only make sense if the whole file is read linearly.

---

## Token Context Optimization Rules

### 1. Put canonical meaning in one place only
For every major concept, define one primary authority file.

Examples:
- system purpose -> `vision.md`
- system structure -> `architecture.md`
- config policy -> `configuration.md`
- request semantics -> `contracts/analysis_request.md`
- simulation truth -> `pipeline/simulation.md`

All other files should reference that authority rather than duplicating it.

### 2. Avoid copy-paste architecture summaries in every doc
Do not start every file by re-explaining the whole V7 system.

Instead use a short local framing line such as:

> This document defines the X layer. It does not redefine contracts, simulation truth, or runtime ownership.

### 3. Prefer compact cross-links over repeated detail
Use short references like:
- See `architecture.md` for system ownership boundaries.
- See `simulation.md` for truth-layer semantics.
- See `configuration.md` for config precedence.

### 4. Keep examples small and semantically rich
Examples should be:
- short
- representative
- directly tied to a rule

Avoid giant examples that become a second specification.

### 5. Separate generated outputs from authority docs
Do not mix stable design docs with:
- audit dumps
- investigation notes
- migration scratchpads
- evaluation reports
- raw change evidence

These should live in separate operational or generated areas.

### 6. Use consistent terminology
Pick one term and keep it stable.

Examples:
- use `canonical state`, not alternating between `snapshot`, `state blob`, `analysis payload`, `market packet`
- use `decision policy`, not alternating between `selector`, `router`, `arbiter`, `decision layer` unless meanings differ

Term drift wastes tokens and confuses retrieval.

### 7. Keep field lists tighter than explanation lists
When defining contracts or config surfaces:
- list the fields cleanly
- explain only what is necessary
- move secondary nuance to rules or notes

This keeps documents short while preserving semantic clarity.

### 8. Prefer tables only when they compress meaning
Do not use tables by default.

Use a table only if it is clearly denser and more scannable than bullets.
In many architecture and contract docs, bullets are easier for LLM parsing.

---

## Recommended Standard Template

Most V7 authority docs should use a variation of this structure:

```text
# Title

## Purpose
## Core Position
## In Scope
## Out of Scope
## Design Principles
## Inputs
## Outputs
## Structure / Fields / Components
## Rules / Invariants
## Failure / Fallback
## Versioning / Evolution Rules
## Relationship To Other Documents
## Immediate Next Step
## Bottom Line
```

Not every document needs every section.
But the shape should remain familiar.

---

## Document-Type Guidance

## 1. Vision docs
Use to define:
- why the system exists
- what success means
- what it is and is not
- first-order design philosophy

Do not overload vision docs with:
- field-level schemas
- config keys
- code layout details

## 2. Architecture docs
Use to define:
- layers
- ownership boundaries
- truth hierarchy
- integration boundaries
- stable system shape

Do not overload architecture docs with:
- detailed field specs
- experimental TODO lists
- runbook details

## 3. Contract docs
Use to define:
- semantic object boundaries
- required and optional fields
- lineage
- compatibility rules
- forbidden field types

Do not overload contract docs with:
- execution algorithms
- training heuristics
- policy internals unless directly relevant

## 4. Config docs
Use to define:
- config responsibilities
- config file structure
- precedence rules
- validation rules
- safe editing rules

Do not overload config docs with:
- contract meaning
- runtime ownership
- duplicated algorithm specs

## 5. Pipeline docs
Use to define:
- one stage of the learning or runtime pipeline
- inputs and outputs
- invariants
- failure behavior
- config surface

Each pipeline doc should own one stage only.

## 6. Implementation docs
Use to define:
- execution order
- repo mapping
- test strategy
- migration notes

Do not let implementation docs become hidden architecture authority.

## 7. Reports and operational docs
Use for:
- evaluation output
- rollout evidence
- incidents
- audits

These should not redefine stable semantics.

---

## What To Avoid

### 1. Doc hell through phase explosion
Avoid creating separate permanent docs for every temporary phase unless they are truly necessary.

Bad pattern:
- `phase_1.md`
- `phase_2.md`
- `phase_3_realign.md`
- `phase_3_followup.md`
- `phase_3_final_final.md`

Prefer:
- one roadmap
- one implementation plan
- generated reports in a separate area

### 2. Same rule copied across many docs
If the same paragraph appears in five files, one of those files should become the authority and the rest should link to it.

### 3. Hidden authority
Do not let a random follow-up note become the real source of truth.

Authority should be obvious from filename, location, and document structure.

### 4. Mixed stable and unstable content
Do not mix:
- stable contract semantics
- temporary migration details
- one-off debugging notes

These should be separate docs.

### 5. Vague ownership
Avoid sentences like:
- this area may handle some of...
- the system can also maybe use...
- this may be controlled elsewhere...

If ownership matters, name it exactly.

### 6. Giant wall-of-text sections
If a section is too long to skim, it is too expensive for both humans and LLMs.
Break it into named subsections.

---

## Markdown Style Rules

### Headings
- Use clear, stable headings.
- Prefer `##` and `###` over deeply nested heading trees.
- Avoid unnecessary heading depth.

### Lists
- Use bullets for rules, responsibilities, and forbidden items.
- Keep list items parallel in style where possible.

### Code fences
Use code fences only for:
- schema sketches
- folder trees
- small examples
- command examples

Do not hide major rules inside large code fences.

### Inline emphasis
Use bold sparingly for high-signal statements only.
Too much emphasis reduces scan value.

### File references
Prefer explicit file references like:
- `vision.md`
- `contracts/analysis_request.md`
- `pipeline/simulation.md`

This makes doc navigation easier for both humans and agents.

---

## Cross-Linking Rules

### 1. Link upward to authority
A lower-level or adjacent document should link to the authority that owns the concept.

### 2. Do not create circular explanation chains
A reader should not have to bounce across five docs to understand one basic rule.

### 3. Use short relationship sections
Every important doc should include a short section like:

- aligned with
- depends on
- does not replace
- next doc to read

This improves guided traversal.

---

## Writing Workflow

When creating a new V7 doc, use this workflow:

1. identify the document's single primary job
2. identify which existing doc already owns adjacent concepts
3. define scope and out-of-scope first
4. write the hard rules and invariants early
5. add only the minimum examples needed
6. remove repeated architecture explanation
7. add cross-links to primary authority docs
8. trim anything that is really implementation scratchpad content
9. check whether the same concept is defined elsewhere already
10. shorten until the document keeps only necessary meaning

---

## LLM Safety Checklist

Before finalizing a doc, check the following:

- Is the primary authority of this file obvious?
- Is the scope explicit?
- Is the out-of-scope section explicit?
- Are the hard rules easy to find?
- Are forbidden changes named directly?
- Are stable terms used consistently?
- Is repeated system background removed?
- Does the document link to stronger authority docs instead of copying them?
- Can a retrieved chunk stand on its own?
- Would an LLM know what not to change after reading this file?

If the answer is no to several of these, the doc needs revision.

---

## Recommended Repo Placement

A compact V7 doc system should keep this guide close to the core authority docs.

Recommended location:

```text
docs/v7/
  doc_writing_guide.md
```

This makes it easy for both humans and LLM agents to find the writing standard.

---

## Immediate Next Use

This guide should be applied when writing or revising:

- contract docs
- pipeline docs
- runtime docs
- implementation docs
- any future V7 authority markdown file

It should also be used as a review checklist before adding new permanent docs.

---

## Bottom Line

V7 markdown docs should be:

- compact
- explicit
- authority-driven
- low-repetition
- easy to chunk
- easy to retrieve
- safe for LLM implementation work

The target is not documentation volume.
The target is high-signal documentation that makes the codebase easier to build, change, and trust.
