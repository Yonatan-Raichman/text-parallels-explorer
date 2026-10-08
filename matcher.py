import re # Let's python search text using patterns
from difflib import SequenceMatcher # SequenceMatcher is a python tool that compares two sequences

SEED_SIZE = 4 # How many words in a row must be identical to start a match
MAX_GAP = 20 # How many words apart two seeds may be and still belong to one passage
MIN_WORDS = 8 # Ignore matches shroter that this
MIN_SCORE = 0.5 # Ignore matches less similar that this
MAX_COMMON = 25 # Ignore 4-word phrases that appear more often than this

def get_words(text): # Take a big text and split it into individual words
    return [(m.group().lower(), m.start(), m.end()) for m in re.finditer(r"[A-Za-z]+", text)] # Returns the words in a list form like [ ("hello", 0, 5),("world", 6, 11)]

def find_seeds(words_a,words_b): # Function that finds a seed (seed = 4 identical consecutive words)
    phrases_b = {}
    for j in range(len(words_b) - SEED_SIZE + 1): # loops through words in text B
        phrase = tuple(words_b[j:j + SEED_SIZE]) # Takes 4 words starting at j, using tuples because tuples can be used as dictionary keys
        phrases_b.setdefault(phrase, []).append(j) # Stores the position where that phrase appears

    seeds = [] # Empoty list of all the seeds we find
    for i in range(len(words_a) - SEED_SIZE + 1): # loops through words in text A
        phrase = tuple(words_a[i:i + SEED_SIZE]) # Take 4 words from text A
        positions = phrases_b.get(phrase, []) # Does this exact 4 words exist in text B?
        if len(positions) <= MAX_COMMON: # If this phrase appears 25 times or less, use it
            for j in positions: # Go through every place the phrase occurs in text B
                seeds.append((i,j)) # Store the match
    return seeds # If phrase starts at word 100 in A and word 250 in B store: (100,250)

def group_seeds(seeds): # Turns nearby seeds into one larger passage
    groups = [] # Stores every group we've created
    open_groups = [] # These groups are close enough that new seeds could be added to them
    for i,j in seeds: # Go through each seed
        open_groups = [g for g in open_groups if i-g[-1][0] <= MAX_GAP] #Removes groups that are too far behind
        placed = False # We haven't yet found a group for the current seed
        for group in open_groups: # Try every possible open group
            last_i, last_j = group[-1] # Take the privious seed in that group
            if 0 < i - last_i <= MAX_GAP and 0 < j - last_j <= MAX_GAP: # Is the new seed reasonably close to the previous seed in BOTH texts?
                group.append((i, j)) # Add the seed to that group
                placed = True # Remember taht this seed successfuly found a group
                break # Stop checking other groups - we already found one
        if not placed: # If we couldn't find any nearby group
            new_group = [(i, j)] # Create a new group containing only this seed
            groups.append(new_group) # Save the new group
            open_groups.append(new_group) # Also mark it as open, because future seeds might join it
    return groups

def similarity(words_a,words_b): # This function calculates how similar two passages are
    return SequenceMatcher(None, words_a,words_b,autojunk=False).ratio()

def find_parallels(text_a, text_b):
    tokens_a, tokens_b = get_words(text_a), get_words(text_b) # Split both texts into words
    words_a = [w for w, _, _ in tokens_a] # Keep only the words from text A
    words_b = [w for w, _, _ in tokens_b] # Keep only the words from text B

    matches = []
    for group in group_seeds(find_seeds(words_a, words_b)): # find the seeds, group them and the look at each group
        # first and last word of the passage in each text
        a_first, a_last = group[0][0], group[-1][0] + SEED_SIZE - 1 # find the first and last word of the passage in text A
        b_first = min(j for _, j in group) # Find the earlies seed position in text B
        b_last = max(j for _, j in group) + SEED_SIZE - 1 # Find the last position covered by seeds in text B
        passage_a = words_a[a_first:a_last + 1] # Take all the words from the beginning to the end of the passage in A
        passage_b = words_b[b_first:b_last + 1] # Take all the words from the beginning to the end of the passage in B

        length = max(len(passage_a), len(passage_b)) # Finds the larges passage
        score = round(similarity(passage_a, passage_b), 3) # Caluculates the similarity score
        if length < MIN_WORDS or score < MIN_SCORE: # Filter bad matches
            continue
        matches.append({
            "a_start": tokens_a[a_first][1], "a_end": tokens_a[a_last][2],  # a_start - Where the passage starts in the original text A, a_end - Where it ends in A 
            "b_start": tokens_b[b_first][1], "b_end": tokens_b[b_last][2], 
            "score": score,
            "kind": "exact" if score == 1 else "near",
            "words": length,
        })
    return remove_overlaps(matches) # Before giving the results back, remove duplicate/overlapping matches


def remove_overlaps(matches):
    kept = [] # Create an empty list of matches we'll keep
    for m in sorted(matches, key=lambda m: -m["words"]): # Sort matches by length, longest first because if two matches overlap, we want to keep the bigger one
        overlaps = any(
            m["a_start"] < k["a_end"]
            and k["a_start"] < m["a_end"]
            and m["b_start"] < k["b_end"]
            and k["b_start"] < m["b_end"]
            for k in kept
        )

        if not overlaps:
            kept.append(m)

    return kept