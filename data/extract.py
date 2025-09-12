import re

# Extract text again to capture topic sections and assign mapping of words to topics.
text_full = ""
try:
    from pdfminer.high_level import extract_text
    text_full = extract_text(str(pdf_path))
except:
    pass

if not text_full.strip():
    try:
        import PyPDF2
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text_full += page.extract_text() + "\n"
    except:
        pass

lines = [ln.strip() for ln in text_full.splitlines() if ln.strip()]

# Identify topic sections
topic_names = [
    "Clothes", "Communications and technology", "Daily life",
    "Education", "Entertainment and media", "Environment", "Food and drink",
    "Health, medicine and exercise", "Hobbies and leisure", "House and home",
    "Language", "People", "Personal feelings, opinions and experiences",
    "Places", "Services", "Shopping", "Social interaction", "Sport",
    "The natural world", "Transport", "Travel and holidays", "Weather", "Work and jobs"
]

topic_set = set(topic_names)

# Build mapping word->topic by scanning lines
word_topic_map = {}
current_topic = None
for ln in lines:
    if ln in topic_set:
        current_topic = ln
        continue
    # If line looks like a headword entry, map it
    m = re.match(r"^([A-Za-z][A-Za-z0-9'’\-/\. ]+)\s*\([a-zA-Z .&/]+\)$", ln)
    if m and current_topic:
        word_topic_map[m.group(1).strip()] = current_topic

# Apply mapping to df
df2 = df.copy()
df2["category"] = df2["word"].map(word_topic_map).fillna("")

# Save updated Excel
out_path2 = Path("/mnt/data/b1_words_with_topics.xlsx")
df2.to_excel(out_path2, index=False)

# Preview
preview2 = df2.head(30)
caas_jupyter_tools.display_dataframe_to_user("B1词汇按主题分类（预览前30行）", preview2)

out_path2.as_posix()