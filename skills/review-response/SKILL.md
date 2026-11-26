---
name: review-response
description: Compatibility entry for explicit requests to use the legacy review-response skill. Routes rebuttal and reviewer-response work to the installed nature-response workflow.
metadata:
  version: "0.1.1-local"
---

# Review Response Compatibility Entry

For rebuttal drafting, revision correspondence, or review-comment analysis, read
[the response workflow](../nature-response/SKILL.md) and follow its task-specific route.
Do not run a second rebuttal workflow or load the legacy references by default.

The existing `references/` remain available if the user explicitly requests a legacy
template. Treat ML/ICLR examples as venue-specific examples, not requirements for
physical chemistry. This skill does not register a slash command or depend on
any legacy manuscript-writing skill. Keep each claimed experiment or manuscript
change tied to an actual artifact; distinguish planned work from completed work.
