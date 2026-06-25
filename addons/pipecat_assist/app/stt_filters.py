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


class ReasoningStripper:
    """Streaming remover of ``<think>...</think>`` blocks from a token stream.

    The local Qwen ACE model emits a (usually empty) leading ``<think></think>``
    even with reasoning disabled, which otherwise gets spoken and displayed.
    ``feed(text)`` returns the text safe to emit now (holding back any partial
    tag or in-think content); ``flush()`` returns leftover buffered text at the
    end of a response and resets. Token streaming of the real reply is preserved.
    """

    _OPEN = "<think>"
    _CLOSE = "</think>"

    def __init__(self) -> None:
        self._pending = ""
        self._dropping = False

    def reset(self) -> None:
        self._pending = ""
        self._dropping = False

    def feed(self, text: str) -> str:
        text = self._pending + (text or "")
        self._pending = ""
        out: list[str] = []
        while text:
            if self._dropping:
                idx = text.find(self._CLOSE)
                if idx == -1:
                    self._pending = self._tail_partial(text, self._CLOSE)
                    break
                text = text[idx + len(self._CLOSE):]
                self._dropping = False
            else:
                idx = text.find(self._OPEN)
                if idx == -1:
                    keep = self._tail_partial(text, self._OPEN)
                    out.append(text[: len(text) - len(keep)] if keep else text)
                    self._pending = keep
                    break
                out.append(text[:idx])
                text = text[idx + len(self._OPEN):]
                self._dropping = True
        return "".join(out)

    def flush(self) -> str:
        tail = "" if self._dropping else self._pending
        self.reset()
        return tail

    @staticmethod
    def _tail_partial(text: str, marker: str) -> str:
        """Longest suffix of text that is a prefix of marker (handles split tags)."""
        for k in range(min(len(marker) - 1, len(text)), 0, -1):
            if text.endswith(marker[:k]):
                return text[-k:]
        return ""


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

    def _strip(chunks):
        s = ReasoningStripper()
        return "".join(s.feed(c) for c in chunks) + s.flush()

    assert _strip(["<think>", "</think>", "Hello"]) == "Hello"
    assert _strip(["<think> reasoning </think>", " Hi there"]) == " Hi there"
    assert _strip(["<th", "ink>x</thi", "nk>Done"]) == "Done"  # tags split across chunks
    assert _strip(["No tags here"]) == "No tags here"
    assert _strip(["<think></think>I've turned on the lights."]) == "I've turned on the lights."
    assert _strip(["partial <thi"]) == "partial <thi"  # dangling partial tag kept (not a real think block)
    print("stt_filters self-check passed")
