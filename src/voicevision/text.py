"""Text processing utilities for sentence boundary detection and word timing.

Ported from Hex (anomalyco/hex) crates/capture/src/transcribe.rs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class WordTiming:
    """A word with its timing information.

    Ported from Hex's WordTiming.
    """
    word: str
    t0: int  # Start time in milliseconds
    t1: int  # End time in milliseconds


def ends_sentence(word: str) -> bool:
    """Check if a word ends a sentence.

    Ported from Hex's `ends_sentence`. Handles:
    - Standard punctuation (.!?;)
    - Trailing quotes, parentheses, brackets
    - CJK punctuation
    - Ellipsis (...) is NOT a sentence end

    Args:
        word: A word (may include trailing punctuation).

    Returns:
        True if the word ends a sentence.
    """
    if not word:
        return False

    # Check for ellipsis first
    if word.rstrip().endswith('...'):
        return False

    # Strip trailing closing punctuation that doesn't end a sentence
    stripped = word.rstrip('\'"）】」』»”’')
    if not stripped:
        return False

    # Check for sentence-ending punctuation
    last_char = stripped[-1]
    return last_char in '.!?;。！？；'


def spread_words(
    words: list[WordTiming],
    interval_start: int,
    interval_end: int,
) -> list[WordTiming]:
    """Distribute words proportionally over a time interval.

    Ported from Hex's `spread_words`. When word timings are not available
    for all words (e.g., only segment-level timing), this distributes
    words evenly across the segment duration.

    Args:
        words: List of words (timing will be assigned).
        interval_start: Start of interval in milliseconds.
        interval_end: End of interval in milliseconds.

    Returns:
        Words with t0/t1 assigned proportionally.
    """
    if not words:
        return []

    duration = interval_end - interval_start
    if duration <= 0:
        # Zero or negative duration: assign all to start
        return [
            WordTiming(word=w.word, t0=interval_start, t1=interval_start)
            for w in words
        ]

    # Simple proportional distribution
    # Each word gets duration / n words
    word_duration = duration / len(words)
    result = []

    for i, w in enumerate(words):
        t0 = interval_start + int(i * word_duration)
        t1 = interval_start + int((i + 1) * word_duration)
        # Clamp to interval bounds
        t0 = max(interval_start, min(t0, interval_end))
        t1 = max(interval_start, min(t1, interval_end))
        result.append(WordTiming(word=w.word, t0=t0, t1=t1))

    return result


def segments_from_words(
    words: list[WordTiming],
    *,
    max_gap_ms: int = 700,
) -> list[tuple[int, int, str]]:
    """Reconstruct segments from word timings.

    Ported from Hex's `segments_from_words`. Groups words into segments
    based on timing gaps.

    Args:
        words: Words with timing (t0, t1 in milliseconds).
        max_gap_ms: Maximum gap between words to stay in same segment.

    Returns:
        List of (start_ms, end_ms, text) segments.
    """
    if not words:
        return []

    segments = []
    current_words: list[WordTiming] = []
    segment_start = words[0].t0

    for i, word in enumerate(words):
        if i == 0:
            current_words.append(word)
            continue

        prev_word = words[i - 1]
        gap = word.t0 - prev_word.t1

        if gap > max_gap_ms:
            # Gap too large: end current segment, start new one
            segment_text = " ".join(w.word for w in current_words)
            segments.append((segment_start, prev_word.t1, segment_text))
            current_words = [word]
            segment_start = word.t0
        else:
            current_words.append(word)

    # Add final segment
    if current_words:
        last_word = current_words[-1]
        segment_text = " ".join(w.word for w in current_words)
        segments.append((segment_start, last_word.t1, segment_text))

    return segments


# --- Sentence extraction for streaming ---

def extract_sentences(text: str) -> list[str]:  # noqa: C901
    """Extract complete sentences from text using proper boundary detection.

    Handles:
    - Standard punctuation (.!?;)
    - Quotes and parentheses nesting
    - Abbreviations (Dr., Sr., etc.)
    - Multi-letter abbreviations (U.S.A., Ph.D., etc.)
    - Ellipsis (...)
    - CJK punctuation

    Args:
        text: Input text to split into sentences.

    Returns:
        List of complete sentences (stripped, no trailing space).
    """
    if not text.strip():
        return []

    # Pre-compute positions that should NOT be sentence endings
    # (dotted abbreviations like U.S.A., Ph.D., etc. - but NOT the final period)
    no_split_positions = set()
    for match in re.finditer(r'[a-zA-Z](?:\.[a-zA-Z])+\.', text):
        # Mark all period positions within the abbreviation EXCEPT the last one
        abbrev_text = match.group()
        start = match.start()
        period_positions = [start + j for j, ch in enumerate(abbrev_text) if ch == '.']
        # Add all periods except the last one (which should be a valid sentence end)
        for pos in period_positions[:-1]:
            no_split_positions.add(pos)

    # Also handle common single-word abbreviations
    abbrev_set = {
        'dr', 'sr', 'sra', 'srta', 'prof', 'profª', 'profº',
        'etc', 'ex', 'p', 'pp', 'cap', 'art', 'inc',
        'ltd', 'sa', 'eua', 'uk', 'br', 'sp', 'rj',
        'mr', 'mrs', 'ms', 'mx', 'dra', 'drª',
        'eng', 'arq', 'bio', 'quim',
        'fís', 'mat', 'hist', 'geog', 'fil', 'psic', 'soc',
        'adm', 'cont', 'econ', 'dir', 'coord', 'superv',
        'ger', 'sub', 'chef', 'resp', 'enc', 'assist',
        'téc', 'anal', 'prog', 'desenv', 'impl', 'test',
        'hom', 'prod', 'qa', 'dev', 'ops', 'sec', 'infra',
        'api', 'ui', 'ux', 'db', 'sql', 'nosql', 'ml', 'ai',
        'ci', 'cd', 'k8s', 'docker', 'aws', 'gcp', 'azure',
        'ssh', 'ssl', 'tls', 'http', 'https', 'ftp', 'sftp',
        'dns', 'dhcp', 'nat', 'vpn', 'lan', 'wan', 'vlan',
        'ip', 'tcp', 'udp', 'icmp', 'arp', 'mac', 'os', 'cpu',
        'ram', 'ssd', 'hdd', 'gpu', 'bios', 'uefi', 'mbr',
        'gpt', 'fat', 'ntfs', 'ext4', 'xfs', 'btrfs', 'zfs',
        'raid', 'lvm', 'md', 'dm', 'crypt', 'luks', 'veracrypt',
        'git', 'svn', 'hg', 'cvs', 'pr', 'issue', 'bug',
        'feat', 'fix', 'refactor', 'docs', 'style', 'chore', 'build', 'deploy', 'rollback',
        'hotfix', 'release', 'tag', 'branch', 'merge', 'rebase',
        'cherry-pick', 'bisect', 'blame', 'log', 'diff', 'patch',
        'stash', 'reset', 'revert', 'checkout', 'switch', 'restore'
    }

    sentences = []
    current = []
    paren_depth = 0
    in_quotes = False
    quote_char = None

    i = 0
    while i < len(text):
        ch = text[i]
        current.append(ch)

        # Track parentheses
        if ch == '(':
            paren_depth += 1
        elif ch == ')':
            paren_depth = max(0, paren_depth - 1)

        # Track quotes (matching opening/closing pairs)
        opening_quotes = {'«', '„', '‘', '“'}
        closing_quotes = {'»', '”', '’'}
        symmetric_quotes = {'"', "'"}
        quote_pairs = {'"': '"', "'": "'", '«': '»', '„': '”', '‘': '’', '“': '”'}

        if ch in symmetric_quotes:
            if not in_quotes:
                in_quotes = True
                quote_char = ch
            elif in_quotes and quote_char == ch:
                in_quotes = False
                quote_char = None
        elif ch in opening_quotes:
            if not in_quotes:
                in_quotes = True
                quote_char = ch
        elif (
        ch in closing_quotes
        and in_quotes
        and quote_char is not None
        and quote_pairs.get(quote_char) == ch
    ):
            in_quotes = False
            quote_char = None

        # Check for sentence endings
        if ch in '.!?。！？':
            # Check for ellipsis
            if i + 2 < len(text) and text[i:i+3] == '...':
                # Add all three dots to current
                current.append(text[i+1])
                current.append(text[i+2])
                # Check if ellipsis should end the sentence
                # (similar logic to other punctuation)
                next_char = text[i+3] if i+3 < len(text) else ''
                # Ellipsis followed by closing quote -> end sentence
                ellipsis_followed_by_closing_quote = next_char in {'"', "'", '»', '”', '’'}
                # Ellipsis followed by another punctuation -> end sentence
                ellipsis_followed_by_punct = next_char in '.!?。！？'

                if ellipsis_followed_by_closing_quote or ellipsis_followed_by_punct:
                    # Include the next char if it's a closing quote
                    if ellipsis_followed_by_closing_quote:
                        current.append(next_char)
                        i += 1
                    should_split = True
                else:
                    should_split = (paren_depth == 0 and not in_quotes)

                if should_split:
                    sentence = ''.join(current).strip()
                    if sentence:
                        sentences.append(sentence)
                    current = []

                i += 3
                continue

            # Check if this position is a dotted abbreviation (should NOT split)
            if i in no_split_positions:
                i += 1
                continue

            # Check for common abbreviations (simple heuristic)
            if ch == '.':
                # Look back for abbreviation pattern
                word_end = i
                word_start = word_end
                while word_start > 0 and text[word_start - 1].isalpha():
                    word_start -= 1
                word = text[word_start:word_end].lower()

                if word in abbrev_set:
                    i += 1
                    continue  # Not a sentence end

            # Handle case where period is followed by closing quote
            # e.g., "Hello world." -> the period should end the sentence
            # even though the closing quote comes after
            next_char = text[i + 1] if i + 1 < len(text) else ''
            text[i + 2] if i + 2 < len(text) else ''

            # Check if this punctuation is followed by another sentence-ending punctuation
            multiple_punct = ch in '.!?。！？' and next_char in '.!?。！？'

            period_followed_by_closing_quote = (
                ch == '.' and next_char in {'"', "'", '»', '”', '’'}
            )

            is_closing_quote = ch in {'"', "'", '»', '”', '’'} and in_quotes

            if period_followed_by_closing_quote:
                current.append(next_char)
                i += 1
                should_split = True
            elif is_closing_quote:
                should_split = True
            elif multiple_punct:
                # Include the next punctuation mark
                current.append(next_char)
                i += 1
                should_split = True
            else:
                should_split = (paren_depth == 0 and not in_quotes)

            if should_split:
                sentence = ''.join(current).strip()
                if sentence:
                    sentences.append(sentence)
                current = []

        i += 1

    # Handle remaining text (incomplete sentence)
    remaining = ''.join(current).strip()
    if remaining:
        sentences.append(remaining)

    return sentences
