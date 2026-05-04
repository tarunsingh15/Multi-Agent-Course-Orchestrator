from __future__ import annotations
# Note: This code was generated with Google's Gemini. The program was reviewed, modified, and tested to
# ensure functionality.
"""
OrchestratorAgent
-----------------
This file defines the OrchestratorAgent, the central "manager" or "router" agent
for the entire workflow. It acts as a state machine, driving the job forward by
delegating tasks to specific "worker" sub-agents based on the job's current
`status` field.

Core Logic:
1.  **Input**: Like other agents, it reads the `job_document` from the ADK session
    state, which was placed there by the entrypoint (`main.py`).
2.  **Routing**: It implements conditional logic based on the `job.status`:
    -   If `status` is "PENDING", it knows this is a new job. It invokes the
        `ParserAgent` to begin processing.
    -   If `status` is "PARSING_COMPLETE", it knows the first step is done. The
        current code treats this as a no-op but marks the spot where the *next*
        agent (e.g., a `BlueprintGeneratorAgent`) would be called.
    -   If `status` is "FAILED" or any other unhandled state, it stops execution
        for that job to prevent further processing.
3.  **Composition**: This agent is composed of other agents (like `ParserAgent`),
    which it holds as `sub_agents`. This composition is the core of the ADK
    framework, allowing complex workflows to be built from smaller, reusable,
    and testable components.

It intentionally does not perform business logic (like parsing or calling LLMs).
Its sole purpose is to direct the flow of the operation.
"""

from typing import AsyncGenerator, Dict, Any
from typing_extensions import override
import logging
import os
import httpx
import json
from google.cloud import storage

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from utils.update_firestore_job import update_job

logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
PROJECT_ID_SUFFIX = "536653873539" 

QUIZ_API_URL = f"https://quiz-generator-api-{PROJECT_ID_SUFFIX}.us-east4.run.app"
EVAL_API_URL = f"https://evaluator-api-{PROJECT_ID_SUFFIX}.us-east4.run.app"
PARSER_API_URL = os.environ.get("PARSER_API_URL", f"https://document-parser-api-{PROJECT_ID_SUFFIX}.us-east4.run.app")
BLUEPRINT_API_URL = os.environ.get("BLUEPRINT_API_URL", f"https://blueprint-generator-api-{PROJECT_ID_SUFFIX}.us-east4.run.app")
LESSON_API_URL = os.environ.get("LESSON_API_URL", f"https://lesson-generator-api-{PROJECT_ID_SUFFIX}.us-east4.run.app")

def _download_json_from_gcs(gcs_uri: str, storage_client: storage.Client) -> Dict[str, Any]:
    """Downloads a JSON blob from GCS."""
    try:
        if gcs_uri.startswith("gs://"):
            parts = gcs_uri[5:].split("/", 1)
            bucket_name, blob_name = parts[0], parts[1]
        elif "storage.googleapis.com" in gcs_uri:
            parts = gcs_uri.replace("https://storage.googleapis.com/", "").split("/", 1)
            bucket_name, blob_name = parts[0], parts[1]
        else:
            raise ValueError(f"Invalid GCS URI: {gcs_uri}")
        
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if not blob.exists():
            raise FileNotFoundError(f"GCS object not found: {gcs_uri}")
        return json.loads(blob.download_as_text())
    except Exception as e:
        logger.exception(f"Failed to download or parse JSON from {gcs_uri}")
        raise

def _get_bucket_from_uri(uri: str) -> str:
    """Helper to extract bucket name from gs:// URI"""
    if not uri or not uri.startswith("gs://"):
        return ""
    return uri.replace("gs://", "").split("/")[0]

