"""
This FastAPI app runs a document-parsing workflow. The /parse-document endpoint:
  1. Downloads the input file from GCS to a temp file.
  2. Uses the unstructured library to break it into clean text chunks.
  3. Generates vector embeddings for each chunk (for RAG).
  4. Saves the parsed chunks + embeddings to JSON.
  5. Uploads the result back to GCS and returns the output URI and status.
"""
import os
import tempfile
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import gcs_io
import doc_parser

# Initialize the FastAPI application.
app = FastAPI()

# --- Pydantic Models (API Contract) ---
# These models define the structure of the API's request and response bodies,
# ensuring that data is validated automatically by FastAPI.

class ParseRequest(BaseModel):
    """
    Defines the expected input for the parser API.
    """
    jobId: str
    source_gcs_uri: str # e.g., "gs://bucket-name/source-files/my-file.pdf"
    output_gcs_bucket: str # e.g., "bucket-name"

class ParseResponse(BaseModel):
    """
    Defines the output of the parser API.
    """
    status: str
    parsed_chunks_gcs_uri: str # e.g., "gs://bucket-name/parsed-output/job-123.json"
    message: str

# --- Helper Function ---

def get_file_extension(filename: str) -> str:
    """Helper to safely get a file extension."""
    return os.path.splitext(filename)[1].lower()

# --- API Endpoints ---

@app.get("/")
def read_root():
    """Health check endpoint to verify that the API is running."""
    return {"status": "Parser API is running"}

@app.post("/parse-document", response_model=ParseResponse)
async def parse_document(request: ParseRequest):
    """
    Main endpoint to download a file from GCS, parse it using
    unstructured, and upload the resulting chunks back to GCS.
    """
    print(f"Received parse request for job: {request.jobId}")
    
    try:
        # 1. Download the source file to a temporary location
        # Use the file extension so unstructured can identify it
        suffix = get_file_extension(request.source_gcs_uri)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as temp_file:
            print(f"Downloading {request.source_gcs_uri} to {temp_file.name}...")
            # The gcs_io helper handles the download from the GCS URI.
            gcs_io.download_blob_to_tempfile(request.source_gcs_uri, temp_file)
            temp_file.seek(0) # Rewind file after writing
            
            # 2. Parse the file using the correct function from doc_parser.py
            # This one function handles PDF, DOCX, and PPTX automatically.
            print(f"Parsing file {temp_file.name} with unstructured...")
            chunks = doc_parser.process_file_path(temp_file.name)
            
            if not chunks:
                raise HTTPException(status_code=500, detail="File was parsed, but no content chunks were extracted.")

            print(f"Successfully parsed {len(chunks)} chunks.")
            
            # 3. Generate vector embeddings for each chunk to be used in RAG.
            print("Generating vector embeddings for chunks")
            chunks_with_embeddings = doc_parser.generate_embeddings(chunks)
            print("COmpleted generating embeddings")

            # 4. Upload the parsed chunks (now with embeddings) back to GCS as a single JSON file.
            output_filename = f"parsed-output/{request.jobId}.json"
            print(f"Uploading parsed chunks with embeddings to gs://{request.output_gcs_bucket}/{output_filename}...")
            
            # The gcs_io helper handles the upload and returns the GCS URI of the new file.
            output_gcs_uri = gcs_io.upload_json_to_gcs(
                chunks_with_embeddings, 
                bucket_name=request.output_gcs_bucket,
                object_name=output_filename
            )
            
            print(f"Upload complete. GCS URI: {output_gcs_uri}")

            # 5. Return a successful response with the URI of the output file.
            return ParseResponse(
                status="success",
                parsed_chunks_gcs_uri=output_gcs_uri,
                message=f"Successfully parsed {len(chunks)} chunks with embeddings."
            )

    except Exception as e:
        print(f"Error during parsing for job {request.jobId}: {e}")
        # In case of any error, return a failure response
        return ParseResponse(
            status="error",
            parsed_chunks_gcs_uri="",
            message=str(e)
        )

# This block allows the script to be run locally.
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)