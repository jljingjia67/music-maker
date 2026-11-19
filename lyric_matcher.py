#!/usr/bin/env python3
"""
Lyric Matcher — checks whether new lyrics fit the rhythm of an original song.

Analyzes syllable count, stress pattern, and rhyme scheme, then scores
how well replacement lyrics would sit on the original melody.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field

import pronouncing


# ── Syllable & stress helpers ──────────────────────────────────────────

def clean_word(word: str) -> str:
    return re.sub(r"[^a-zA-Z']", "", word).lower()


def syllable_count(word: str) -> int:
    """Count syllables using CMU dict, with a regex fallback."""
    cleaned = clean_word(word)
    if not cleaned:
        return 0

    phones = pronouncing.phones_for_word(cleaned)
    if phones:
        return pronouncing.syllable_count(phones[0])

    return _fallback_syllable_count(cleaned)


def _fallback_syllable_count(word: str) -> int:
    """Rough syllable count when a word isn't in CMU dict."""
    word = word.lower()
    count = len(re.findall(r'[aeiouy]+', word))
    if word.endswith('e') and not word.endswith('le') and count > 1:
        count -= 1
    if word.endswith("'s"):
        pass
    return max(1, count)


def stress_pattern(word: str) -> str:
    """
    Return the stress pattern of a word as a string of 0/1/2.
    0 = unstressed, 1 = primary stress, 2 = secondary stress.
    Falls back to simple heuristic.
    """
    cleaned = clean_word(word)
    if not cleaned:
        return ""

    phones = pronouncing.phones_for_word(cleaned)
    if phones:
        return pronouncing.stresses(phones[0])

    count = _fallback_syllable_count(cleaned)
    if count == 1:
        return "1"
    return "1" + "0" * (count - 1)


def last_syllable_phones(word: str) -> str | None:
    """Get the phonemes from the last stressed vowel onward (for rhyme checking)."""
    cleaned = clean_word(word)
    if not cleaned:
        return None

    phones_list = pronouncing.phones_for_word(cleaned)
    if not phones_list:
        return None

    phones = phones_list[0].split()
    last_stressed_idx = -1
    for i, p in enumerate(phones):
        if any(c.isdigit() for c in p):
            last_stressed_idx = i

    if last_stressed_idx == -1:
        return " ".join(phones[-2:]) if len(phones) >= 2 else " ".join(phones)

    return " ".join(phones[last_stressed_idx:])


# ── Line analysis ──────────────────────────────────────────────────────

@dataclass
class LineAnalysis:
    text: str
    words: list[str]
    syllables_per_word: list[int]
    total_syllables: int
    stress: str
    last_word: str
    rhyme_tail: str | None

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "total_syllables": self.total_syllables,
            "stress": self.stress,
            "syllables_per_word": self.syllables_per_word,
            "last_word": self.last_word,
        }


def analyze_line(text: str) -> LineAnalysis:
    words = text.split()
    cleaned_words = [clean_word(w) for w in words]
    cleaned_words = [w for w in cleaned_words if w]

    syl_counts = [syllable_count(w) for w in cleaned_words]
    stresses = "".join(stress_pattern(w) for w in cleaned_words)
    last = cleaned_words[-1] if cleaned_words else ""

    return LineAnalysis(
        text=text.strip(),
        words=cleaned_words,
        syllables_per_word=syl_counts,
        total_syllables=sum(syl_counts),
        stress=stresses,
        last_word=last,
        rhyme_tail=last_syllable_phones(last),
    )


# ── Comparison scoring ─────────────────────────────────────────────────

@dataclass
class LineComparison:
    original: LineAnalysis
    replacement: LineAnalysis
    syllable_diff: int
    syllable_match: bool
    stress_similarity: float
    rhymes: bool
    score: float
    notes: list[str] = field(default_factory=list)


