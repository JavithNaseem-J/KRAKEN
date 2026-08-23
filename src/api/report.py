"""
Executive Incident Briefing Generator.
Generates structured HTML reports for completed sessions/incidents using Jinja2.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from jinja2 import Template

_BRIEFING_TEMPLATE = Template(
    """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Incident Briefing — {{ session_id }}</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
  h1 { font-size: 1.5rem; border-bottom: 2px solid #e5e7eb; padding-bottom: 0.5rem; }
  .meta { color: #6b7280; font-size: 0.875rem; margin-bottom: 1.5rem; }
  .message { border-left: 3px solid #6366f1; padding: 0.75rem 1rem; margin: 0.75rem 0; background: #f9fafb; }
  .message.user { border-left-color: #3b82f6; }
  .message.assistant { border-left-color: #10b981; }
  .role { font-weight: 700; font-size: 0.8rem; text-transform: uppercase; margin-bottom: 0.25rem; }
  .role.user { color: #2563eb; }
  .role.assistant { color: #059669; }
  .persona { background: #f3f4f6; padding: 0.75rem 1rem; border-radius: 0.5rem; margin-bottom: 1rem; }
  footer { margin-top: 2rem; color: #9ca3af; font-size: 0.75rem; border-top: 1px solid #e5e7eb; padding-top: 0.75rem; }
</style>
</head>
<body>
<h1>Incident Briefing</h1>
<div class="meta">
  <strong>Session:</strong> {{ session_id }}<br>
  <strong>Exported:</strong> {{ export_time }}
</div>
<div class="persona">
  <strong>Persona:</strong> {{ persona_label }} &mdash; {{ persona_title }}
</div>
<h2>Conversation Log</h2>
{% for msg in messages %}
<div class="message {{ msg.role }}">
  <div class="role {{ msg.role }}">{{ msg.role }}</div>
  <div>{{ msg.content }}</div>
  {% if msg.timestamp %}<div>{{ msg.timestamp }}</div>{% endif %}
</div>
{% else %}
<p><em>No messages recorded.</em></p>
{% endfor %}
<footer>KRAKEN Incident Briefing &bull; Generated {{ export_time }}</footer>
</body>
</html>"""
)


def generate_incident_html(session_data: dict[str, Any]) -> str:
    """Generate an Executive Incident Briefing HTML from session data."""
    session_id = str(session_data.get("session_id", "N/A"))
    persona = session_data.get("persona") or {}
    persona_label = persona.get("label", "Analyst")
    persona_title = persona.get("title", "Security Tier 1")
    messages = session_data.get("messages", [])
    export_time = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    return _BRIEFING_TEMPLATE.render(
        session_id=session_id,
        persona_label=persona_label,
        persona_title=persona_title,
        messages=messages,
        export_time=export_time,
    )
