## Why

The current AI loading indicator ("Agent is processing knowledge & executing tools...") and input placeholder ("Agent is processing...") feel verbose and unpolished. Replacing them with a clean, minimal "🧠 Agent is thinking…" badge aligns the interface with modern AI application standards (like ChatGPT and Gemini) while presenting a professional, sleek execution state. Additionally, formatting in the Reasoning Inspector drawer needs structured card rendering for reasoning steps and clean styling for executed actions.

## What Changes

- Replace verbose loading text with a clean inline thinking badge: `🧠 Agent is thinking…`
- Update input box disabled placeholder to `Agent is thinking…`
- Refactor `ReasoningInspectorDrawer` to parse step-by-step reasoning sections into clean callout cards (removing raw unparsed markdown symbols)
- Style executed action badges and output payloads into translucent dark panels with subtle tags

## Capabilities

### New Capabilities

- `agent-thinking-indicator`: Replaces verbose loading copy with compact inline thinking badges and clean disabled input placeholders.
- `reasoning-inspector-formatting`: Formats agent reasoning and action execution outputs into structured cards in the Inspector drawer.

### Modified Capabilities

None.

## Impact

- `frontend-react/src/components/ui/ruixen-moon-chat.tsx`: Thinking badge text and textarea placeholder.
- `frontend-react/src/components/ReasoningInspectorDrawer.tsx`: Structured reasoning cards and action payload styling.
