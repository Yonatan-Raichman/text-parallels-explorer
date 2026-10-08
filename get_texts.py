import re # library that let's you search text for patterns
import urllib.request # let's python download something from the internet
from pathlib import Path # path help python work with files and folders

BOOKS = {"matthew": 8040, "mark": 8041, "luke": 8042, "john": 8043} # Creates a Python dictionary - The numbers are the Project Gutneberg ebook numbers
FOLDER = Path(__file__).parent / "corpus" # file means the python file that is currently running, this variable now reperesents the corpus folder
FOLDER.mkdir(exist_ok=True) # Creates corpus folder

for name, number in BOOKS.items(): # This loops goes through BOOKS dictionary one book at a time
    saved_by_hand = FOLDER / f"{name}-download.txt" # Constracts the file name
    if saved_by_hand.exists(): # Checks if the file already exists
        raw = saved_by_hand.read_text(encoding="utf-8-sig") # Read all the text in the file and store it inside the variable raw
    else: # If the file doesn't exist
        url = f"https://www.gutenberg.org/cache/epub/{number}/pg{number}.txt" # Builds the Gutenberg URL
        print("Downloading", url)
        raw = urllib.request.urlopen(url).read().decode("utf-8-sig") # Connects to the url, reads the contents (data is in raw bytes) and then converts to python string

    start = raw.find("*** START") # Searches at what point does *** START appear inside raw
    start = raw.find("\n", start) # Searches for the position of newline after the start marker
    end = raw.find("*** END") # Finds where Gutenberg's ending marker begins
    book = raw[start:end] # Give me the text starting at 'start' and ending at 'end'

    marks = list(re.finditer(r"(?<![\d:])(?:\d+:)?(\d+):(\d+)\s", book)) # Find every location a new verse starts, looks like this: ["1:1", "1:2"]
    lines  = []
    for this, following in zip(marks, marks[1:] + [None]): # Go throught each verse
        verse_text = book[this.end(): following.start() if following else len(book)] # Take the text immediately after this verse number, up to the beginning of the next verse number
        verse_text = " ".join(verse_text.split()) # Remove broken lines
        lines.append(f"{int(this.group(1))}:{int(this.group(2))} {verse_text}") # Add the chapter and verse back

    (FOLDER / f"{name}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8") # Save the cleaned book
    print(f" {name}: {len(lines)} verses") # Prints how many verses were found
