---
name: research-ideation
description: Develop an early-stage research question, hypothesis, evidence plan, or project plan from a broad topic. Use for 5W1H brainstorming and gap analysis; use paper-lookup for ordinary literature searches, literature-review for formal reviews, and focused writing or Zotero skills for those separate tasks.
metadata:
  version: "0.1.0"
---

# Research Ideation

<!-- local-mw-profile-v1 -->

## Core Features

### 1. Idea Brainstorming (5W1H Framework)

Systematically brainstorm research ideas using the 5W1H framework:
- **What**: What problem or phenomenon to study
- **Why**: Why this problem is important
- **Who**: Target audience and stakeholders
- **When**: Time scope and context of the research
- **Where**: Application scenarios and domains
- **How**: Preliminary research methodology ideas

**Integration with superpowers:brainstorming**: Can invoke the superpowers:brainstorming skill for interactive brainstorming to help rapidly generate and evaluate research ideas.

### 2. Targeted Evidence Scan

Search and synthesize enough literature to refine a research question or test whether a proposed gap is plausible:
- Build focused search terms and select relevant scholarly sources
- Screen and compare evidence, methods, and limitations
- Return source-linked candidates and distinguish recent work from foundational papers
- For broad paper retrieval use `paper-lookup`; for a requested formal scoping or systematic review use `literature-review`
- Do not turn an idea-stage evidence scan into a full review unless requested

### 3. Gap Analysis

Systematically identify and evaluate research gaps:
- **Literature gaps**: Identify topics or questions not yet sufficiently studied
- **Methodological gaps**: Discover limitations and improvement opportunities in existing methods
- **Application gaps**: Identify opportunities for theory-to-practice transfer
- **Interdisciplinary gaps**: Discover research opportunities at the intersection of different fields
- **Temporal gaps**: Identify new research needs arising from changes over time

**Analysis Dimensions:**
- Coverage of research topics
- Comparison of strengths and weaknesses of existing methods
- Completeness of experimental setups
- Availability of datasets and benchmarks
- Gap between theory and practice

### 4. Research Question Definition

Formulate specific research questions based on literature analysis:
- Identify research gaps and opportunities
- Apply SMART principles to formulate questions
- Evaluate importance, novelty, and feasibility
- Define research objectives and expected contributions
- Write a `Research Question Card` that states the hypothesis, current evidence, missing evidence, support criteria, falsification criteria, and minimal next action
- Apply the proposal readiness gate before turning a card into a polished proposal

### 5. Method Selection

Select appropriate research methods:
- Analyze strengths and weaknesses of existing methods
- Evaluate method applicability
- Identify required technologies and resources
- Consider method feasibility

### 6. Research Planning

Develop detailed research plans:
- Plan research timeline
- Define milestones and deliverables
- Identify potential risks
- Assess resource requirements

## When to Use

### Scenarios for This Skill

Use the research-ideation skill in the following situations:

1. **Starting a new research project** - Have research interests but no clear research question yet
2. **Research gap exploration** - Need a targeted evidence scan to shape a question; formal reviews use `literature-review`
3. **Research question formulation** - Need to transform vague ideas into specific research questions
4. **Method selection** - Need to choose appropriate research methods and technical approaches
5. **Research planning** - Need to plan research timeline and resources

### Typical Workflow

```
Research interest → Idea brainstorming (5W1H) → Research Question Card → Evidence Records → Gap analysis → Proposal readiness gate → Select method or experiment → Decision
```

**Conditional Outputs:**
- `research-question-card.md` - Always generate this for research startup or intake.
- `literature-review.md` - Generate only when evidence-labeled sources are sufficient for synthesis.
- `research-proposal.md` - Generate only when a selected Research Question Card passes the evidence gate.
- `references.bib` - Generate only when reliable citation metadata exists.

## Integration with Other Systems

### Complete Research Workflow

```
research-ideation (Research initiation)
    ↓
Experiment execution (completed by user)
    ↓
results-analysis (Results analysis)
    ↓
nature-writing (Paper drafting) or nature-polishing (Existing draft revision)
```

### Data Flow

- **Research Question Card** → Guides literature scope, experiment design, and method selection
- **Evidence Records** → Carry source type, claim strength, and allowed/forbidden wording into literature synthesis, project knowledge, and later claim audit
- **Proposal Readiness Gate** → Prevents abstract-only or webpage-placeholder evidence from becoming a polished proposal
- **Experimental results** → results-analysis for statistical analysis and claim candidates
- **Analysis results** → results-report for internal reports; nature-writing for manuscript prose, with explicit evidence limits

### Zotero handoff

Literature discovery and research planning do not add papers, create Collections, attach files, or change the Zotero library. Return useful citation identifiers and source links in the research notes. When the user asks to inspect or change Zotero, hand off to `managing-zotero` and follow its current preview, authorization, and read-back workflow. Do not call legacy Zotero MCP tools named in older examples or assume that a search request authorizes a library write.

### Key Configuration

- **Literature search scope**: Choose a date window that fits the question; cover recent work and include older foundational or method papers when relevant
- **Output format**: Markdown format for easy editing and version control
- **Citation management**: Generates references in BibTeX format

## Additional Resources

### Reference Files

Detailed methodology guides, loaded on demand:

- **`references/5w1h-framework.md`** - 5W1H Framework Guide
  - What, Why, Who, When, Where, How — six dimensions
  - Systematic approach to brainstorming research ideas
  - Integration with superpowers:brainstorming
  - Usage examples and best practices

- **`references/literature-search-strategies.md`** - Literature Search Strategies
  - Keyword construction techniques
  - Academic database selection (arXiv, Google Scholar)
  - Search tips and screening criteria
  - Paper quality evaluation methods
  - DOI and identifier extraction for a source-linked candidate list

- **`references/zotero-integration-guide.md`** - Scope and handoff to the current Zotero management workflow

- **`references/gap-analysis-guide.md`** - Gap Analysis Guide
  - 5 types of Gap Analysis (literature, methodological, application, interdisciplinary, temporal)
  - 5 analysis dimensions
  - Systematic approach to identifying research opportunities
  - Usage examples and best practices

- **`references/research-question-formulation.md`** - Research Question Formulation
  - Applying SMART principles
  - Question type classification (exploratory, confirmatory, applied)
  - Evaluation criteria (importance, novelty, feasibility)
  - Defining research objectives and contributions

- **`references/research-contract.md`** - Research Contract
  - Research Question Card template
  - Evidence Record template
  - Claim Candidate template
  - Claim strength rules

- **`references/method-selection-guide.md`** - Method Selection Guide
  - Common research method classification
  - Method applicability analysis
  - Strengths and weaknesses comparison
  - Resource requirement assessment

- **`references/research-planning.md`** - Research Planning
  - Timeline planning methods
  - Milestone definition techniques
  - Risk identification and mitigation
  - Resource allocation strategies

### Example Files

Complete working examples:

- **`examples/example-literature-review.md`** - Literature Review Example
  - Demonstrates structured literature review format
  - Includes research trend analysis and gap identification

- **`examples/example-research-proposal.md`** - Research Proposal Example
  - Demonstrates complete research proposal structure
  - Includes complete examples of question, method, and plan
