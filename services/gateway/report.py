"""
Executive Incident Briefing PDF Generator.
Generates structured PDF reports for completed sessions/incidents using ReportLab.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any


def generate_incident_pdf(session_data: dict[str, Any]) -> bytes:
    """
    Generate an Executive Incident Briefing PDF from session data.
    `session_data` structure:
    {
      "session_id": "...",
      "persona": {"label": "Alice", "title": "Tier 1 Analyst"},
      "messages": [{"role": "user"|"assistant", "content": "...", "timestamp": "..."}],
      "timestamp": "..."
    }
    """
    session_id = str(session_data.get("session_id", "N/A"))
    persona = session_data.get("persona") or {}
    persona_label = persona.get("label", "Analyst")
    persona_title = persona.get("title", "Security Tier 1")
    messages = session_data.get("messages", [])
    export_time = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "TitleStyle",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            textColor=colors.HexColor("#6b21a8"),
            spaceAfter=4,
        )
        subtitle_style = ParagraphStyle(
            "SubTitleStyle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            textColor=colors.HexColor("#4b5563"),
            spaceAfter=12,
        )
        section_style = ParagraphStyle(
            "SectionStyle",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            textColor=colors.HexColor("#1f2937"),
            spaceBefore=10,
            spaceAfter=6,
        )
        msg_header_user = ParagraphStyle(
            "UserMsgHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=colors.HexColor("#2563eb"),
        )
        msg_header_bot = ParagraphStyle(
            "BotMsgHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=colors.HexColor("#7c3aed"),
        )
        msg_body = ParagraphStyle(
            "MsgBody",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#374151"),
        )

        story = []

        # Header Title
        story.append(Paragraph("KRAKEN Executive Incident Briefing", title_style))
        story.append(Paragraph(f"Autonomous Cyber Operations & Security Triage Report | Exported: {export_time}", subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#9333ea"), spaceAfter=12))

        # Metadata Table
        meta_table_data = [
          [Paragraph("<b>Incident / Session ID:</b>", msg_body), Paragraph(session_id[:16] + "...", msg_body)],
          [Paragraph("<b>Analyst Persona:</b>", msg_body), Paragraph(f"{persona_label} ({persona_title})", msg_body)],
          [Paragraph("<b>Total Messages:</b>", msg_body), Paragraph(str(len(messages)), msg_body)],
        ]
        meta_table = Table(meta_table_data, colWidths=[150, 380])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f9fafb")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#f3f4f6")),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 14))

        # Audit Trail Section
        story.append(Paragraph("Session Communication & Audit Trail", section_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e5e7eb"), spaceAfter=8))

        for idx, m in enumerate(messages, 1):
            role = str(m.get("role", "user")).lower()
            content = str(m.get("content", "")).replace("\n", "<br/>")
            timestamp = str(m.get("timestamp", ""))[:19]

            header_p = Paragraph(f"#{idx} [{role.upper()}] — {timestamp}", msg_header_user if role == "user" else msg_header_bot)
            body_p = Paragraph(content[:2000], msg_body)

            msg_table = Table([[header_p], [body_p]], colWidths=[530])
            bg_color = colors.HexColor("#eff6ff") if role == "user" else colors.HexColor("#f5f3ff")
            border_color = colors.HexColor("#bfdbfe") if role == "user" else colors.HexColor("#ddd6fe")
            msg_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), bg_color),
                ('BOX', (0, 0), (-1, -1), 0.5, border_color),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(msg_table)
            story.append(Spacer(1, 6))

        story.append(Spacer(1, 14))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#9333ea"), spaceAfter=8))
        story.append(Paragraph("CONFIDENTIAL — Internal Security Operations & Incident Audit Record", subtitle_style))

        doc.build(story)
        return buffer.getvalue()

    except ImportError:
        # Fallback minimal PDF builder if reportlab is not available
        buffer = io.BytesIO()
        pdf_header = (
            b"%PDF-1.4\n"
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            b"2 0 obj << /Type /Pages /Kinds [] /Count 1 /Kids [3 0 R] >> endobj\n"
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >> endobj\n"
            b"4 0 obj << /Length 120 >> stream\n"
            b"BT /Helvetica 14 Tf 50 720 Td (KRAKEN Executive Briefing Report - Session " + session_id[:8].encode('utf-8') + b") Tj ET\n"
            b"endstream endobj\n"
            b"xref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000210 00000 n \n"
            b"trailer << /Size 5 /Root 1 0 R >>\nstartxref\n380\n%%EOF"
        )
        buffer.write(pdf_header)
        return buffer.getvalue()
