"""
FastAPI app with endpoints to:
  Start quiz generation from a course blueprint (async)
  Retrieve the generated quiz JSON from GCS
  Check job generation status
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import firestore, storage
from agents.quiz_utils import generate_quiz_from_blueprint, _download_json_from_gcs
import os
import logging

# Set up project ID and initialize the FastAPI application.
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "amazing-math-473517-f9")
app = FastAPI(title="Quiz Generator API")

# Configure basic logging.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/jobs/{job_id}/generate_quiz", status_code=status.HTTP_202_ACCEPTED)
def generate_quiz(job_id: str, background_tasks: BackgroundTasks):
    """
    Initiates the quiz generation process for a given job ID.
    The actual generation is run as a background task to prevent blocking.
    """
    if not job_id:
        raise HTTPException(status_code=400, detail="Job ID REQUIRED")
    
    try:
        logger.info(f"Starting quiz generation for job: {job_id}")
        # Add the long-running quiz generation function to the background tasks.
        background_tasks.add_task(generate_quiz_from_blueprint, job_id)
        
        # Immediately return a response to the client.
        return {
            "message": "Quiz generation job accepted and processing in background",
            "jobId": job_id,
        }
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.exception(f"Error generation quiz. jobId = {job_id}: {e}")
        
        raise HTTPException(status_code=500, detail={"error": str(e), "trace": tb})
    
@app.get("/jobs/{job_id}/quiz")
def get_quiz(job_id: str):
    """
    Retrieves the generated quiz JSON from GCS for a given job.
    This endpoint is called by the new frontend UI component.
    """
    if not job_id:
        raise HTTPException(status_code=400, detail="Job ID is required.")

    db = firestore.Client(project=PROJECT_ID)
    storage_client = storage.Client()
    
    try:
        # Fetch the job document from Firestore to find the quiz URI.
        job_doc = db.collection("jobs").document(job_id).get()
        if not job_doc.exists:
            raise HTTPException(status_code=404, detail="Job not found")

        job_data = job_doc.to_dict()
        quiz_gcs_uri = job_data.get("results", {}).get("quiz_gcs_uri")
        
        if not quiz_gcs_uri:
            # If the URI doesn't exist, check the job status.
            status = job_data.get("status")
            # If the job is still in a processing state, inform the client.
            if status in ("PROCESSING_QUIZ", "LESSON_GENERATED", "BLUEPRINT_COMPLETE", "REVIEW_COMPLETE", "PROCESSING_LESSONS"):
                 raise HTTPException(status_code=202, detail=f"Quiz not ready. Current status: {status}")
            
            # If processing is finished and still no URI, the quiz is not available.
            raise HTTPException(status_code=404, detail="No quiz URI found for this job. Status: {status}")

        # If the URI exists, download the quiz data from GCS.
        logger.info(f"Fetching quiz data from GCS for job {job_id}")
        quiz_data = _download_json_from_gcs(quiz_gcs_uri, storage_client)
        return quiz_data

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.exception(f"Error retrieving quiz for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail={"error": str(e), "trace": tb})
    
@app.get("/jobs/{job_id}/quiz/status")
def get_quiz_status(job_id: str):
    """
    Provides a lightweight endpoint to check the current status of a job.
    Useful for frontend polling.
    """
    db = firestore.Client()

    job_ref = db.collection("jobs").document(job_id)
    job_doc = job_ref.get()

    if not job_doc.exists:
        raise HTTPException(status_code=404, detail="Job not found")

    data = job_doc.to_dict()
    status = data.get("status", "UNKNOWN")

    return {"status": status}
