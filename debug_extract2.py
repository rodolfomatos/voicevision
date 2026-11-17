#!/usr/bin/env python3
"""Debug extract_sentences hanging - full logic."""

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
sentences = []
current = []
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
    elif ch in closing_quotes:
        if in_quotes and quote_pairs.get(quote_char) == ch:
            in_quotes = False
            quote_char = None
    
    # Check for sentence endings
    if ch in '.!?。！？':
        # Check for ellipsis
        if i + 2 < len(text) and text[i:i+3] == '...':
            print(f'i={i}: ellipsis, skipping')
            i += 2
            continue
        
        # Check for common abbreviations (simple heuristic)
        if ch == '.':
            # Look back for abbreviation pattern
            word_end = i
            word_start = word_end
            while word_start > 0 and text[word_start - 1].isalpha():
                word_start -= 1
            word = text[word_start:word_end].lower()
            print(f'  i={i}: word={repr(word)}')
            
            # Also check for multi-letter abbreviations like U.S.A., Ph.D., etc.
            is_dotted_abbrev = False
            if word_start >= 3:
                prev_text = text[word_start - 3:word_end]
                if re.match(r'^[a-zA-Z](\.[a-zA-Z])+\.$', prev_text):
                    is_dotted_abbrev = True
                    print(f'  -> Dotted abbrev detected: {prev_text}')
            
            abbrevs = (
                'dr', 'sr', 'sra', 'srta', 'prof', 'profª', 'profº',
                'etc', 'ex', 'p', 'pp', 'cap', 'art', 'inc',
                'ltd', 'sa', 'eua', 'uk', 'br', 'sp', 'rj',
                'mr', 'mrs', 'ms', 'mx', 'prof', 'dra', 'drª',
                'sr', 'sra', 'srta', 'eng', 'arq', 'bio', 'quim',
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
                'git', 'svn', 'hg', 'cvs', 'pr', 'mr', 'issue', 'bug',
                'feat', 'fix', 'refactor', 'docs', 'style', 'test',
                'chore', 'build', 'ci', 'cd', 'deploy', 'rollback',
                'hotfix', 'release', 'tag', 'branch', 'merge', 'rebase',
                'cherry-pick', 'bisect', 'blame', 'log', 'diff', 'patch',
                'stash', 'reset', 'revert', 'checkout', 'switch', 'restore'
            )
            
            if word in abbrevs or is_dotted_abbrev:
                print(f'  -> Abbreviation detected, skipping')
                i += 1
                continue  # Not a sentence end
        
        # Handle period followed by closing quote
        next_char = text[i + 1] if i + 1 < len(text) else ''
        period_followed_by_closing_quote = (
            ch == '.' and next_char in {'"', "'", '»', '”', '’', '”'}
        )
        is_closing_quote = ch in {'"', "'", '»', '”', '’', '”'} and in_quotes
        
        if period_followed_by_closing_quote:
            print(f'  i={i}: period followed by closing quote')
        elif is_closing_quote:
            print(f'  i={i}: is_closing_quote')
        
        if period_followed_by_closing_quote or is_closing_quote:
            should_split = True
        else:
            should_split = (paren_depth == 0 and not in_quotes)
        
        if should_split:
            sentence = ''.join(current).strip()
            if sentence:
                sentences.append(sentence)
            current = []
    
    i += 1
    if iteration > 1000:
        print('INFINITE LOOP!')
        break

print('Sentences:', sentences)
print('Done')