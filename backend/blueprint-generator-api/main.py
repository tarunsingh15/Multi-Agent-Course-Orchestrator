# Note: This code was generated with Google's Gemini. The program was reviewed, modified, and tested to
# ensure functionality.
"""
FastAPI service for generating and revising course blueprints.

Key features:
- `/generate`: Creates a new blueprint from parsed document chunks.
- `/revise`: Updates an existing blueprint using feedback.

Core flow:
- Calls generation helpers and validates output against `CourseBlueprint`.
- Retries up to 3 times if validation fails, adding error feedback each time.
- Uses GCS for reading inputs and storing final blueprints.
"""

import json
import traceback
import vertexai
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from vertexai.generative_models import GenerativeModel

import blueprint_generation
import gcs_io

# Initialize Vertex AI client with the specified project and location.
PROJECT_ID = "amazing-math-473517-f9"
LOCATION = "us-central1"
vertexai.init(project=PROJECT_ID, location=LOCATION)

# Load the generative model from Vertex AI.
GENERATION_MODEL = GenerativeModel("gemini-2.5-pro")

# Initialize the FastAPI application.
app = FastAPI()

# --- Pydantic Models ---
# These models define the expected request and response body structures for the API endpoints,
# providing automatic validation and serialization.

class GenerateRequest(BaseModel):
    """Defines the request body for the /generate endpoint."""
    jobId: str
    parsed_chunks_gcs_uri: str
    output_gcs_bucket: str
    learnerProfile: Optional[Dict[str, Any]] = None
    context: Optional[str] = None

class ReviseRequest(BaseModel):
    """Defines the request body for the /revise endpoint."""
    jobId: str
    feedback: str
    current_blueprint_gcs_uri: str
    parsed_chunks_gcs_uri: str
    output_gcs_bucket: str
    learnerProfile: Optional[Dict[str, Any]] = None
    context: Optional[str] = None

class BlueprintResponse(BaseModel):
    """Defines the standard response structure for the API."""
    status: str
    blueprint_gcs_uri: str
    message: str

# --- Helper Function: Generation Loop ---

def _generate_and_validate(
    generation_func,
    func_kwargs: dict,
    jobId: str,
    output_bucket: str,
    max_retries: int = 3
) -> str:
    """
    Executes a generation function, validates the output against the Pydantic schema,
    and retries with error feedback if validation fails. This creates a self-correcting loop.
    """
    errors = []
    
    # Loop for the initial attempt plus the specified number of retries.
    for attempt in range(max_retries + 1):
        try:
            # If this is a retry, pass the accumulated errors from previous attempts
            # to the generation function to help the model correct itself.
            if errors:
                func_kwargs["previous_errors"] = errors
                print(f"Attempt {attempt + 1}: Retrying generation with error feedback...", flush=True)
            
            # 1. Generate: Call the provided generation function to generate (or regenerate).
            blueprint_json_str = generation_func(**func_kwargs)
            
            # 2. Validate: Parse and validate the generated JSON against the CourseBlueprint model.
            # Throws a ValueError if the schema is incorrect
            # Likely due to incorrect data types or learning objectives not starting with measurable verbs.
            blueprint_obj = blueprint_generation.CourseBlueprint.model_validate_json(blueprint_json_str)
            
            # 3. Upload final JSON to GCS if validation is successful.
            blueprint_dict = json.loads(blueprint_obj.model_dump_json(indent=2))
            output_filename = f"blueprint-output/{jobId}-v{attempt + 1}.json"
            
            print(f"Validation success (Attempt {attempt + 1}). Uploading to {output_filename}...", flush=True)
            
            output_gcs_uri = gcs_io.upload_json_to_gcs(
                data=blueprint_dict,
                bucket_name=output_bucket,
                object_name=output_filename 
            )
            return output_gcs_uri

        except Exception as e:
            # If validation or any other step fails, capture the error message.
            error_msg = str(e)
            print(f"Validation/Upload failed (Attempt {attempt + 1}): {error_msg}", flush=True)
            errors.append(error_msg)
            
    # If all retries fail, raise an exception with the final error.
    raise Exception(f"Failed to generate valid blueprint after {max_retries} retries. Last error: {errors[-1]}")


# --- API Endpoints ---

@app.get("/")
def read_root():
    """A simple health check endpoint to confirm the API is running."""
    return {"status": "Blueprint Generator API is running"}

