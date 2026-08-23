import re

# Standard regex pattern for ticket IDs (e.g., TCK-1001, T-1001, TK-001)
TICKET_ID_PATTERN = r"\b(?:TCK|T|TK|INC|SR)[-_]?\d+\b"
TICKET_ID_REGEX = re.compile(TICKET_ID_PATTERN, re.IGNORECASE)
