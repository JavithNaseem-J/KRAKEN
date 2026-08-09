## Context

The current streaming loading indicator in `ruixen-moon-chat.tsx` displays verbose text (`Agent is processing knowledge & executing tools…`), and the textarea placeholder displays `Agent is processing…`. In addition, `ReasoningInspectorDrawer.tsx` displays raw markdown strings (`GAPS OR CONFLICTS: * The lack of...`).

## Goals / Non-Goals

**Goals:**

- Replace verbose loading text with a clean inline thinking badge: `🧠 Agent is thinking…`
- Update textarea disabled placeholder to `Agent is thinking…`
- Format reasoning text in `ReasoningInspectorDrawer.tsx` into clean callout cards using `react-markdown`
- Style executed action badges into translucent dark panels with subtle tags

**Non-Goals:**

- Modifying backend orchestrator or LLM graph nodes.
- Changing HITL approval logic or decision endpoints.

## Decisions

- **Decision 1**: Standardize the loading state string to `Agent is thinking…` across `ruixen-moon-chat.tsx` streaming badge and disabled input placeholder for visual consistency.
- **Decision 2**: Use `react-markdown` in `ReasoningInspectorDrawer.tsx` to cleanly format reasoning step titles (`RELEVANT INFORMATION`, `GAPS OR CONFLICTS`, `CONCLUSION`) into structured cards instead of raw unparsed text.

## Risks / Trade-offs

- None identified; purely frontend UI/UX text and layout refinement.
