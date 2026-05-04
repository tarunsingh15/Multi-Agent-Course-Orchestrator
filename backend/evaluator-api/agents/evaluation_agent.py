"""
Runs the evaluation agent that grades generated lessons and quizzes using a rubric + AI model.

Key functions:
1. Uses a detailed rubric to score correctness, clarity, engagement, and alignment.
2. Builds structured prompts that include the rubric, learner profile, and content.
3. evaluate_job orchestrates the full workflow:
    a. Fetches job + content from Firestore/GCS
    b. Evaluates lessons or quiz via the model
    c. Aggregates results and uploads the final evaluation JSON
    d. Updates job status in Firestore
"""
import os
import json
import logging
from typing import Any, Dict, List, Tuple

from pydantic import BaseModel, Field, ValidationError
from google.cloud import firestore, storage

import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

from utils.gcs_io import (download_json_from_uri, download_text_from_uri, upload_json_to_gcs)
# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# GCS bucket and project settings
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "amazing-math-473517-f9")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
BUCKET_NAME = "mari-uploads-ns-uc1-east4"
MODEL_NAME = os.getenv("EVAL_MODEL_NAME", "gemini-2.5-pro")

# Defines the evaluation rubric and required JSON output format used by the model to score lessons and quizzes.

RUBRIC_TEXT = """
## Evaluation Rubric and Scoring Guidelines

### Scoring Scale (1-5)
Use this scale consistently for all numeric metrics:
- **1 (Poor)**: Major issues present. Content is fundamentally flawed, incorrect, or unusable. Requires complete revision.
- **2 (Below Acceptable)**: Significant problems exist. Multiple errors or misalignments that substantially impact learning. Needs major improvements.
- **3 (Acceptable)**: Meets basic requirements but has room for improvement. Minor issues present that don't significantly hinder learning. Suitable for use with minor revisions.
- **4 (Good)**: High quality with only minor issues. Well-aligned with requirements. May benefit from small refinements but is ready for use.
- **5 (Excellent)**: Outstanding quality. No significant issues. Perfectly aligned with requirements and learner needs. No changes needed.

### Threshold Guidelines
- **Minimum Acceptable Score**: 3.0 average across all metrics
- **Critical Metrics**: factual_accuracy must be "pass" for content to be acceptable
- **Quality Threshold**: Average score of 4.0+ indicates high-quality content ready for production
- **Red Flags**: Any score of 1-2 indicates content needs revision before use

---
### 1. Module Content Evaluation
(Evaluate the Markdown lesson content)

#### Correctness
* **factual_accuracy** ("fail" | "pass"): 
  - **"pass"**: All information is factually correct, accurate, and verifiable. No errors in facts, definitions, or explanations.
  - **"fail"**: Contains factual errors, incorrect information, or misleading statements. Content cannot be trusted.
  
* **internal_consistency** (1-5): 
  - **5**: No contradictions. All concepts, examples, and explanations align perfectly throughout.
  - **4**: Minor inconsistencies that don't affect understanding.
  - **3**: Some contradictions present but don't significantly impact learning.
  - **2**: Multiple contradictions that confuse the learner.
  - **1**: Fundamental contradictions that make content unreliable.

#### Clarity
* **clarity_grammar** (1-5):
  - **5**: Flawless grammar, clear sentence structure, professional writing.
  - **4**: Minor grammatical issues that don't affect comprehension.
  - **3**: Some grammatical errors but content is generally understandable.
  - **2**: Frequent grammatical errors that hinder understanding.
  - **1**: Poor grammar making content difficult to read or understand.

* **avoid_jargon** (1-5):
  - **5**: All technical terms clearly explained. Assumes no prior knowledge. Perfectly accessible.
  - **4**: Most terms explained well. Minor assumptions of prior knowledge.
  - **3**: Some jargon unexplained but context helps. Generally accessible.
  - **2**: Significant unexplained jargon. Assumes too much prior knowledge.
  - **1**: Heavy use of unexplained jargon. Inaccessible to target learner.

* **difficulty_progression** (1-5):
  - **5**: Perfect progression from simple to complex. Each concept builds naturally on previous ones.
  - **4**: Good progression with minor jumps in difficulty.
  - **3**: Acceptable progression but some concepts could be better sequenced.
  - **2**: Uneven progression. Some concepts too advanced or too basic for their position.
  - **1**: Poor progression. Concepts presented in confusing order.

#### Alignment to Preferences
* **learner_profile** (1-5):
  - **5**: Perfectly matches learner's complexity level, learning style preferences, and tone expectations.
  - **4**: Well-aligned with minor deviations from profile.
  - **3**: Generally aligned but some aspects don't match profile perfectly.
  - **2**: Significant misalignment with learner profile.
  - **1**: Poor alignment. Content doesn't match learner's needs or preferences.

* **context** (1-5):
  - **5**: Highly relevant to learner's stated goals and context. Directly applicable.
  - **4**: Relevant with strong connection to goals.
  - **3**: Somewhat relevant but connection to goals could be stronger.
  - **2**: Limited relevance to stated goals.
  - **1**: Not relevant to learner's goals or context.

#### Engagement
* **interest** (1-5):
  - **5**: Highly engaging, relatable, and compelling. Maintains learner attention throughout.
  - **4**: Engaging with good use of examples and relatable content.
  - **3**: Moderately engaging. Some interesting elements but could be more compelling.
  - **2**: Lacks engagement. Dry or uninteresting presentation.
  - **1**: Boring or unengaging. Fails to capture learner interest.

* **depth** (1-5):
  - **5**: Provides deep, comprehensive understanding. Goes beyond surface-level explanation.
  - **4**: Good depth with thorough coverage of concepts.
  - **3**: Adequate depth but could explore concepts more thoroughly.
  - **2**: Superficial coverage. Lacks depth in explanations.
  - **1**: Very shallow. Fails to provide meaningful understanding.

* **real_world_impact** (1-5):
  - **5**: Excellent practical applications. Clear connections to real-world use cases.
  - **4**: Good practical examples and applications.
  - **3**: Some practical applications but could be more explicit.
  - **2**: Limited practical application or real-world relevance.
  - **1**: No practical application or real-world connection.

---
### 2. Quiz Content Evaluation
(Evaluate the JSON quiz questions)

* **factual_accuracy** ("fail" | "pass"):
  - **"pass"**: All questions have correct answers based on module content. No errors in answer keys or explanations.
  - **"fail"**: Contains incorrect answers, wrong answer keys, or misleading explanations. Quiz cannot be trusted.

* **clarity** (1-5):
  - **5**: Questions are crystal clear, unambiguous, and easy to understand. No confusion possible.
  - **4**: Clear questions with minor ambiguities that don't affect understanding.
  - **3**: Generally clear but some questions could be more precise.
  - **2**: Multiple unclear or ambiguous questions that confuse learners.
  - **1**: Questions are confusing, misleading, or poorly worded.

* **relevance** (1-5):
  - **5**: Perfectly tests all key concepts from the module. Questions align with learning objectives.
  - **4**: Tests most important concepts well. Good alignment with objectives.
  - **3**: Tests relevant concepts but misses some important topics.
  - **2**: Limited relevance. Many questions don't test key concepts.
  - **1**: Poor relevance. Questions don't align with module content or objectives.

* **difficulty** (1-5):
  - **5**: Perfect difficulty level matching learner profile. Challenging but achievable.
  - **4**: Appropriate difficulty with minor adjustments needed.
  - **3**: Generally appropriate but some questions too easy or too hard.
  - **2**: Significant difficulty mismatch with learner profile.
  - **1**: Poor difficulty alignment. Too easy or too hard for target learner.

* **feedback** (1-5):
  - **5**: Excellent, constructive feedback. Clear explanations for both correct and incorrect answers. Encouraging tone.
  - **4**: Good feedback with helpful explanations.
  - **3**: Adequate feedback but could be more detailed or encouraging.
  - **2**: Limited or unhelpful feedback. Lacks explanation or encouragement.
  - **1**: Poor or missing feedback. No value added for learner.

---
### Required JSON Output Format
You must return *only* a valid JSON object. Do not add markdown backticks or "json".
The JSON object must contain *only the keys you are evaluating* ("module_content" or "quiz_content").

Each metric should include:
- **score**: The numeric score (1-5) or "pass"/"fail" for factual_accuracy
- **comment**: A concise, 1-sentence explanation justifying the score

Example for "lessons" scope:
{
  "module_content": {
    "correctness": {
      "factual_accuracy": {"score": "pass", "comment": "All information is factually correct and accurate."},
      "internal_consistency": {"score": 4, "comment": "Content is consistent with minor areas that could be better aligned."}
    },
    "clarity": {
      "clarity_grammar": {"score": 5, "comment": "Flawless grammar and clear sentence structure throughout."},
      "avoid_jargon": {"score": 4, "comment": "Most technical terms are well-explained with minor assumptions."},
      "difficulty_progression": {"score": 4, "comment": "Good progression from simple to complex concepts."}
    },
    "alignment_to_preferences": {
      "learner_profile": {"score": 4, "comment": "Well-aligned with learner's complexity level and preferences."},
      "context": {"score": 5, "comment": "Highly relevant to learner's stated goals."}
    },
    "engagement": {
      "interest": {"score": 4, "comment": "Engaging content with relatable examples."},
      "depth": {"score": 4, "comment": "Provides good depth in explanations."},
      "real_world_impact": {"score": 4, "comment": "Good practical applications and real-world connections."}
    }
  }
}

Example for "quiz" scope:
{
  "quiz_content": {
    "factual_accuracy": {"score": "pass", "comment": "All answers are correct based on module content."},
    "clarity": {"score": 4, "comment": "Questions are clear with minor ambiguities."},
    "relevance": {"score": 5, "comment": "Perfectly tests key concepts from the module."},
    "difficulty": {"score": 4, "comment": "Appropriate difficulty level for the learner profile."},
    "feedback": {"score": 4, "comment": "Good feedback with helpful explanations for answers."}
  }
}
"""

