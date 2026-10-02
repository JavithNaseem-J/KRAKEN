import re

# Seed tickets use numeric IDs; public sessions create twelve-character hex SYN IDs.
TICKET_ID_PATTERN = r"\b(?:(?:TCK|T|TK|INC|SR)[-_]?\d+|SYN-[A-F0-9]{12})\b"
TICKET_ID_REGEX = re.compile(TICKET_ID_PATTERN, re.IGNORECASE)