@app.post("/generate", response_model=BlueprintResponse)
async def generate_blueprint(request: GenerateRequest):
    """
    Handles the generation of a new course blueprint from scratch based on parsed text chunks.
    """
    print(f"Handling /generate request for job: {request.jobId}", flush=True)
    try:
        # Download the source text chunks from the GCS URI provided in the request.
        chunks = gcs_io.download_json_from_uri(request.parsed_chunks_gcs_uri)
        if not chunks:
            raise HTTPException(status_code=404, detail="Parsed chunks file not found.")

        # Use the self-correcting generation loop to produce a valid blueprint.
        output_uri = _generate_and_validate(
            generation_func=blueprint_generation.generate_blueprint_from_chunks,
            func_kwargs={
                "model": GENERATION_MODEL,
                "chunks": chunks,
                "learner_profile": request.learnerProfile,
                "context": request.context
            },
            jobId=request.jobId,
            output_bucket=request.output_gcs_bucket
        )

        return BlueprintResponse(
            status="success",
            blueprint_gcs_uri=output_uri,
            message="Blueprint generated successfully."
        )

    except Exception as e:
        print(f"Error during /generate for job {request.jobId}: {e}", flush=True)
        traceback.print_exc()
        return BlueprintResponse(status="error", blueprint_gcs_uri="", message=str(e))

@app.post("/revise", response_model=BlueprintResponse)
async def revise_blueprint(request: ReviseRequest):
    """
    Handles the revision of an existing blueprint based on user feedback. It uses a
    router to decide whether to patch the JSON or regenerate it completely.
    """
    print(f"Handling /revise request for job: {request.jobId}", flush=True)
    try:
        # Download the current blueprint that needs to be revised.
        current_blueprint_json = json.dumps(
            gcs_io.download_json_from_uri(request.current_blueprint_gcs_uri)
        )

        # 1. Router: Call a model to classify the feedback as a 'PATCH' or 'REGENERATE' task.
        action = blueprint_generation.get_revision_route(
            model=GENERATION_MODEL,
            feedback=request.feedback,
        )
        action = blueprint_generation.get_revision_route(
            model=GENERATION_MODEL,
            feedback=request.feedback
        )
        
        print(f"Router decided: {action}", flush=True)

        # 2. Prepare Generation Arguments: Based on the router's decision, set up the
        # appropriate function and arguments for the generation loop.
        gen_func = None
        gen_kwargs = {}

        if action == "REGENERATE":
            # Major changes needed, regenerate the blueprint from the original source chunks.
            print("Starting REGENERATION...", flush=True)
            chunks = gcs_io.download_json_from_uri(request.parsed_chunks_gcs_uri)
            gen_func = blueprint_generation.generate_blueprint_from_chunks
            gen_kwargs = {
                "model": GENERATION_MODEL,
                "chunks": chunks,
                "reviewer_feedback": request.feedback,
                "learner_profile": request.learnerProfile,
                "context": request.context
            }
        
        elif action == "PATCH":
            # Minor changes needed, use the JSON patcher function.
            print("Starting PATCH...", flush=True)
            gen_func = blueprint_generation.patch_blueprint_json
            gen_kwargs = {
                "model": GENERATION_MODEL,
                "feedback": request.feedback,
                "current_blueprint_json": current_blueprint_json
            }
        else:
             # Fallback: The router gives an unexpected response; default to regeneration.
             print(f"Unknown action '{action}', defaulting to REGENERATE", flush=True)
             chunks = gcs_io.download_json_from_uri(request.parsed_chunks_gcs_uri)
             gen_func = blueprint_generation.generate_blueprint_from_chunks
             gen_kwargs = {
                "model": GENERATION_MODEL,
                "chunks": chunks,
                "reviewer_feedback": request.feedback,
                "learner_profile": request.learnerProfile,
                "context": request.context
            }

        # 3. Execute Loop: Run the selected generation function within the validation loop.
        output_uri = _generate_and_validate(
            generation_func=gen_func,
            func_kwargs=gen_kwargs,
            jobId=request.jobId,
            output_bucket=request.output_gcs_bucket
        )

        return BlueprintResponse(
            status="success",
            blueprint_gcs_uri=output_uri,
            message=f"Blueprint revised successfully via {action}."
        )

    except Exception as e:
        print(f"Error during /revise for job {request.jobId}: {e}", flush=True)
        traceback.print_exc()
        return BlueprintResponse(status="error", blueprint_gcs_uri="", message=str(e))

# This allows the script to be run locally.
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)