def _build_evaluation_prompt(scope: str, lesson_markdown: str, quiz_module_json: str, learner_profile_json: str) -> str:
    """
    Builds the evaluation prompt by combining the rubric, learner profile, and target content for the given scope.
    """
    if scope == "lessons":
        task = "Evaluate *only* the 'Module Lesson Content' and return the 'module_content' JSON block."
        content_to_eval = f"## Module Lesson Content (Markdown)\n{lesson_markdown}"
    else: # scope == "quiz"
        task = "Evaluate *only* the 'Module Quiz Content' and return the 'quiz_content' JSON block."
        content_to_eval = f"## Module Quiz Content (JSON)\n{quiz_module_json}"

    return f"""
You are an expert instructional design evaluator with deep expertise in educational content quality assessment. Your task is to evaluate content rigorously based on the detailed rubric provided.

## Critical Evaluation Principles
1. **Be Strict but Fair**: Use the full scoring range (1-5). Reserve scores of 5 for truly excellent content and scores of 1-2 for content with significant issues.
2. **Threshold Awareness**: 
   - Content averaging below 3.0 is NOT acceptable and needs revision
   - Content averaging 4.0+ is high-quality and production-ready
   - factual_accuracy MUST be "pass" for content to be acceptable
3. **Consistency**: Apply scoring criteria consistently across all metrics. Similar quality should receive similar scores.
4. **Actionable Comments**: Provide specific, constructive comments that explain your score and identify what could be improved.

## Evaluation Rubric
{RUBRIC_TEXT}

---

## 1. Learner Profile (for Alignment)
Use this profile to evaluate alignment metrics (learner_profile, context, difficulty):
{learner_profile_json}

---

## 2. Content to Evaluate
{content_to_eval}

---

## Task
{task}

## Important Reminders
- Return *only* a valid JSON object (no markdown backticks, no "json" prefix)
- Each metric must include both "score" and "comment" fields
- Use the scoring scale consistently: 1=Poor, 2=Below Acceptable, 3=Acceptable, 4=Good, 5=Excellent
- factual_accuracy must be either "pass" or "fail" (not a number)
- Be thorough but concise in your comments (1 sentence per metric)
- Consider the threshold guidelines when assigning scores

Return *only* the valid JSON evaluation object matching the structure shown in the rubric examples.
"""

