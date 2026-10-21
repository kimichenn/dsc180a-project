"""Local text token matching; server counts require calibration and a live audit."""
import math

class TokenCounter:
    def __init__(self, settings):
        self.settings = settings.copy()
        self.encoding = None
        if settings["kind"] == "tiktoken":
            import tiktoken
            from importlib.metadata import version
            self.encoding = tiktoken.get_encoding(settings["encoding"])
            self.settings["version"] = version("tiktoken")
        elif settings["kind"] != "characters" or settings.get("characters_per_token", 0) <= 0:
            raise ValueError("Choose characters or a named tiktoken encoding")

    def count(self, text):
        if self.encoding is not None:
            return len(self.encoding.encode(text, disallowed_special=()))
        return math.ceil(len(text) / self.settings["characters_per_token"])

    def exact_for(self, model):
        # Empirical agreement does not verify a served model's tokenizer/framing.
        return False


def match_texts(texts, counter, tolerance=.02, before=None):
    """Pad only the appendix to a fixed target, counting every candidate in tokens.

    Binary search avoids the old character-derived padding cost and moving target.
    A short one-token filler corrects the remaining difference after whole phrases.
    """
    if not texts or not 0 < tolerance <= .02:
        raise ValueError("Supply prompts and a tolerance in (0, 0.02]")
    if before and any(text.count(before) != 1 for text in texts.values()):
        raise ValueError("Padding requires exactly one question boundary")
    target = max(counter.count(text) for text in texts.values()) + 4
    result = {}
    for key, original in texts.items():
        def candidate(n, remainder=0):
            padding = "\n" + "Routine note. " * n + " Note" * remainder
            return original.replace(before, padding + before) if before else original + padding

        lo, hi = 0, 1
        while counter.count(candidate(hi)) < target:
            hi *= 2
            if hi > 1_000_000:
                raise ValueError("Padding exceeds the supported size")
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if counter.count(candidate(mid)) <= target:
                lo = mid
            else:
                hi = mid - 1
        alternatives = [candidate(lo, n) for n in range(9)]
        best = min(alternatives, key=lambda text: abs(counter.count(text) - target))
        if abs(counter.count(best) - target) > 1:
            raise ValueError("Could not match the fixed token target within one token")
        result[key] = best
    counts = {key: counter.count(text) for key, text in result.items()}
    if (max(counts.values()) - min(counts.values())) / max(counts.values()) > tolerance:
        raise ValueError("Matched prompt counts exceed the requested tolerance")
    return result, counts

