"""
Central FastAPI app that combines endpoints for user profiles, blueprint feedback, and session management.

Key endpoints:
  GET /jobs/{job_id} — Retrieve job data from Firestore
  GET /ping — Health check

Routers included:
  /profiles — User profile operations
  /blueprint — Blueprint review + feedback
  /session — Session and user ID mapping
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.profiles import router as profiles_router
from api.session import router as session_router
from reviewer.api.blueprint_feedback import router as blueprint_router
from google.cloud import firestore

app = FastAPI(title="Profiles + Reviewer API")
db = firestore.Client()

@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    """Return the full job document from Firestore."""
    # Retrieve a specific job document by its ID from the 'jobs' collection.
    doc = db.collection("jobs").document(job_id).get()
    if not doc.exists:
        return {"error": "Job not found"}
    # Convert the document to a dictionary and return it.
    return doc.to_dict()


# Include the routers from different modules
app.include_router(profiles_router, prefix="/profiles", tags=["profiles"])
app.include_router(blueprint_router, prefix="/blueprint", tags=["blueprint"])
app.include_router(session_router,prefix="/session", tags= ["session"]) # email -> UID mapping

@app.get("/ping")
def health_check():
    """A simple health check endpoint to confirm the API is running."""
    return {"status": "OK"}

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)