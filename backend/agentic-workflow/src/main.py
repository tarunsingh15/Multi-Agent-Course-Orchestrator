# Note: This code was generated with Google's Gemini. The program was reviewed, modified, and tested to
# ensure functionality.
"""
main.py
-------
This file serves as the primary entry point for the agentic workflow. It contains a
Google Cloud Function (`firestore_handler`) that is triggered by Firestore events
via Eventarc.

Core Logic:
1.  **Trigger**: The function is invoked whenever a document in the `jobs/{jobId}`
    collection in Firestore is created or updated.
2.  **Event Parsing**: It parses the incoming CloudEvent to extract the `jobId`
    of the affected document. It's designed to handle multiple event formats for
    flexibility.
3.  **Data Fetching**: The event payload itself is minimal. The function uses the
    `jobId` to fetch the full job document directly from Firestore. This ensures
    the agent always works with the most up-to-date data.
4.  **ADK Setup**: It initializes the ADK `Runner` and an `InMemorySessionService`.
    Crucially, it creates a new session for the current `jobId` and injects the
    full `job_document` into the session's initial state.
5.  **Execution**: It starts the ADK `Runner` with the `OrchestratorAgent` as the
    top-level agent. The `OrchestratorAgent` then takes over, reading the job
    document from the session state and beginning the routing process.

This event-driven architecture allows the system to be reactive and stateful.
Each step in the workflow can be a distinct state in Firestore, and any update
to that state can re-trigger this entry point to drive the job to its next stage.
"""
import asyncio
import logging
import os
import re
#The functions_framework library is used to define and run Google Cloud Functions.
import functions_framework
from datetime import datetime
from cloudevents.http import CloudEvent

from google.cloud import firestore
from google.adk.runners import InMemorySessionService, Runner
from google.genai import types

from agents.orchestrator_agent import OrchestratorAgent
# --- Configuration ---
#Load settings from environment variables with sensible defaults.
APP_NAME = os.getenv("APP_NAME", "agentic-workflow")
USER_ID = os.getenv("USER_ID", "system")
DEFAULT_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "amazing-math-473517-f9")
# Hard-coded profile ID that we want to fetch
PROFILE_ID = "AYrTvroL62Z3uKhne9Yt"


# --- Logging Setup ---
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# --- Regular Expressions for Event Parsing ---
FULL_SUBJECT_RE = re.compile(
    r"^projects/(?P<project>[^/]+)/databases/\(default\)/documents/jobs/(?P<jobId>[^/]+)$"
)
SHORT_SUBJECT_RE = re.compile(
    r"^documents/jobs/(?P<jobId>[^/]+)$"
)

def _parse_subject(subject: str, fallback_project: str | None) -> tuple[str | None, str | None]:
    """
    Parses the 'subject' from a Firestore CloudEvent to extract the project and job ID.
    The 'subject' is a string inside the event data that gcloud sends whena Firestore document changes
    to specify a unique id for that specific document
    """
    # Tries to match the full subject format, which includes the project ID.
    m = FULL_SUBJECT_RE.match(subject)
    if m:
        return m.group("project"), m.group("jobId")

    # If the full format doesn't match, tries a shorter format and uses a fallback project.
    m = SHORT_SUBJECT_RE.match(subject)
    if m:
        return fallback_project, m.group("jobId")

    # Returns None if no match is found.
    return None, None


async def _run_orchestrator_for_job(db: firestore.Client, job_dict: dict) -> None:
    """
    Sets up and runs the OrchestratorAgent for a specific job.
    """
    # HARD STOP for old jobs before ADK runner
    # This is a safeguard to prevent processing jobs that might be stuck or outdated.
    created_at = job_dict.get("createdAt")
    if created_at:
        try:
            age_seconds = (datetime.utcnow() - created_at.replace(tzinfo=None)).total_seconds()
            if age_seconds > 1800:  # 30 minutes
                logging.info(f"[MAIN] Ignoring OLD job {job_dict.get('jobId')} ({age_seconds} seconds old).")
                return
        except Exception as e:
            logging.warning(f"[MAIN] Could not compute job age for {job_dict.get('jobId')}: {e}")

    job_id = job_dict["jobId"]

    # Fetch learner profile if it's not already in the job document.
    profile_data = job_dict.get("learnerProfile")
    if not profile_data:
        logger.info(f"Job {job_id} missing profile, fetching.")
        try:
            # Fetches a hard-coded profile from the 'profiles' collection.
            profile_copy = db.collection("profiles").document(PROFILE_ID).get()
            if profile_copy.exists:
                profile_data = profile_copy.to_dict()
                logger.info(f"Successfully fetched profile {PROFILE_ID}")

                # Saves a copy of the profile to the job document for future use.
                db.collection("jobs").document(job_id).set(
                    {"learnerProfile": profile_data}, merge=True
                )
                logger.info(f"Saved copy of profile to job {job_id}")
            else:
                logger.warning(f"Profile document {PROFILE_ID} not found.")
                profile_data = {}
        except Exception as e:
            logger.error(f"Failed to fetch profile {PROFILE_ID}: {e}")
            profile_data = {}
    else:
        logger.info(f"Job {job_id} already has learner profile.")

    # Create session ONCE — do NOT overwrite it
    # Initializes the session service and the main orchestrator agent.
    session_service = InMemorySessionService()
    orchestrator = OrchestratorAgent()

    # Creates a new session for the job, injecting the job document and learner profile
    # into the session's state. This makes the data available to all sub-agents.
    await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=job_id,
        state={
            "job_document": job_dict,
            "learner_profile": profile_data,
        },
    )

    # The Runner is the main execution engine of the ADK.
    runner = Runner(agent=orchestrator, app_name=APP_NAME, session_service=session_service)
    # A system message is created to trigger the agent's execution loop.
    msg = types.Content(role="system", parts=[types.Part(text="firestore-trigger")])

    # The runner is started asynchronously, processing events from the agent.
    async for event in runner.run_async(
        user_id=USER_ID, session_id=job_id, new_message=msg
    ):
        logger.info("ADK event: %s", event)


@functions_framework.cloud_event
def firestore_handler(event: CloudEvent):
    """
    Eventarc -> Cloud Run entrypoint for Firestore 'document created' on jobs/{jobId}.
    """
    # Extracts the subject from the CloudEvent to identify the affected document.
    subject = event.get("subject", "") or ""
    project, job_id = _parse_subject(subject, DEFAULT_PROJECT)

    if not job_id:
        logger.info("Ignoring non-jobs subject (no jobId parsed): %s", subject)
        return "ignored"

    project = project or DEFAULT_PROJECT
    if not project:
        logger.error("No project available for Firestore read (subject=%s)", subject)
        return "error: no project"

    logger.info("Received Firestore event for jobs/%s (project=%s)", job_id, project)

    # Initializes the Firestore client and fetches the full job document.
    db = firestore.Client(project=project)
    snap = db.collection("jobs").document(job_id).get()
    if not snap.exists:
        logger.warning("Job doc not found: jobs/%s (project=%s)", job_id, project)
        return "not_found"

    job_data = snap.to_dict() or {}
    job_data.setdefault("jobId", job_id)
    # --- Execution ---
    # `functions_framework` provides a synchronous entry point, but our ADK
    # runner is asynchronous. `asyncio.run()` is used to start the async
    # event loop and run our orchestrator function until it completes.
    asyncio.run(_run_orchestrator_for_job(db, job_data))
    return "ok"