# Note: This code was generated with Google's Gemini. The program was reviewed, modified, and tested to
# ensure functionality.
"""
Builds and uploads quizzes using lesson content and a generative model.
generate_quiz_from_blueprint runs in the background to:

  1. Fetch the blueprint and lessons
  2. Generate quiz questions per module based on assessment goals
  3. Upload the final quiz JSON to GCS
"""
from __future__ import annotations
from datetime import datetime, timezone
import os
import json
import logging
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field, field_validator
from urllib.parse import unquote, urlparse

from google.cloud import firestore, storage
from pydantic import BaseModel, Field, field_validator

import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

#Configuration
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "amazing-math-473517-f9")
LOCATION   = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
BUCKET_NAME = 'mari-uploads-ns-uc1-east4'
MODEL_NAME = os.getenv("QUIZ_MODEL_NAME", "gemini-2.5-flash") #using 2.5 flash over 2.5 pro for its speed

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Pydantic Models for Quiz Data Structure

class QuizOption(BaseModel):
    """Defines the structure for a single answer option in a quiz question."""
    text: str = Field(..., description="Text of the option")
    is_correct: bool = Field(..., alias="isCorrect", description="True if it is the correct answer")
    class Config:
        populate_by_name = True  # Allows using 'isCorrect' or 'is_correct' in Python

class QuizQuestion(BaseModel):
    """Defines the structure for a single quiz question."""
    question_text: str = Field(..., description="Text of the question")
    question_type: str = Field(..., description="Type of the question(single_correct or multi_correct)")
    justification: str = Field(..., description="Explanation of the correct answer refering to the lesson content")
    options: List[QuizOption] = Field(..., min_length=3, max_length=8, description="List of answer choices (minimum 3, maximum 8)")
    original_assessment: str = Field(..., description="The original assessment question from the blueprint")

    @field_validator('options')
    def check_correct_answers(cls, options: List[QuizOption]) -> List[QuizOption]:
        """Validator to ensure that at least one correct answer is provided for a question."""
        correct_count = sum(1 for opt in options if opt.is_correct)
        if correct_count ==0:
            raise ValueError("No correct answer provided. At least one option must be the correct answer")
        return options
    
class ModuleQuiz(BaseModel):
    """Represents a collection of quiz questions for a single course module."""
    module_title: str = Field(..., description="Title of the module the quiz belongs to")
    questions: List[QuizQuestion] = Field(..., description="A list of quiz questions for the module")

class CourseQuiz(BaseModel):
    """Represents the entire quiz for a course, composed of quizzes for each module."""
    course_title: str = Field(..., description=" Title of the main course")
    modules: List[ModuleQuiz]= Field(..., description="A list of all the generated quiz modules")

# Google Cloud Storage Utility Functions

def _split_gcs_uri(gcs_uri: str) -> Tuple[str, str]:
    """Parses a GCS URI (gs:// or https://) and returns the bucket name and blob name."""
    if gcs_uri.startswith("gs://"):
        parts = gcs_uri[5:].split("/", 1)
        if len(parts) < 2 or not parts[0] or not parts[1]:
             raise ValueError(f"Invalid GCS URI: {gcs_uri}")
        return parts[0], parts[1]
    elif "storage.googleapis.com" in gcs_uri:
        parsed = urlparse(gcs_uri)
        path_parts = parsed.path.lstrip("/").split("/", 1)
        if len(path_parts) < 2:
            raise ValueError(f"Unexpected GCS URL format: {gcs_uri}")
        # The first part of the path is the bucket name
        return path_parts[0], path_parts[1]
    else:
        raise ValueError(f"Not a valid GCS or HTTPS GCS URI: {gcs_uri}")
    
def _download_json_from_gcs(gcs_uri: str, storage_client: storage.Client) -> Dict[str, Any]:
    """Downloads a blob from GCS and parses it as JSON."""
    logger.info(f"Downloading JSON from: {gcs_uri}")
    try:
        bucket_name, blob_name = _split_gcs_uri(gcs_uri)
        blob_name = unquote(blob_name)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if not blob.exists():
            raise FileNotFoundError(f"GCS object not found: {gcs_uri}")
        return json.loads(blob.download_as_text())
    except Exception as e:
        logger.exception(f"Failed to download or parse JSON from {gcs_uri}")
        raise

def _download_text_from_gcs(gcs_uri: str, storage_client: storage.Client) -> str:
    """Downloads a blob from GCS and returns its raw text content."""
    logger.info(f"Downloading text from: {gcs_uri}")
    try:
        bucket_name, blob_name = _split_gcs_uri(gcs_uri)
        blob_name = unquote(blob_name)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if not blob.exists():
            raise FileNotFoundError(f"GCS object not found: {gcs_uri}")
        return blob.download_as_text()
    except Exception as e:
        logger.exception(f"Failed to download text from {gcs_uri}")
        raise

