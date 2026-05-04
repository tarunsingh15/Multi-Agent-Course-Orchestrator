# Overview:
# - Provides utilities to convert arbitrary document bytes (PDF, DOCX, PPTX, etc.)
#   into a list of normalized "chunks" of text.
# - Uses the optional `unstructured` library's `partition` to extract elements,
#   then normalizes and sentence-splits each element into manageable pieces.
#
# Key constants:
# - MAX_FILE_SIZE_MB: safety guard if you parse from a file path.
# - DEFAULT_MAX_TOKENS (actually words here): target chunk size for readability / LLM context.
# - SUPPORTED_EXTENSIONS: file types allowed when using process_file_path.
#
# Primary entry points:
# 1) process_file_path(file_path): local path → partition → chunks
# 2) process_file_bytes(data, content_type): in-memory bytes → partition → chunks
#
# Why sentence tokenization and further splitting?
# - `unstructured` elements can be long; chunking decreases LLM prompt size,
#   improves retrieval/grounding quality, and supports previews in the UI.
#
# Output schema (for each chunk):
#   {
#     "chunk_id": <uuid>,
#     "chunk_text": <str>,
#     "word_count": <int>,
#     "chunk_order": <int>,         # stable ordering for downstream steps
#     "element_type": <str>,        # e.g., "Title", "NarrativeText", "Table"
#     "page_number": <int|None>     # if available from partition metadata
#   }
#
# This file purposefully avoids external ADK or Firestore knowledge;
# it’s a pure parsing/normalization utility used by agents and tests.
# Note: This code was generated with Google's Gemini. The program was reviewed, modified, and tested to
# ensure functionality.



from __future__ import annotations
import os
import re
import unicodedata
import uuid
from typing import Any, List

import logging
import vertexai
from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel
import time

try:
    # Import the 'unstructured' library to parse complex documents.
    from unstructured.partition.auto import partition  # type: ignore
except Exception:
    partition = None

# --- Configuration ---
MAX_FILE_SIZE_MB = 50
DEFAULT_MAX_TOKENS = 220  # words per chunk
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx"}
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "amazing-math-473517-f9")
LOCATION = "us-central1"

logger = logging.getLogger(__name__)

# --- Helpers ---
def normalize_text(s: str) -> str:
    """
    Cleans up a string by normalizing Unicode characters and collapsing whitespace.
    """
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def safe_sent_tokenize(text: str, language="english") -> list[str]:
    """
    Splits text into sentences using NLTK, with a fallback to return the original
    text as a single-sentence list if tokenization fails.
    """
    import nltk
    try:
        # Get the tokenizer and download it if necessary.
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        nltk.download("punkt", quiet=True)
    try:
        # Tokenize the text into sentences.
        return nltk.sent_tokenize(text, language=language)
    except Exception:
        # If tokenization results in error, return the original text as a single item.
        return [text]

def split_long_chunk(chunk: str, max_words: int) -> list[str]:
    """
    Splits a single long string into multiple smaller strings, each with a word
    count at or below the specified maximum.
    """
    words = chunk.split()
    out, cur = [], []
    for w in words:
        # If adding the next word exceeds the max, finalize the current sub-chunk.
        if len(cur) + 1 > max_words:
            out.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        out.append(" ".join(cur))
    return out

def generate_embeddings(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Generates vector embeddings for a list of text chunks using a Vertex AI model
    and adds the embedding to each chunk dictionary.
    """
    logger.info("Init VERTEXAI for embeddings")
    vertexai.init(project = PROJECT_ID, location = LOCATION)
    
    model = TextEmbeddingModel.from_pretrained("text-embedding-004")
    batch_size = 100 #model can support larger batches upto 250, keeping it 100 for now
    
    texts = [c["chunk_text"] for c in chunks]
    
    updated_chunks = chunks.copy()
    
    # Process the texts in batches.
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i: i+batch_size]
        try:
            # Prepare the input for the embedding model.
            inputs = [TextEmbeddingInput(text=t, task_type="RETRIEVAL_DOCUMENT") for t in batch_texts]
            embeddings = model.get_embeddings(inputs)

            # Add the generated embedding vector to each chunk in the batch.
            for j, embedding in enumerate(embeddings):
                updated_chunks[i+j]["embedding"] = embedding.values
                
            time.sleep(0.1)
        except Exception as e:
            logger.error(f"Failed to genreate embeddings for batch {i}: {e}")
            pass    #if a batch fails, proceed without embeddings instead of failing the whole job
        
    return updated_chunks
    
# --- Core processors ---
def process_elements_to_chunks(elements, max_words: int = DEFAULT_MAX_TOKENS) -> list[dict[str, Any]]:
    """
    Converts a list of unstructured elements into a list of normalized,
    sentence-split chunks, each represented as a dictionary.
    """
    final_chunks: list[dict[str, Any]] = []
    order = 1

    for el in elements:
        text = getattr(el, "text", None)
        if not text:
            continue

        # Extract metadata from the element, such as its type and page number.
        element_type = getattr(el, "category", None) or type(el).__name__
        page_number = None
        meta = getattr(el, "metadata", None)
        if meta is not None:
            page_number = getattr(meta, "page_number", None)

        # Normalize the text and split it into sentences.
        element_text = normalize_text(text)
        for sentence in safe_sent_tokenize(element_text):
            # If a sentence is too long, split it into smaller parts.
            parts = split_long_chunk(sentence, max_words) if len(sentence.split()) > max_words else [sentence]
            for p in parts:
                # Append the final chunk dictionary to the list.
                final_chunks.append({
                    "chunk_id": str(uuid.uuid4()),
                    "chunk_text": p,
                    "word_count": len(p.split()),
                    "chunk_order": order,
                    "element_type": element_type,
                    "page_number": page_number,
                })
                order += 1

    return final_chunks

def process_file_path(file_path: str, *, max_words: int = DEFAULT_MAX_TOKENS) -> list[dict[str, Any]]:
    """
    Processes file from local path  with the 'unstructured' library
    and converting the result into a list of chunks.
    """
    _, ext = os.path.splitext(file_path)
    # Validate the file extension against the list of supported types.
    if ext.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: '{ext}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")

    # Check if the file size exceeds the defined maximum.
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise ValueError(f"File too large ({size_mb:.1f}MB) > {MAX_FILE_SIZE_MB}MB")

    if partition is None:
        raise RuntimeError("unstructured is not installed or failed to import")

    # Use 'unstructured' to process the document into a list of elements.
    elements = partition(filename=file_path, strategy="hi_res")
    # Convert the elements into chunks
    return process_elements_to_chunks(elements, max_words=max_words)

def process_file_bytes(data: bytes, content_type: str | None = None, *, max_words: int = DEFAULT_MAX_TOKENS) -> list[dict[str, Any]]:
    """
    Processes a file provided as in-memory bytes  with the 'unstructured' library
    and converting the elements into a list of chunks.
    """
    if partition is None:
        raise RuntimeError("unstructured is not installed or failed to import")

    from io import BytesIO
    # Use 'unstructured' to process the document into a list of elements.
    elements = partition(file=BytesIO(data), content_type=content_type)
    # Convert the elements into chunks
    return process_elements_to_chunks(elements, max_words=max_words)







