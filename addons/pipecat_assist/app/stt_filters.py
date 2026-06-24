"""Filters for local-runtime STT output.

faster-whisper hallucinates filler phrases ("Thank you", "Bye bye bye",
"Thanks for watching", ...) on silence and low-level background noise. Left
unfiltered, each hallucination becomes a user turn that interrupts the
assistant before it can answer or run a tool. ``is_stt_noise`` drops these
before they enter the pipeline.

ponytail: a whitelist-by-exact-phrase blocklist + repeated-fragment heuristic,
matched on the WHOLE transcript only — so real commands that merely contain a
filler word ("thanks, now turn off the lights") still pass.
"""

from __future__ import annotations

import re

# Lowercased, surrounding-punctuation-stripped phrases faster-whisper emits on
# silence. Matched only as a *whole* transcript, never as a substring.
_HALLUCINATION_PHRASES = frozenset(
    {
        "thank you",
        "thanks",
        "thank you very much",
        "thank you for watching",
        "thanks for watching",
        "thank you for watching this video",
        "please subscribe",
        "subscribe",
        "you",
        "bye",
        "bye bye",
        "goodbye",
        "okay",
        "ok",
        "so",
        "yeah",
        "hmm",
        "mm",
        "um",
        "uh",
    }
)

# A "letter" in any language (keeps Polish ł/ą/ę etc.), excluding digits.
_HAS_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)


def is_stt_noise(transcript: str) -> bool:
    """Return True when a transcript is a silence/noise hallucination, not speech."""

    text = (transcript or "").strip()
    if len(text) < 2:
        return True

    norm = re.sub(r"\s+", " ", text.lower()).strip(" .,!?-–—…\"'")
    if not norm:
        return True
    if norm in _HALLUCINATION_PHRASES:
        return True

    # Same short fragment repeated, e.g. "Bye. Bye. Bye."
    fragments = [f.strip() for f in re.split(r"[\n.!?]+", text) if f.strip()]
    if len(fragments) >= 3 and len({f.lower() for f in fragments}) == 1:
        return True

    # Same single word repeated, e.g. "you you you" / "bye bye bye bye".
    words = norm.split()
    if len(words) >= 3 and len(set(words)) == 1:
        return True

    # No actual letters at all (pure punctuation / digits / symbols).
    if not _HAS_LETTER_RE.search(norm):
        return True

    return False


if __name__ == "__main__":
    # ponytail self-check: `python stt_filters.py` — no framework needed.
    _noise = [
        "", " ", ".", "...", "you", "Thank you.", "thank you", "Thanks for watching!",
        "Bye.\n Bye.\n Bye.", "you you you", "  um  ", "Okay.", "123", "- -", "?!",
    ]
    _real = [
        "turn off the office lights",
        "what's the temperature",
        "thanks, now turn off the lights",  # contains 'thanks' but is a command
        "lights off",
        "set the heat to 21",
        "is the garage door open",
    ]
    for _t in _noise:
        assert is_stt_noise(_t), f"should be noise: {_t!r}"
    for _t in _real:
        assert not is_stt_noise(_t), f"should pass: {_t!r}"
    print("stt_filters self-check passed")
