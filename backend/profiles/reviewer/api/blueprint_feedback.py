"""
FastAPI router for blueprint review:
  Fetch the current blueprint for a job from GCS
  Submit approval or revision feedback

Feedback updates the job status in Firestore, triggering the next workflow step.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from google.cloud import firestore
from google.cloud import storage
from urllib.parse import unquote
import json
# this is work done to connect the blueprint to the backend so when the user
# submits feedback the blueprint changes.
# this code will run when the backend connects to the blueprint to allow changes

router = APIRouter(tags=["blueprint"])
db = firestore.Client()
BUCKET_NAME = 'mari-uploads-ns-uc1-east4'

def _jobs_collection():
    """Initialize Firestore client and return a reference to the 'jobs' collection."""
    db = firestore.Client()
    return db.collection("jobs")

class Feedback(BaseModel):
    """
    Pydantic model for validating the feedback request body.
    """
    reviewer_id: str
    reviewer_name: str
    decision: str        # either approve or revise the blueprint based on user decision
    comments: str

@router.get("/{job_id}")
def get_blueprint(job_id: str):
    """
    Retrieves the course blueprint JSON for a given job ID.
    The blueprint's location is stored as a GCS URI in the job document.
    """
    coll = _jobs_collection()
    doc = coll.document(job_id).get()
    data = doc.to_dict()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # fetch blueprint from GCS
    storage_client = storage.Client()

    blueprint_uri: str = data.get("results", {}).get("blueprint_gcs_uri")
    if not blueprint_uri:
        raise HTTPException(status_code=404, detail="No blueprint URI found")

    # Parse the GCS URI to get the bucket and blob name.
    if blueprint_uri.startswith("https://storage.googleapis.com/"):
        parts = blueprint_uri.replace("https://storage.googleapis.com/", "").split("/", 1)
        bucket_name = parts[0]
        blob_name = parts[1]
    elif blueprint_uri.startswith(f"gs://{BUCKET_NAME}/"):
        blob_name = blueprint_uri.split(f"{BUCKET_NAME}/")[-1]
        bucket_name = BUCKET_NAME
    else:
        raise HTTPException(status_code=400, detail="Invalid blueprint URI format")

    # Download and parse the blueprint JSON from GCS.
    bucket = storage_client.bucket(bucket_name)
    blob_name = unquote(blob_name)
    blob = bucket.blob(blob_name)

    try:
        blueprint = json.loads(blob.download_as_text())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download or parse blueprint: {str(e)}")
    
    if not blueprint:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    
    return blueprint

@router.post("/{job_id}/feedback", status_code=status.HTTP_201_CREATED)
def post_feedback(job_id: str, body: Feedback):
    """
    Records a reviewer's feedback for a blueprint and updates the job status.
    """
    coll = _jobs_collection()
    ref = coll.document(job_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Job not found")

    # Determine the new job status and log message based on the reviewer's decision.
    if body.decision.lower() == "approved":
        msg = "Blueprint approved by reviewer, will begin generating lessons"
    else:
        msg = "Blueprint revision requested by reviewer, agent will now revise blueprint"

    ref.update({
        "results.reviewer_feedback": body.model_dump(),
        "status": "REVIEW_COMPLETE" if body.decision.lower() == "approved" else "REVISION_REQUESTED",
        "updateLog": firestore.ArrayUnion([{
            "time": datetime.now(timezone.utc),
            "message": msg
        }])
    })

    return {"message": f"Feedback for job {job_id} recorded successfully"}