def evaluate_job(job_id: str, scope: str):
    """
    Runs the full evaluation workflow: fetches data, evaluates content via the model, and updates job status.
    """
    logger.info(f"Starting evaluation for job {job_id} with scope: {scope}")
    db = firestore.Client(project=PROJECT_ID)
    storage_client = storage.Client()
    job_ref  = db.collection("jobs").document(job_id)
    
    eval_object_name = f"jobs/{job_id}/evaluation/evaluation_results.json"
    
    try:
        # Fetch the job document from Firestore.
        job_doc = job_ref.get()
        if not job_doc.exists:
            logger.error(f"Job {job_id} not found")
            return
        
        # Update job status to indicate evaluation is in progress.
        job_ref.update({"status": "PROCESSING_EVALUATION"})
        job_data = job_doc.to_dict() or {}
        results = job_data.get("results",{})
        # Get required data URIs and profiles from the job document.
        learner_profile = job_data.get("learnerProfile", {})
        blueprint_uri = results.get("blueprint_gcs_uri")
        lesson_uris: Dict[str, str] = results.get("lesson_gcs_uris", {})
        quiz_uri = results.get("quiz_gcs_uri")
        
        if not blueprint_uri:
            raise ValueError("Missing blueprint URI in job results")
        
        # Download the course blueprint and serialize the learner profile for the prompt.
        blueprint = download_json_from_uri(blueprint_uri)
        learner_profile_json = json.dumps(learner_profile, indent=2)
        # Initialize the Vertex AI model and configure its generation settings.
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        model = GenerativeModel(MODEL_NAME)
        generation_config = GenerationConfig( temperature = 0.1, 
                                             response_mime_type= 'application/json')
        # This dictionary will hold the evaluation results.
        evaluation_results = {}
        
        # --- Lesson Evaluation Scope ---
        if scope=="lessons":
            if not lesson_uris:
                raise ValueError("Missing lesson_gcs_uri in job results")
            
            evaluation_results = {"job_id": job_id, "modules": {}}
            
            # Download all lesson content into a map for easy access.
            lesson_content_map: Dict[str, str] = {}
            for module_title, uri in lesson_uris.items():
                lesson_content_map[module_title] = download_text_from_uri(uri)
                
            # Iterate through each module defined in the blueprint to evaluate its lesson.
            for module in blueprint.get("modules", []):
                module_title = module.get("module_title")
                if not module_title: continue
                
                logger.info(f"Evaluating LESSONS for module: {module_title}")
                lesson_markdown = lesson_content_map.get(module_title, "")
                
                if not lesson_markdown:
                    logger.warning(f"No lesson content for {module_title}, skipping module.")
                    evaluation_results["modules"][module_title] = {"module_content" : {"error" : "Missing lesson content"}}
                    continue
                
                # Build the prompt and call the model.
                prompt = _build_evaluation_prompt (
                    scope= "lessons",
                    lesson_markdown=lesson_markdown,
                    quiz_module_json="",
                    learner_profile_json=learner_profile_json
                )
                
                response = model.generate_content(prompt, generation_config=generation_config)
                
                # Store the parsed JSON response.
                eval_json = json.loads(response.text)
                evaluation_results["modules"][module_title] = eval_json
            
            # Upload the complete evaluation results to GCS.
            eval_gcs_uri = upload_json_to_gcs(
                data= evaluation_results,
                bucket_name=BUCKET_NAME,
                object_name=eval_object_name,
                storage_client=storage_client
            )
            
            # Update the job document with the new evaluation URI and status.
            final_results = {**results, "evaluation_gcs_uri":eval_gcs_uri}
            job_ref.update({
                "status": "LESSON_EVALUATED",
                "results": final_results
            })
            logger.info(f"Lesson evaluation complete. Results at {eval_gcs_uri}")
            
        # --- Quiz Evaluation Scope ---
        elif scope=="quiz":
            if not quiz_uri:
                raise ValueError("Missing quiz_gcs_uri in job results")
            
            # The quiz evaluation builds upon the lesson evaluation, so it requires the previous results.
            lesson_eval_uri = results.get("evaluation_gcs_uri")
            
            if not lesson_eval_uri:
                raise ValueError("Missing 'evaluation_gcs_uri' in job results. Please ensure the 'lessons' evaluation has completed before running 'quiz' eval")
            
            # Download the existing lesson evaluation to append the quiz results to it.
            logger.info(f"Dowloading exisitng lesson metrics from: {lesson_eval_uri}")    
            evaluation_results = download_json_from_uri(lesson_eval_uri)
            
            if "modules" not in evaluation_results:
                evaluation_results["modules"] = {}
                
            # Download the quiz data and map it by module title for easy lookup.
            quiz_data = download_json_from_uri(quiz_uri)
            quiz_modules_map = {m["module_title"]: m for m in quiz_data.get("modules", [])}
            
            # Iterate through each module to evaluate its corresponding quiz.
            for module in blueprint.get("modules", []):
                module_title = module.get("module_title")
                if not module_title: continue
                
                logger.info(f"Evaluating QUIZ for module: {module_title}")
                quiz_module = quiz_modules_map.get(module_title)
                
                if not quiz_module:
                    logger. warning(f"No quiz content for {module_title}, skip")
                    if module_title not in evaluation_results["modules"]:
                        evaluation_results["modules"][module_title] = {}
                    evaluation_results["modules"][module_title]["quiz_content"] = {"error" : "Missing quiz content"}
                    continue
                
                # Build the prompt and call the model.
                prompt = _build_evaluation_prompt(
                    scope="quiz",
                    lesson_markdown="",
                    quiz_module_json=json.dumps(quiz_module, indent=2),
                    learner_profile_json=learner_profile_json
                )
                
                response = model.generate_content(prompt, generation_config=generation_config)
                eval_json = json.loads(response.text)
                
                # Merge the quiz evaluation into the existing results object.
                if module_title not in evaluation_results["modules"]:
                    evaluation_results["modules"][module_title] = {}
                evaluation_results["modules"][module_title].update(eval_json)
                
            # Upload the final, combined evaluation results to GCS.
            eval_gcs_uri = upload_json_to_gcs(
                data= evaluation_results,
                bucket_name=BUCKET_NAME,
                object_name=eval_object_name,
                storage_client=storage_client
            )
            
            # Update the job document with the final URI and mark the evaluation as complete.
            final_results = {**results, "evaluation_gcs_uri": eval_gcs_uri}
            job_ref.update({
                "status": "EVALUATION_COMPLETE",
                "results": final_results
            })
            logger.info(f"Quiz evaluation complete. Final results at {eval_gcs_uri}")
    except Exception as e:
        # If any error occurs, log it and update the job status to FAILED in Firestore.
        logger.exception(f"Evaluation failed for job {job_id} (Scope = {scope}): {e}")
        job_ref.update({
            "status": "FAILED",
            "error": f"Evaluation failed (scope: {scope}): {str(e)}"
        })
