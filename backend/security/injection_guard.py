"""
Security Layer
Prompt injection detection, input sanitization, secret scrubbing.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Common prompt injection patterns
INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|above)\s+instructions",
    r"forget\s+(everything|all|your\s+instructions)",
    r"you\s+are\s+now\s+(a\s+)?(?:different|new|evil|uncensored)",
    r"do\s+anything\s+now",
    r"DAN\s+mode",
    r"jailbreak",
    r"override\s+(safety|restrictions|guidelines)",
    r"act\s+as\s+if\s+you\s+have\s+no\s+restrictions",
    r"your\s+true\s+self",
    r"pretend\s+you\s+are\s+not\s+an\s+AI",
    r"system\s*:\s*you\s+are",  # Fake system prompt injection
    r"<\s*system\s*>",          # System tag injection
    r"\[INST\]",                # Llama instruction injection
]

# Secret patterns to scrub from tool outputs
SECRET_PATTERNS = [
    (r"(api[_-]?key\s*[:=]\s*)(['\"]?)([A-Za-z0-9_\-]{20,})", r"\1\2***REDACTED***"),
    (r"(password\s*[:=]\s*)(['\"]?)(\S+)", r"\1\2***REDACTED***"),
    (r"(secret\s*[:=]\s*)(['\"]?)(\S+)", r"\1\2***REDACTED***"),
    (r"(token\s*[:=]\s*)(['\"]?)([A-Za-z0-9_\-\.]{20,})", r"\1\2***REDACTED***"),
    (r"sk-[A-Za-z0-9]{40,}", "sk-***REDACTED***"),
    (r"ghp_[A-Za-z0-9]{30,}", "ghp_***REDACTED***"),
    (r"xoxb-[A-Za-z0-9\-]+", "xoxb-***REDACTED***"),
]

COMPILED_INJECTIONS = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]
COMPILED_SECRETS = [(re.compile(p, re.IGNORECASE), r) for p, r in SECRET_PATTERNS]

MAX_INPUT_LENGTH = 8000


class SecurityError(Exception):
    pass


def check_prompt_injection(text: str) -> tuple[bool, str | None]:
    """
    Check for prompt injection attempts.
    Returns (is_safe, detected_pattern).
    """
    for pattern in COMPILED_INJECTIONS:
        match = pattern.search(text)
        if match:
            return False, match.group(0)
    return True, None


def sanitize_input(text: str) -> str:
    """
    Sanitize user input:
    - Truncate to max length
    - Remove null bytes
    - Strip control characters (keep newlines/tabs)
    """
    if not isinstance(text, str):
        text = str(text)

    # Remove null bytes
    text = text.replace("\x00", "")

    # Remove other control chars except \n \r \t
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Truncate
    if len(text) > MAX_INPUT_LENGTH:
        text = text[:MAX_INPUT_LENGTH] + "\n[... truncated for safety]"

    return text


def scrub_secrets(text: str) -> str:
    """Remove secrets from tool outputs before returning to user."""
    for pattern, replacement in COMPILED_SECRETS:
        text = pattern.sub(replacement, text)
    return text


class InputGuard:
    """
    Central input validation.
    Use before processing any user input.
    """

    def __init__(self, strict: bool = True):
        self.strict = strict

    def validate(self, text: str) -> str:
        """
        Validate and sanitize input.
        Raises SecurityError if injection detected (in strict mode).
        Returns sanitized text.
        """
        sanitized = sanitize_input(text)

        is_safe, detected = check_prompt_injection(sanitized)
        if not is_safe:
            logger.warning(f"Prompt injection detected: '{detected}'")
            if self.strict:
                raise SecurityError(
                    f"Input rejected: potential prompt injection detected. "
                    f"Please rephrase your request."
                )
            else:
                logger.warning("Injection detected but strict mode off, continuing")

        return sanitized

    def scrub_output(self, text: str) -> str:
        """Scrub secrets from any output before sending to user."""
        return scrub_secrets(text)


# Singleton guard
_guard: InputGuard | None = None


def get_guard() -> InputGuard:
    global _guard
    if _guard is None:
        _guard = InputGuard(strict=True)
    return _guard