def _upload_json_to_gcs(data: Any, bucket_name: str, object_name: str, storage_client: storage.Client) -> str:
    """Uploads a JSON-serializable dictionary to GCS and returns the GCS URI."""
    logger.info(f"Uploading JSON to: gs://{bucket_name}/{object_name}")
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        # Serialize the data to a JSON string.
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        blob.upload_from_string(payload, content_type="application/json")
        return f"gs://{bucket_name}/{object_name}"
    except Exception as e:
        logger.exception(f"Failed to upload JSON to gs://{bucket_name}/{object_name}")
        raise

# Core Quiz Generation Logic

def _get_quiz_generation_prompt(
        module_title: str,
        assesment_questions: List[str],
        lesson_content: str,
        learner_profile: Dict[str, any] | None = None) -> str:
    """
    Constructs detailed prompt for generative model to create a quiz for a module.
    """
    # Incorporate learner profile to tailor question complexity.
    profile_instructions = ""
    if learner_profile:
        complexity = learner_profile.get("complexity", "intermediate")
        profile_instructions = f"\n- Target a '{complexity}' complexity level for the questions and distractors."

    # Getting the questions from the blueprint
    assessment_list = "\n".join(f"- {q}" for q in assesment_questions)

    # The main prompt template providing persona, instructions, schema, and inputs.
    prompt = f""" 
        You are an expert instructional designer tasked with creation of a quiz for the given module.
        Your goal is to generate multiple-choice questions based on a list of assessment items and the full lesson content.

        Instructions to be followed:
        1. Base your questions on the assessments. Each item in the "Assessment Questions" list must be converted into a multiple-choice question.
        2. If the exact question cannot be made as a multiple-choice question, generate a similar question that is meaningful to have as a multiple-choice question.
        3. The text for the correct answers, incorrect answers (distractors), and the justification MUST be derived from the provided "Lesson Content".
        4. The justification should be a short paragraph explaining the correct answer and where this was taught within the module.
        5. Each question MUST have a minimum of 3 and a maximum of 8 answer choices (options). Ensure you always provide at least 3 options, and you may include up to 8 options if appropriate for the question.
        6. JSON Schema: The final output MUST be a single, valid JSON object matching the 'ModuleQuiz' schema provided below.

        JSON Output Schema:
        ```json
        {{
            "module_title": "{module_title}",
            "questions": [
                {{
                    "question_text": "string",
                    "question_type": "string ('single_correct' or 'multi_correct')",
                    "options": [
                        {{ "text": "string", "is_correct" : boolean}},
                        {{ "text": "string", "is_correct" : boolean}},
                        {{ "text": "string", "is_correct" : boolean}}
                        // ... (minimum 3, maximum 8 options required)
                    ],
                    "justification": "string (Explanation for the correct answer, using verbiage from the lesson).",
                    "original_assessment": "string (The original assessment item text.)"
                }}
            ]
        }}
        ```

        INPUTS:
        1. Learner Profile: {profile_instructions}
        2. Full Lesson Content (Markdown):
        ---
        {lesson_content}
        ---
        3. Assessment Questions (to be converted into MCQs):
        ---
        {assessment_list}
        ---

        TASK:
        - Use the above inputs to create the quiz.
        - All questions and answers must be derived from the lesson content.
        - Include exactly one correct answer per question.
        - Each question must have a minimum of 3 and a maximum of 8 answer choices.
        - Justification must quote or paraphrase lesson material.

        IMPORTANT: Output must be **raw JSON only** — no backticks, no markdown formatting, and no text before or after the JSON.
    """

    return prompt
        

def _generate_quiz_for_module(
    model: GenerativeModel,
    module_title: str,
    assesment_questions: List[str],
    lesson_content: str,
    learner_profile: Dict[str, any] | None = None
) -> ModuleQuiz:
    """
    Generates a quiz for a single module by calling the generative model.
    """
    if not assesment_questions:
        logger.info(f"No assessment questions found in blueprint. Module: {module_title}")
        return ModuleQuiz(module_title=module_title, questions=[])
    
    try:
        prompt = _get_quiz_generation_prompt(
            module_title=module_title,
            assesment_questions=assesment_questions,
            lesson_content=lesson_content,
            learner_profile=learner_profile
        )

        # Configure the model to output JSON directly.
        generation_config = GenerationConfig(
            temperature=0.2,
            response_mime_type="application/json",
            max_output_tokens=4096
        )

        logger.info(f"Generating quiz for module: {module_title}")
        response = model.generate_content(prompt, generation_config=generation_config)

        # Extract text response
        response_text = response.candidates[0].content.parts[0].text.strip()

        # Validate the response as JSON
        try:
            module_quiz = ModuleQuiz.model_validate_json(response_text)
        except Exception:
            cleaned = response_text.replace("```json", "").replace("```", "").strip()
            try:
                module_quiz = ModuleQuiz.model_validate_json(cleaned)
            except Exception as e:
                logger.error(f"Invalid JSON for module '{module_title}': {e}")
                raise

        logger.info(f"✅ Successfully generated and validated quiz for module: {module_title}")
        return module_quiz

    except Exception as e:
        logger.exception(f"❌ Failed to create quiz for module - {module_title}")
        # Return an empty quiz for the module on failure to avoid breaking the whole process.
        return ModuleQuiz(module_title=module_title, questions=[])
    