def stress_similarity(a: str, b: str) -> float:
    """Compare two stress strings, returning 0.0–1.0 similarity."""
    if not a or not b:
        return 0.0

    max_len = max(len(a), len(b))
    a_padded = a.ljust(max_len, "0")
    b_padded = b.ljust(max_len, "0")

    matches = 0
    for ca, cb in zip(a_padded, b_padded):
        if ca == cb:
            matches += 1
        elif (ca in "12" and cb in "12"):
            matches += 0.5

    return matches / max_len


def words_rhyme(word_a: str, word_b: str) -> bool:
    """Check if two words rhyme."""
    a = clean_word(word_a)
    b = clean_word(word_b)
    if a == b:
        return True

    rhymes_a = pronouncing.rhymes(a)
    if b in rhymes_a:
        return True

    tail_a = last_syllable_phones(a)
    tail_b = last_syllable_phones(b)
    if tail_a and tail_b and tail_a == tail_b:
        return True

    return False


def compare_lines(original: LineAnalysis, replacement: LineAnalysis) -> LineComparison:
    syl_diff = replacement.total_syllables - original.total_syllables
    syl_match = syl_diff == 0
    stress_sim = stress_similarity(original.stress, replacement.stress)
    rhymes = words_rhyme(original.last_word, replacement.last_word)

    notes = []

    if syl_diff > 0:
        notes.append(f"{syl_diff} extra syllable(s) — will feel rushed")
    elif syl_diff < 0:
        notes.append(f"{abs(syl_diff)} fewer syllable(s) — will feel stretched")

    if stress_sim < 0.5:
        notes.append("Stress pattern clashes with melody accents")
    elif stress_sim < 0.75:
        notes.append("Stress pattern is a loose fit")

    if not rhymes:
        notes.append(f"'{replacement.last_word}' doesn't rhyme with '{original.last_word}'")

    syl_score = max(0, 1.0 - abs(syl_diff) * 0.25)
    score = syl_score * 0.50 + stress_sim * 0.35 + (1.0 if rhymes else 0.0) * 0.15

    if not notes:
        notes.append("Great fit!")

    return LineComparison(
        original=original,
        replacement=replacement,
        syllable_diff=syl_diff,
        syllable_match=syl_match,
        stress_similarity=stress_sim,
        rhymes=rhymes,
        score=score,
        notes=notes,
    )


# ── Full song comparison ──────────────────────────────────────────────

def parse_lyrics(text: str) -> list[str]:
    """Parse lyrics text into clean lines, dropping section headers and blanks."""
    lines = []
    for raw in text.strip().splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.match(r'^\[.*\]$', line):
            continue
        line = re.sub(r'\[.*?\]', '', line)
        line = re.sub(r'\(.*?\)', '', line)
        line = line.strip()
        if line:
            lines.append(line)
    return lines


def compare_lyrics(original_text: str, replacement_text: str) -> list[LineComparison]:
    orig_lines = parse_lyrics(original_text)
    repl_lines = parse_lyrics(replacement_text)

    comparisons = []
    for i in range(min(len(orig_lines), len(repl_lines))):
        orig_a = analyze_line(orig_lines[i])
        repl_a = analyze_line(repl_lines[i])
        comparisons.append(compare_lines(orig_a, repl_a))

    if len(repl_lines) > len(orig_lines):
        for i in range(len(orig_lines), len(repl_lines)):
            repl_a = analyze_line(repl_lines[i])
            comparisons.append(LineComparison(
                original=LineAnalysis("(no original line)", [], [], 0, "", "", None),
                replacement=repl_a,
                syllable_diff=repl_a.total_syllables,
                syllable_match=False,
                stress_similarity=0.0,
                rhymes=False,
                score=0.0,
                notes=["Extra line — no corresponding original"],
            ))

    return comparisons


# ── Display ───────────────────────────────────────────────────────────

GRADE_THRESHOLDS = [(0.9, "A", "🟢"), (0.75, "B", "🟡"), (0.6, "C", "🟠"), (0.0, "F", "🔴")]


def grade(score: float) -> tuple[str, str]:
    for threshold, letter, icon in GRADE_THRESHOLDS:
        if score >= threshold:
            return letter, icon
    return "F", "🔴"