class OrchestratorAgent(BaseAgent):
    """
    Acts as a state machine, routing a job to the appropriate sub-agent.
    """
    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, name: str = "OrchestratorAgent") -> None:
        super().__init__(name=name, sub_agents=[])

    @override
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator:
        job: Dict[str, Any] = (ctx.session.state or {}).get("job_document") or {}
        profile: Dict[str, Any] = (ctx.session.state or {}).get("learner_profile") or {}
        job_id = job.get("jobId")
        status = job.get("status")

        if not job_id:
            logger.error("[Orchestrator] No jobId in job_document")
            yield {"type": "orchestrator_error", "message": "Missing jobId"}
            return
            
        if profile:
            logger.info(f"Job {job_id} started with learner profile: {list(profile.keys())}")
        
        # --- Terminals ---
        # These are the final states of the job. If a job reaches one of these,
        # the orchestrator's work for this job is done.
        if status == "EVALUATION_COMPLETE":
            logger.info(f"[Orchestrator] Job {job_id} fully processed.")
            yield {"type": "orchestrator_done", "jobId": job_id}
            return
        
        if status == "FAILED":
            logger.warning(f"[Orchestrator] Job {job_id} already FAILED.")
            return
        
        # --- STEP 1: PARSING ---
        # If the job is new ("PENDING"), start the parsing process by calling the
        # document-parser-api.
        if status == "PENDING":
            update_job(job_id, status="PROCESSING", msg="Orchestrator triggering document-parser-api")
            
            try:
                inputs = job.get("inputs", {})
                source_uri = inputs.get("originalSyllabusGcsUri") or job.get("gcs_uri")
                
                # Derive bucket from the source URI if not explicitly provided
                output_bucket = job.get("gcs_bucket")
                if not output_bucket and source_uri:
                    output_bucket = _get_bucket_from_uri(source_uri)
                
                if not source_uri or not output_bucket:
                    raise Exception(f"Missing 'gcs_uri' or 'gcs_bucket'. Inputs: {inputs}")

                # Prepare the payload for the parser API.
                payload = {
                    "jobId": job_id,
                    "source_gcs_uri": source_uri,
                    "output_gcs_bucket": output_bucket
                }
                
                # Call the document parser API asynchronously.
                async with httpx.AsyncClient() as client:
                    response = await client.post(f"{PARSER_API_URL}/parse-document", json=payload, timeout=300.0) 
                
                if response.status_code != 200:
                    raise Exception(f"Parser API failed: {response.status_code} {response.text}")

                api_result = response.json()
                if api_result.get("status") == "error":
                    raise Exception(f"Parser API error: {api_result.get('message')}")
                
                parsed_chunks_gcs_uri = api_result.get("parsed_chunks_gcs_uri")
                
                # Save results AND the inferred bucket for future steps
                update_job(
                    job_id,
                    status="PARSING_COMPLETE",
                    msg="Document parsing complete.",
                    results={"parsed_chunks_gcs_uri": parsed_chunks_gcs_uri},
                    gcs_bucket=output_bucket 
                )
                yield {"type": "parser_api_success", "jobId": job_id}
                
            except Exception as e:
                logger.exception(f"Parser step failed for {job_id}")
                update_job(job_id, status="FAILED", error=f"Parser API call failed: {str(e)}")
                yield {"type": "parser_api_failed", "jobId": job_id, "error": str(e)}
            return
            
        # --- STEP 2: BLUEPRINT GENERATION ---
        # If parsing is complete or a revision was requested, generate or revise the blueprint.
        if status in ("PARSING_COMPLETE", "REVISION_REQUESTED"): 
            logger.info(f"[Orchestrator] Job {job_id} status is {status}, triggering blueprint.")
            
            update_job(job_id, status="PROCESSING_BLUEPRINT", msg="Orchestrator requesting blueprint...")
            
            try:
                inputs = job.get("inputs", {})
                context = inputs.get("context")
                job_results = job.get("results", {})
                parsed_chunks_gcs_uri = job_results.get("parsed_chunks_gcs_uri")

                # Ensure an output bucket is available.
                output_bucket = job.get("gcs_bucket")
                if not output_bucket:
                     source_uri = inputs.get("originalSyllabusGcsUri")
                     output_bucket = _get_bucket_from_uri(source_uri)

                if not parsed_chunks_gcs_uri or not output_bucket:
                    raise Exception(f"Missing parsed_chunks_gcs_uri or output_bucket. Bucket: {output_bucket}")

                endpoint_url = ""
                payload = {}

                # If parsing is complete, generate a new blueprint.
                if status == "PARSING_COMPLETE":
                    endpoint_url = f"{BLUEPRINT_API_URL}/generate"
                    payload = {
                        "jobId": job_id,
                        "parsed_chunks_gcs_uri": parsed_chunks_gcs_uri,
                        "output_gcs_bucket": output_bucket,
                        "learnerProfile": profile,
                        "context": context
                    }
                
                # If a revision is requested, revise the existing blueprint.
                elif status == "REVISION_REQUESTED":
                    endpoint_url = f"{BLUEPRINT_API_URL}/revise"
                    current_blueprint_gcs_uri = job_results.get("blueprint_gcs_uri")
                    
                    feedback_data = job_results.get("reviewer_feedback", {})
                    feedback = feedback_data.get("comments")

                    if not current_blueprint_gcs_uri or not feedback:
                        raise Exception("Missing 'blueprint_gcs_uri' or 'feedback' for revision")
                    
                    payload = {
                        "jobId": job_id,
                        "feedback": feedback,
                        "current_blueprint_gcs_uri": current_blueprint_gcs_uri,
                        "parsed_chunks_gcs_uri": parsed_chunks_gcs_uri,
                        "output_gcs_bucket": output_bucket,
                        "learnerProfile": profile,
                        "context": context
                    }

                # Call the blueprint API.
                async with httpx.AsyncClient() as client:
                    response = await client.post(endpoint_url, json=payload, timeout=300.0) 
                
                if response.status_code != 200:
                    raise Exception(f"Blueprint API failed: {response.status_code} {response.text}")

                api_result = response.json()
                if api_result.get("status") == "error":
                    raise Exception(f"Blueprint API error: {api_result.get('message')}")
                
                # Update the job with the new blueprint URI.
                new_blueprint_gcs_uri = api_result.get("blueprint_gcs_uri")
                merged_results = {**job_results, "blueprint_gcs_uri": new_blueprint_gcs_uri}

                update_job(
                    job_id,
                    status="BLUEPRINT_COMPLETE",
                    msg="Blueprint generation complete.",
                    results=merged_results
                )
                yield {"type": "blueprint_api_success", "jobId": job_id}
                
            except Exception as e:
                logger.exception(f"Blueprint step failed for {job_id}")
                update_job(job_id, status="FAILED", error=f"Blueprint API call failed: {str(e)}")
                yield {"type": "blueprint_api_failed", "jobId": job_id, "error": str(e)}
            return
        
        # --- STEP 3: LESSON EVALUATION ---
        # After lessons are generated, trigger the evaluation process.
        if status == "LESSON_GENERATED":
            logger.info(f"[Orchestrator] Job {job_id} lessons complete, triggering eval.")
            update_job(job_id, status="PROCESSING_LESSON_EVAL", msg = "Orchestrator triggering lesson evaluation")
            
            try:
                # Call the evaluator API to start the evaluation.
                eval_url = f"{EVAL_API_URL}/jobs/{job_id}/evaluate"
                async with httpx.AsyncClient() as client:
                    eval_response = await client.post(eval_url, json={"scope": "lessons"}, timeout=30.0)
                    
                if eval_response.status_code != 202:
                    raise Exception(f"Lesson EVAL API failed: {eval_response.status_code}")
                
                yield {"type":"parallel_triggers_success", "jobId": job_id}
                
            except Exception as e:
                logger.exception(f"Eval trigger failed for {job_id}")
                update_job(job_id, status="FAILED", error=f"Eval API call failed: {str(e)}")
                yield {"type": "parallel_triggers_failed", "jobId": job_id, "error": str(e)}
            return
        
        # --- STEP 4: REVISION DECISION ---
        # After lesson evaluation, decide if a revision is needed based on scores.
        if status == "LESSON_EVALUATED":
            logger.info(f"[Orchestrator] Job {job_id} eval complete. Checking scores.")
            
            try:
                job_results = job.get("results", {})
                eval_uri = job_results.get("evaluation_gcs_uri")
                if not eval_uri:
                    raise Exception("Missing 'evaluation_gcs_uri'")

                # Download the evaluation results from GCS.
                storage_client = storage.Client()
                eval_data = _download_json_from_gcs(eval_uri, storage_client)
                
                retry_count = job.get("lessonRetryCount", 0)
                failed_modules = []

                # Iterate through evaluated modules to check for failures.
                for module_title, eval_scores in eval_data.get("modules", {}).items():
                    module_content = eval_scores.get("module_content", {})
                    if not module_content: continue
                    if "error" in module_content: continue 

                    # Robust score extraction
                    try:
                        metrics = {
                            "factual_accuracy": module_content.get("correctness", {}).get("factual_accuracy", {}).get("score", "fail"),
                            "clarity": module_content.get("clarity", {}).get("clarity_grammar", {}).get("score", 0),
                        }
                        # Simple fail check based on factual accuracy and clarity.
                        if metrics["factual_accuracy"] == "fail" or metrics["clarity"] < 3:
                             failed_modules.append({"title": module_title, "reason": "Low quality score"})
                    except Exception:
                        continue

                # If there are failed modules and the retry limit has not been reached,
                # trigger a revision for the failed modules.
                if failed_modules and retry_count < 3:
                    logger.warning(f"Job {job_id} requires revision. Attempt {retry_count + 1}")
                    
                    update_job(
                        job_id,
                        status="PROCESSING_REVISION",
                        lessonRetryCount=retry_count + 1,
                        msg=f"Starting revision attempt {retry_count + 1}."
                    )
                    
                    # Trigger revision for each failed module.
                    async with httpx.AsyncClient() as client:
                        for module in failed_modules:
                            payload = {"module_title": module['title'], "critique_reasoning": module['reason']}
                            await client.post(f"{LESSON_API_URL}/jobs/{job_id}/revise_lesson", json=payload, timeout=30.0)
                    
                    # Re-trigger evaluation after revision.
                    eval_url = f"{EVAL_API_URL}/jobs/{job_id}/evaluate"
                    async with httpx.AsyncClient() as client:
                        await client.post(eval_url, json={"scope": "lessons"}, timeout=30.0)
                    
                    yield {"type": "revision_loop_started", "jobId": job_id}

                else:
                    # If no failures or retry limit is reached, proceed to quiz generation.
                    update_job(job_id, status="LESSON_CRITIQUE_COMPLETE", msg="Proceeding to quiz.")
                    yield {"type": "revision_loop_complete", "jobId": job_id}

            except Exception as e:
                logger.exception(f"Revision loop failed for {job_id}")
                update_job(job_id, status="FAILED", error=f"Loop failed: {str(e)}")
                yield {"type": "revision_loop_failed", "jobId": job_id}
            return
        
        # --- STEP 5: QUIZ GENERATION ---
        # After lesson critique is complete, generate the quiz.
        if status == "LESSON_CRITIQUE_COMPLETE":
            update_job(job_id, status="PROCESSING_QUIZ_GEN", msg="Triggering quiz generation")
            
            try:
                # Call the quiz generator API.
                quiz_url = f"{QUIZ_API_URL}/jobs/{job_id}/generate_quiz"
                async with httpx.AsyncClient() as client:
                    resp = await client.post(quiz_url, timeout=30.0)
                
                if resp.status_code not in (200, 202):
                    raise Exception(f"Quiz API failed: {resp.status_code}")
                
                yield {"type" : "quiz_gen_trigger_success", "jobId": job_id}

            except Exception as e:
                logger.exception(f"Quiz trigger failed {job_id}")
                update_job(job_id, status="FAILED", error=str(e))
                yield {"type": "quiz_gen_failed", "jobId": job_id}
            return

        # After the quiz is generated, trigger its evaluation.
        if status == "QUIZ_GENERATED":
            update_job(job_id, status="PROCESSING_QUIZ_EVAL", msg = "Triggering quiz evaluation")
            trigger_url = f"{EVAL_API_URL}/jobs/{job_id}/evaluate"

            try:
                # Call the evaluator API for the quiz.
                async with httpx.AsyncClient() as client:
                    resp = await client.post(trigger_url, json={"scope": "quiz"}, timeout=30.0)

                if resp.status_code != 202:
                    raise Exception(f"Quiz Eval API failed: {resp.status_code}")
                    
                yield {"type" : "quiz_eval_trigger_success", "jobId": job_id}
            
            except Exception as e:
                logger.exception(f"Quiz eval trigger failed {job_id}")
                update_job(job_id, status="FAILED", error=str(e))
                yield {"type": "quiz_eval_failed", "jobId": job_id}
            return
        
        # If the blueprint is complete, the orchestrator waits for the next step
        # (lesson generation) to be triggered externally.
        if status == "BLUEPRINT_COMPLETE":
            yield {"type": "orchestrator_idle", "jobId": job_id, "status" : "Waiting for lesson eval"}
            return
            
        # If the job status doesn't match any of the above conditions, log it and wait.
        logger.info(f"[Orchestrator] No route for status={status}")
        yield {"type": "orchestrator_idle", "jobId": job_id}
        return