def generate_quiz_from_blueprint(job_id: str) -> Dict[str, any]:
    """
    Main orchestration function to generate a full course quiz from a blueprint.
    This function is intended to be run as a background task.
    """
    db = firestore.Client(project=PROJECT_ID)
    storage_client = storage.Client()
    
    # 1. Get job details from Firestore.
    job_ref = db.collection("jobs").document(job_id)
    job_doc = job_ref.get()
    
    if not job_doc.exists:
        raise ValueError(f"Job {job_id} not found in firestore")
    
    job_data = job_doc.to_dict() or {}
    results = job_data.get("results", {})
    learner_profile = job_data.get("learnerProfile", {})
    
    # 2. Update job status to indicate quiz generation has started.
    job_ref.update({"status": "PROCESSING_QUIZ_GEN"}) #updating status to show work started
    
    # 3. Get the course blueprint from GCS.
    blueprint_uri = results.get("blueprint_gcs_uri")
    if not blueprint_uri:
        raise ValueError(f"blueprint uri not found in Job - {job_id}")
    
    blueprint = _download_json_from_gcs(blueprint_uri, storage_client)
    course_title = blueprint.get("course_title", "Untitled")
    
    # 4. Get the URIs for all generated lesson markdown files.
    lesson_uris: Dict[str, str] = results.get("lesson_gcs_uris")
    if not lesson_uris:
        raise ValueError(f"lesson_gcs_uris not found in job {job_id}")
    
    # 5. Download the content of each lesson.
    lesson_content_map: Dict[str, str] = {}
    for module_title, uri in lesson_uris.items():
        lesson_content_map[module_title] = _download_text_from_gcs(uri ,storage_client)
        
    # 6. Initialize the generative model.
    vertexai.init(project = PROJECT_ID, location=LOCATION)
    model = GenerativeModel(MODEL_NAME)
    
    # 7. Iterate through modules and generate a quiz for each one.
    course_quiz = CourseQuiz(course_title=course_title, modules=[])
    for module in blueprint.get("modules", []):
        module_title = module.get("module_title")
        if not module_title:
            logger.warning("Skipping module with no title")
            continue
        
        assessment_questions = module.get("assessment_questions", [])
        lesson_content = lesson_content_map.get(module_title, "")
        
        if not lesson_content or not assessment_questions:
            logger.warning(f"Skipping quiz for module {module_title} with no content/questions")
            continue
        
        # Generate the quiz for the current module.
        module_quiz = _generate_quiz_for_module(
            model=model,
            module_title=module_title,
            assesment_questions=assessment_questions,
            lesson_content=lesson_content,
            learner_profile=learner_profile
        )
        
        course_quiz.modules.append(module_quiz)
        # Log progress to Firestore.
        job_ref.update({
            "updateLog": firestore.ArrayUnion([{
                "time" : datetime.now(timezone.utc),
                "message" : f"Quiz generated for module: {module_title}"
            }])
        })
    
    # 8. Upload the final course quiz to GCS.
    quiz_data = json.loads(course_quiz.model_dump_json(indent=2))
    quiz_data["passing_percentage"] = 70 # must get 70% or higher to pass the quiz
    quiz_object_name = f"jobs/{job_id}/quiz/course_quiz.json"
    
    quiz_gcs_uri = _upload_json_to_gcs(
        data=quiz_data,
        bucket_name=BUCKET_NAME,
        object_name=quiz_object_name,
        storage_client=storage_client
    )
    logger.info(f"Success - Uploaded quiz to GCS : {quiz_gcs_uri}")
    
    # 9. Update the final status and quiz URI on the job document.
    final_results = {**results, "quiz_gcs_uri": quiz_gcs_uri}
    job_ref.update({
        "status": "QUIZ_GENERATED",
        "results" : final_results,
        "updateLog": firestore.ArrayUnion([{
            "time" : datetime.now(timezone.utc),
            "message" : "Quiz generation completed successfully for all modules."
        }])
    })
    
    return {"quiz_gcs_uri": quiz_gcs_uri,  "module_processed": [m.module_title for m in course_quiz.modules]}