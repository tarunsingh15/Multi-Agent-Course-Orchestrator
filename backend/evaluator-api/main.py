"""
Provides FastAPI endpoints to run and retrieve content evaluations:

POST /jobs/{job_id}/evaluate
Starts lesson or quiz evaluation in the background (async), returning 202 Accepted immediately.

GET /jobs/{job_id}/evaluation
Polls job status: returns 202 if still processing, or the final evaluation JSON from GCS once ready.
"""
import os
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from google.cloud import firestore
from agents.evaluation_agent import evaluate_job
from utils.gcs_io import download_json_from_uri
from pydantic import BaseModel

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "amazing-math-473517-f9")
app = FastAPI(title="Evaluation API")

class EvaluationRequest(BaseModel):
    """Defines the request body for triggering an evaluation."""
    scope: str
    
@app.post("/jobs/{job_id}/evaluate", status_code=202)
async def trigger_evaluation(job_id: str, body: EvaluationRequest, background_tasks: BackgroundTasks):
    """
    Triggers a background task to evaluate course content (lessons or quizzes).
    
    This endpoint immediately returns a 202 response and processes the evaluation
    asynchronously to avoid blocking the calling service.
    """
    if body.scope not in ["lessons", "quiz"]:
        raise HTTPException(status_code=400, detail="Invalid scope.")
    background_tasks.add_task(evaluate_job, job_id, body.scope)
    return {"message":  f"Evalation started for job {job_id} with scope: {body.scope}"}

@app.get("/jobs/{job_id}/evaluation")
async def get_evaluation(job_id: str):
    """
    Retrieves the evaluation results for a given job.
    
    It checks the job status and returns the results if complete, or a status
    update if the evaluation is still in progress.
    """
    db = firestore.Client(project=PROJECT_ID)
    job_ref = db.collection("jobs").document(job_id)
    job_doc = job_ref.get()
    
    if not job_doc.exists:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job_data = job_doc.to_dict() or {}
    results = job_data.get("results", {})
    eval_uri = results.get("evaluation_gcs_uri")
    status = job_data.get("status", "")
    
    # If the evaluation URI doesn't exist or the final status isn't set,
    # check if it's still being processed.
    if not eval_uri or status != "EVALUATION_COMPLETE":
        # These statuses indicate the evaluation is running or pending.
        if status in ("PROCESSING_EVALUATION", "PROCESSING_QUIZ_AND_EVAL", "LESSON_GENERATED", "QUIZ_GENERATED", "LESSON_EVALUATED"):
            return JSONResponse(status_code=202, content= {"message" : f"Evaluation in progres. Status = {status}"})
        # If not in progress, the evaluation is not available.
        return JSONResponse(status_code=404, content= {"message": f"Evaluation not found. Status = {status}"})
    
    try:
        # If the evaluation is complete, download the results from GCS.
        evaluation = download_json_from_uri(eval_uri)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    # Return the full evaluation data.
    return evaluation