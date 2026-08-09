"""
Shared application constants across AKEA microservices.
"""

import re

# Standard regex pattern for ticket IDs (e.g., TCK-1001, TK-001)
TICKET_ID_PATTERN = r"\b(?:TCK-\d+|TK-\d+)\b"
TICKET_ID_REGEX = re.compile(TICKET_ID_PATTERN, re.IGNORECASE)
