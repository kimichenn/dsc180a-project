"""The final-answer line every experiment asks for: "ANSWER: ...", tolerant of markdown and "Final answer:"."""

from __future__ import annotations

import re

ANSWER_LINE = re.compile(r"^[\s*_#>`-]*(?:final\s+)?answer[\s*_`]*:(.*)$", re.IGNORECASE | re.MULTILINE)