def print_report(comparisons: list[LineComparison]):
    if not comparisons:
        print("No lines to compare.")
        return

    print()
    print("=" * 72)
    print("  LYRIC MATCH REPORT")
    print("=" * 72)

    total_score = 0
    for i, c in enumerate(comparisons):
        letter, icon = grade(c.score)
        total_score += c.score

        print(f"\n  Line {i + 1}  {icon} {letter}  (score: {c.score:.0%})")
        print(f"  Original:    {c.original.text}")
        print(f"               syllables: {c.original.total_syllables}  "
              f"stress: {c.original.stress}")
        print(f"  Replacement: {c.replacement.text}")
        print(f"               syllables: {c.replacement.total_syllables}  "
              f"stress: {c.replacement.stress}")

        if c.syllable_diff != 0:
            direction = "+" if c.syllable_diff > 0 else ""
            print(f"  Syllables:   {direction}{c.syllable_diff}")
        else:
            print(f"  Syllables:   match ✓")

        print(f"  Stress sim:  {c.stress_similarity:.0%}")
        print(f"  Rhyme:       {'yes ✓' if c.rhymes else 'no ✗'}")

        for note in c.notes:
            print(f"  → {note}")

    avg = total_score / len(comparisons)
    letter, icon = grade(avg)

    print()
    print("-" * 72)
    print(f"  OVERALL: {icon} {letter}  ({avg:.0%})")
    print(f"  {len(comparisons)} lines compared")

    perfect = sum(1 for c in comparisons if c.syllable_match)
    print(f"  Syllable matches: {perfect}/{len(comparisons)}")

    rhyming = sum(1 for c in comparisons if c.rhymes)
    print(f"  Rhyme matches:    {rhyming}/{len(comparisons)}")
    print("=" * 72)
    print()


def print_json_report(comparisons: list[LineComparison]):
    report = {
        "lines": [],
        "overall_score": 0,
        "total_lines": len(comparisons),
    }

    total = 0
    for c in comparisons:
        letter, _ = grade(c.score)
        total += c.score
        report["lines"].append({
            "original": c.original.text,
            "replacement": c.replacement.text,
            "score": round(c.score, 3),
            "grade": letter,
            "syllable_diff": c.syllable_diff,
            "stress_similarity": round(c.stress_similarity, 3),
            "rhymes": c.rhymes,
            "notes": c.notes,
        })

    report["overall_score"] = round(total / len(comparisons), 3) if comparisons else 0
    letter, _ = grade(report["overall_score"])
    report["overall_grade"] = letter

    print(json.dumps(report, indent=2))


# ── Analyze-only mode ─────────────────────────────────────────────────

def print_analysis(text: str):
    lines = parse_lyrics(text)
    print()
    print("=" * 72)
    print("  LYRIC ANALYSIS")
    print("=" * 72)

    for i, line in enumerate(lines):
        a = analyze_line(line)
        print(f"\n  Line {i + 1}: {a.text}")
        print(f"    Syllables: {a.total_syllables}  ({', '.join(str(s) for s in a.syllables_per_word)})")
        print(f"    Stress:    {a.stress}")
        print(f"    Last word: {a.last_word}")

    print()
    print("=" * 72)
    print()


# ── CLI ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Check whether replacement lyrics fit an original song's rhythm"
    )
    parser.add_argument("original", help="Path to original lyrics text file")
    parser.add_argument("replacement", nargs="?", help="Path to replacement lyrics text file")
    parser.add_argument(
        "--analyze", action="store_true",
        help="Just analyze the original lyrics (syllable counts, stress, etc.)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON instead of a formatted report",
    )

    args = parser.parse_args()

    with open(args.original) as f:
        original_text = f.read()

    if args.analyze:
        print_analysis(original_text)
        return

    if not args.replacement:
        print("Error: provide a replacement lyrics file, or use --analyze.")
        sys.exit(1)

    with open(args.replacement) as f:
        replacement_text = f.read()

    comparisons = compare_lyrics(original_text, replacement_text)

    if args.json:
        print_json_report(comparisons)
    else:
        print_report(comparisons)


if __name__ == "__main__":
    main()
