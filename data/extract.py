from __future__ import annotations
import logging
import re
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd

# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(asctime)s %(name)s: %(message)s",
)
log = logging.getLogger("extract_topics")

# ------------------------------------------------------------
# Constants
# ------------------------------------------------------------

TOPIC_NAMES = [
    "Clothes", "Communications and technology", "Daily life",
    "Education", "Entertainment and media", "Environment", "Food and drink",
    "Health, medicine and exercise", "Hobbies and leisure", "House and home",
    "Language", "People", "Personal feelings, opinions and experiences",
    "Places", "Services", "Shopping", "Social interaction", "Sport",
    "The natural world", "Transport", "Travel and holidays", "Weather", "Work and jobs",
]
TOPIC_SET = set(TOPIC_NAMES)

# Headword + note in parentheses, for example:
#   Apple Inc. (US)
#   mother-in-law (n.)
#   rock’n’roll (music)
#
# Explanation:
#   ^(?P<head>...)      Headword at line start (letters/numbers/spaces/hyphens/dots/slashes/straight or curly quotes)
#   \s*                 Optional spaces between headword and parentheses
#   \( (?P<note>...) \) Note inside parentheses (letters/spaces/dots/&/slashes)
#   $                   End of line
HEADWORD_LINE_RE = re.compile(
    r"""
    ^(?P<head>[A-Za-z0-9`’'./\- ]+?)     # headword (non-greedy)
    \s*
    \(
      (?P<note>[A-Za-z .&/]+)
    \)
    $
    """,
    re.VERBOSE,
)

# ------------------------------------------------------------
# PDF text extraction with fallback
# ------------------------------------------------------------

def extract_text_with_fallback(pdf_path: Path) -> str:
    """Extract text from PDF using pdfminer; fallback to PyPDF2 if needed."""
    text_full = ""
    # Primary: pdfminer.six
    try:
        from pdfminer.high_level import extract_text  # type: ignore
        text_full = extract_text(str(pdf_path))
        if text_full and text_full.strip():
            log.info("Text extracted using pdfminer.")
            return text_full
    except ImportError as e:
        log.warning("pdfminer not installed: %s", e)
    except Exception as e:
        log.warning("pdfminer failed: %s", e)

    # Fallback: PyPDF2
    try:
        import PyPDF2  # type: ignore
    except ImportError as e:
        log.error("PyPDF2 not installed and pdfminer failed: %s", e)
        return text_full  # empty

    try:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                try:
                    txt = page.extract_text() or ""
                except Exception as pe:
                    log.warning("PyPDF2 failed on a page: %s", pe)
                    txt = ""
                if txt:
                    text_full += txt + "\n"
        if text_full.strip():
            log.info("Text extracted using PyPDF2 fallback.")
        else:
            log.warning("PyPDF2 extracted empty text.")
    except (OSError, ValueError) as e:
        log.error("Failed to read PDF via PyPDF2: %s", e)

    return text_full

# ------------------------------------------------------------
# Parsing helpers
# ------------------------------------------------------------

def iter_nonempty_lines(text: str) -> Iterable[str]:
    """Yield non-empty, stripped lines from text."""
    for ln in text.splitlines():
        s = (ln or "").strip()
        if s:
            yield s

def try_parse_headword_line(line: str) -> Optional[str]:
    """If line matches headword pattern, return the headword (without note); else None."""
    m = HEADWORD_LINE_RE.match(line)
    if not m:
        return None
    return m.group("head").strip()

def build_word_topic_map(lines: Iterable[str]) -> Dict[str, str]:
    """Scan lines: track current topic; map 'headword (note)' lines to that topic."""
    current_topic: Optional[str] = None
    mapping: Dict[str, str] = {}

    for ln in lines:
        if ln in TOPIC_SET:
            current_topic = ln
            continue

        head = try_parse_headword_line(ln)
        if head and current_topic:
            mapping[head] = current_topic

    log.info("Built word->topic map of size %d", len(mapping))
    return mapping

# ------------------------------------------------------------
# Main pipeline
# ------------------------------------------------------------

def assign_topics_and_save(
    df: pd.DataFrame,
    pdf_path: Path,
    out_path: Path = Path("b1_words_with_topics.xlsx"),
) -> Path:
    """Extract topics from PDF, map words to topics, write DataFrame to Excel."""
    text_full = extract_text_with_fallback(pdf_path)
    if not text_full.strip():
        log.error("No text extracted from PDF: %s", pdf_path)
    lines = list(iter_nonempty_lines(text_full))
    mapping = build_word_topic_map(lines)

    # Do not modify the original df, only add the category column
    df2 = df.copy()
    if "word" not in df2.columns:
        raise KeyError("DataFrame is missing required column: 'word'")
    df2["category"] = df2["word"].map(mapping).fillna("")

    out_path = Path(out_path)
    try:
        df2.to_excel(out_path, index=False)
        log.info("Saved: %s (rows=%d)", out_path, len(df2))
    except OSError as e:
        log.error("Failed to save Excel: %s", e)
        raise
    return out_path

# ------------------------------------------------------------
# Usage (expects df & pdf_path defined by caller)
# ------------------------------------------------------------
# out_path2 = assign_topics_and_save(df=df, pdf_path=Path(pdf_path))
# from caas_jupyter_tools import display_dataframe_to_user
# display_dataframe_to_user("B1 Vocabulary by topic (preview of the first 30 lines)", pd.read_excel(out_path2).head(30))
# print(out_path2.as_posix())
