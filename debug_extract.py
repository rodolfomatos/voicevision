#!/usr/bin/env python3
"""Debug extract_sentences hanging."""

import re

text = 'Dr. Smith went to the U.S.A. He saw Mr. Jones.'
print('Input:', text)
print('Length:', len(text))

in_quotes = False
quote_char = None
paren_depth = 0
symmetric_quotes = {'"', "'"}
opening_quotes = {'«', '„', '‘', '“'}
closing_quotes = {'»', '”', '’', '”'}
quote_pairs = {'"': '"', "'": "'"}

i = 0
iteration = 0
while i < len(text):
    iteration += 1
    if iteration > 1000:
        print(f'INFINITE LOOP at i={i}')
        break
    
    ch = text[i]
    
    # Parentheses
    if ch == '(':
        paren_depth += 1
    elif ch == ')':
        paren_depth = max(0, paren_depth - 1)
    
    # Quotes
    symmetric_quotes = {'"', "'"}
    opening_quotes = {'«', '„', '‘', '“'}
    closing_quotes = {'»', '”', '’', '”'}
    quote_pairs = {'"': '"', "'": "'"}
    
    if ch in symmetric_quotes:
        print(f'  i={i}, ch={repr(ch)}: symmetric quote')
    elif ch in opening_quotes:
        print(f'  i={i}, ch={repr(ch)}: opening quote')
    elif ch in closing_quotes:
        print(f'  i={i}, ch={repr(ch)}: closing quote')
    
    i += 1
    if i > 100:
        print('Breaking')
        break

print('Done')