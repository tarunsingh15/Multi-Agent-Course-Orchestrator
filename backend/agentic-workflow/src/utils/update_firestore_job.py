# Overview:
# - A tiny helper to update a job document in Firestore by jobId.
# - Minimizes Firestore-specific code strewn throughout agents.
#
# Signature:
#   update_job(job_id: str, status: str | None, results: dict | None, error: str | None)
#
# Behavior:
# - Always sets 'updatedAt' to the current UTC timestamp (server-side notion of "progress").
# - Conditionally merges:
#    - 'status' if provided (e.g., PENDING → PROCESSING_PARSER → PARSING_COMPLETE)
#    - 'results' if provided (e.g., {"parse_results": {"chunks": [...]}})
#    - 'error' if provided (used when agents fail)
#
# Why set(merge=True)?
# - To preserve the rest of the job document created by the frontend (inputs, createdAt, etc.)
#   and to avoid overwriting fields that other steps might have written.
#
# This separation keeps Firestore concerns out of agent logic, making agents easier to test.
# Note: This code was generated with Google's Gemini. The program was reviewed, modified, and tested to
# ensure functionality.


from google.cloud import firestore
from datetime import datetime, timezone

db = firestore.Client()

def update_job(job_id: str, status: str = None, results: dict = None, error: str = None, msg: str = None, **kwargs):
    updates = {
        "updateLog": firestore.ArrayUnion([{
            "time": datetime.now(timezone.utc),
            "message": msg or f"Status update: {status}"
        }])
    }
    
    if status:
        updates["status"] = status
    if results is not None:
        updates["results"] = results
    if error is not None:
        updates["error"] = error

    if kwargs:
        updates.update(kwargs)

    db.collection("jobs").document(job_id).set(updates, merge=True)
