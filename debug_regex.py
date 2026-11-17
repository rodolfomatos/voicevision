#!/usr/bin/env python3
"""Test the dotted abbreviation detection."""

import re

text = 'Dr. Smith went to the U.S.A. He saw Mr. Jones.'

# Test the dotted abbreviation detection at each period position
for i, ch in enumerate(text):
    if ch == '.':
        word_end = i
        word_start = word_end
        while word_start > 0 and text[word_start - 1].isalpha():
            word_start -= 1
        word = text[word_start:word_end].lower()
        
        print(f'Position {i}: word={repr(word)}, word_start={word_start}')
        
        # Check for dotted abbreviation pattern
        is_dotted_abbrev = False
        if word_start >= 3:
            # Check for pattern like X.Y.Z. where each letter is followed by .
            prev_text = text[word_start - 3:word_end]
            print(f'  prev_text={repr(prev_text)}')
            if re.match(r'^[a-zA-Z](\.[a-zA-Z])+\.$', prev_text):
                is_dotted_abbrev = True
                print(f'  -> Dotted abbrev detected: {prev_text}')
        
        # Also check broader context: look at the 6 chars before the period
        if i >= 5:
            broader = text[i-5:i+1]
            print(f'  broader context: {repr(broader)}')
            if re.match(r'^[a-zA-Z](\.[a-zA-Z])+\.$', broader):
                print(f'  -> Broader dotted abbrev: {broader}')