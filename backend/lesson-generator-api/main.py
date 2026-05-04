"""
FastAPI service for generating, revising, and retrieving lessons, and logging quiz attempts.

Key endpoints:

  POST /jobs/{job_id}/generate_lessons — Create lessons from a course blueprint.

  POST /jobs/{job_id}/revise_lesson — Revise a specific lesson using critique feedback.

  GET /jobs/{job_id}/lessons — Fetch generated Markdown lessons from GCS.

  POST /jobs/{job_id}/quizAttempts — Log a user's quiz attempt to Firestore.
"""
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import firestore, storage
from datetime import datetime, timezone
from agents.lessons_utils import generate_lessons_from_blueprint, revise_single_lesson
import os
from urllib.parse import unquote
from pydantic import BaseModel

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "amazing-math-473517-f9")
BUCKET_NAME = 'mari-uploads-ns-uc1-east4'

# Initialize the FastAPI application.
app = FastAPI(title="Lesson Generator API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://react-frontend-536653873539.us-east4.run.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define the request body for our revision endpoint
class RevisionRequest(BaseModel):
    module_title: str
    critique_reasoning: str

@app.options("/jobs/{job_id}/generate_lessons")
def options_generate_lessons(job_id: str):
    return Response(status_code=200)

@app.post("/jobs/{job_id}/generate_lessons")
def generate_lessons(job_id: str):
    """
    Triggers the generation of all lesson modules for a given job ID.
    """
    try:
        # Call the main orchestration function from lessons_utils.
        result = generate_lessons_from_blueprint(job_id)
        return {
            "message": "Lesson Markdown generated and uploaded",
            "modules": list(result["lesson_uris"].keys()),
            "uris": result["lesson_uris"],
        }
    except Exception as e:
        # Provide detailed error information if the generation fails.
        import traceback
        tb = traceback.format_exc()
        print("Error generating lessons:\n", tb)
        return {"error": str(e), "trace": tb}
    
@app.post("/jobs/{job_id}/revise_lesson")
def revise_lesson(job_id: str, body: RevisionRequest):
    """
    Triggers the revision of a single lesson module based on feedback.
    """
    try:
        # Call the revision function with the job ID and feedback from the request body.
        result = revise_single_lesson(
            job_id=job_id,
            module_title=body.module_title,
            critique_reasoning=body.critique_reasoning
        )
        return {
            "message": "Lesson revision complete",
            "module_title": body.module_title,
            "details": result.get("message")
        }
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Error revising lesson {body.module_title}:\n", tb)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/jobs/{job_id}/lessons")
def get_lessons(job_id: str):
    """
    Retrieves the Markdown content of all lessons for a given job ID from GCS.
    """
    db = firestore.Client(project=PROJECT_ID)
    job_doc = db.collection("jobs").document(job_id).get()
    if not job_doc.exists:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get the GCS URIs for the lessons from the job document.
    job_data = job_doc.to_dict()
    lesson_uris = job_data.get("results", {}).get("lesson_gcs_uris")
    if not lesson_uris:
        raise HTTPException(status_code=404, detail="No lessons found")

    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)

    # Download the content of each lesson from its GCS URI.
    lesson_markdown_by_module = {}
    for module, uri in lesson_uris.items():
        blob_name = uri.split(f"{BUCKET_NAME}/")[-1]
        blob_name = unquote(blob_name)  
        blob = bucket.blob(blob_name)
        lesson_markdown_by_module[module] = blob.download_as_text()

    return {"lesson_markdown_by_module": lesson_markdown_by_module}

@app.post("/jobs/{job_id}/quizAttempts")
def log_quiz_attempt(job_id: str, attempt: dict):
    """
    Logs the details of a user's quiz attempt to Firestore for analytics.
    """
    db = firestore.Client()
    job_ref = db.collection("jobs").document(job_id)

    # Structure the quiz attempt data.
    attempt_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "moduleTitle": attempt.get("moduleTitle"),
        "score": attempt.get("score"),
        "total": attempt.get("total"),
        "percentage": attempt.get("percentage"),
        "passed": attempt.get("passed"),
        "attemptNumber": attempt.get("attemptNumber"),
    }

    # Add the new attempt to an array field in the job document.
    job_ref.update({
        "quizAttempts": firestore.ArrayUnion([attempt_record])
    })

    return {"status": "logged", "attempt": attempt_record}