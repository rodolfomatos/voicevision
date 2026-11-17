#!/usr/bin/env python3
"""Debug the abbreviation detection in extract_sentences."""

from voicevision.text import extract_sentences

text = 'Dr. Smith went to the U.S.A. He saw Mr. Jones.'
print('Input:', text)
print('---')

# Debug: manually trace through
text = 'Dr. Smith went to the U.S.A. He saw Mr. Jones.'
print('Input:', text)
print('---')

# Check abbreviation detection
import re
text = 'Dr. Smith went to the U.S.A. He saw Mr. Jones.'
for i, ch in enumerate(text):
    if ch == '.':
        word_end = i
        word_start = word_end
        while word_start > 0 and text[word_start - 1].isalpha():
            word_start -= 1
        word = text[word_start:word_end].lower()
        print(f'Position {i}: word={repr(word)}')
        if word in ('dr', 'sr', 'sra', 'srta', 'prof', 'profª', 'profº',
                    'etc', 'ex', 'p', 'pp', 'cap', 'art', 'inc',
                    'ltd', 'sa', 'eua', 'uk', 'br', 'sp', 'rj'):
            print(f'  -> Abbreviation detected: {word}')
        else:
            print(f'  -> NOT an abbreviation')