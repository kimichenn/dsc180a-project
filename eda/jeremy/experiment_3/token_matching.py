"""Frozen copy of Experiment 2 token estimation and neutral padding helpers."""
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
        return self.encoding is not None and model in self.settings.get("verified_for_models", [])


def match_texts(texts, counter, tolerance=.02, before=None):
    """Pad a reserved non-evidence appendix; retain counts and method with the plan."""
    result = dict(texts)
    for _ in range(3000):
        counts = {k: counter.count(v) for k, v in result.items()}
        target = max(counts.values())
        if (target - min(counts.values())) / target <= tolerance:
            return result, counts
        for key, count in counts.items():
            if (target - count) / target > tolerance:
                # Neutral words contain no route, office, project, or record identifiers.
                padding = "\n" + "Routine note. " * max(1, (target - count) // 4)
                if before:
                    if result[key].count(before) != 1:
                        raise ValueError("Padding requires one question boundary")
                    result[key] = result[key].replace(before, padding + before)
                else:
                    result[key] += padding
    raise ValueError("Unable to match token lengths")

