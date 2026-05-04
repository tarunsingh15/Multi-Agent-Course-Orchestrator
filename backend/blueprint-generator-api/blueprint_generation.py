# Note: This code was generated with Google's Gemini. The program was reviewed, modified, and tested to
# ensure functionality.
##########################################################################################
# FILE PURPOSE
# - Declares the CourseBlueprint schema using Pydantic and provides a helper function that calls a Vertex AI Gemini model to
#   generate a blueprint JSON given input content and constraints (learning objectives, assessments, timing).
#   
# WHY THIS EXISTS
# - The blueprint acts as a single source of truth for downstream rendering/authoring steps. Validation ensures objectives are
#   measurable and time estimates are sane before the data is used elsewhere.
#
# KEY CONCEPTS CALLED OUT IN COMMENTS BELOW
# - Bloom-style measurable verbs enforcement via a validator.
# - Model invocation (GenerativeModel + GenerationConfig) with response parsing.
# - Guardrails around extracting text safely even when model response structure varies.
# - Configuration of project/region/model to keep deployments portable.
#
##########################################################################################

# Vertex AI GenerativeModel client + config to call a Gemini model for structured text generation.
from vertexai.generative_models import GenerativeModel, GenerationConfig
# Pydantic is used for data validation/serialization of structured objects.
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any

import json # TEMPORARY FOR TESTING

# --- Configuration ---
PROJECT_ID = "amazing-math-473517-f9"
LOCATION = "us-central1"
MODEL_NAME = "gemini-2.5-pro"

# Expanded list of measurable verbs based on Bloom's Taxonomy
MEASURABLE_VERBS = [
    "define", "list", "name", "recall", "recognize", "repeat", "state",
    "classify", "describe", "discuss", "explain", "identify", "summarize", "translate",
    "apply", "demonstrate", "implement", "interpret", "operate", "solve", "use",
    "analyze", "compare", "contrast", "differentiate", "examine", "organize", "relate",
    "appraise", "critique", "defend", "evaluate", "judge", "justify", "support",
    "construct", "create", "design", "develop", "formulate", "generate", "write",
    "connect", "outline", "predict", "distinguish", "calculate",
    "trace", "locate", "provide", "give", "select"
]

# --- Pydantic Models for Schema Validation ---
# Class Module: encapsulates related behavior and/or schema for this module.
class Module(BaseModel):
    module_title: str = Field(..., description="Short title for the module.")
    estimated_minutes: int = Field(..., description="An estimated integer value of how long the module will take to complete.")
    learning_objectives: List[str] = Field(..., description="List of measurable learning objectives.")
    assessment_questions: List[str] = Field(..., description="Questions that align with the objectives and input content.")

    @field_validator('learning_objectives')
    def objectives_must_start_with_measurable_verb(cls, objectives: List[str]) -> List[str]:
        """
        Validates that each learning objective starts with a verb from a predefined list
        of measurable verbs.
        """
        invalid_objectives = []
        for objective in objectives:
            if not objective.strip(): continue  # Skip empty strings
            first_word = objective.strip().split(" ")[0].lower()
            if first_word not in MEASURABLE_VERBS:
                invalid_objectives.append(objective)
        # If any invalid objectives are found, raise a ValueError.
        if invalid_objectives:
            # Raise a single error listing all invalid objectives
            error_list = "\n".join(f"- '{obj}'" for obj in invalid_objectives)
            raise ValueError(f"The following objectives do not start with a measurable verb:\n{error_list}")   
        return objectives

    @field_validator('estimated_minutes')
    def time_estimate_must_be_in_range(cls, v: int) -> int:
        """
        Ensures that the estimated time for a module is within a reasonable range (1 to 1440 minutes).
        """
        if not (1 <= v <= 1440):
            raise ValueError(f"Estimated minutes must be between 1 and 1440. Found: {v}.")
        return v

class CourseBlueprint(BaseModel):
    course_title: str = Field(..., description="The main title of the entire course.")
    course_description: str = Field(..., description="A brief, one or two-sentence summary of the course.")
    modules: List[Module] = Field(..., description="The list of modules that make up the course.")

    @field_validator('modules')
    def check_module_count(cls, modules: List[Module]) -> List[Module]:
        """
        Validates that the number of modules in the course is between 1 and 50.
        """
        if not (1 <= len(modules) <= 50):
            raise ValueError(f"The number of modules must be between 1 and 50. Found: {len(modules)}.")
        return modules

# --- Prompts ---

# Generates a prompt based on the user's learner profile.
def get_profile_context_prompt(learner_profile: Dict[str, Any]) -> str:
    """
    Constructs a string detailing the learner's preferences (tone, complexity, learning styles)
    to be included in the main prompt.
    """
    if not learner_profile:
        return "No learner profile found."
    profile_instructions = []
    if tone := learner_profile.get("tone"):
        profile_instructions.append(f"- Adopt a '{tone}' tone.")
    if complexity := learner_profile.get("complexity"):
        profile_instructions.append(f"- Target a '{complexity}' complexity level.")
    if styles := learner_profile.get("learningStyles"):
        style_str = ", ".join(styles)
        profile_instructions.append(f"- Incorporate learning styles such as: {style_str}.")
    if not profile_instructions:
        return "None."
    return "\nLearner Profile Preferences:\n" + "\n".join(profile_instructions)

# Generates a prompt if the user has context.
def get_user_context_prompt(context: Optional[str] = None) -> str:
    """
    Creates a prompt section that instructs the model on how to use the learner's specific interests
    to frame the course content without altering the core information from the source text.
    """
    if not context:
        return "No context."
    return f"""
User Content Focus (treat as preference, not a source of new facts):
- The learner has a specific interest in: "{context.strip()}"
- When generating modules, learning objectives, and assessments:
  * Ensure the course REMAINS COMPREHENSIVE and covers ALL major topics in the source text.
  * DO NOT remove valid modules just because they don't match the user's specific interest.
  * Instead, use the context to frame the "Learning Objectives" and "Why this matters" sections where applicable.
  * If the context mentions time periods, events, or themes (e.g., "Middle Ages," "Crusades"), emphasize those in titles, descriptions, and objectives — **but only if they appear in the source text**.
  * Do NOT invent content that is not present in the reference snippets, even if the user requests it.
"""

# Generates the complete prompt for the initial blueprint generation.
def get_prompt(formatted_chunks: str, validation_errors: list = None, learner_profile: Dict[str, Any] | None = None, context: Optional[str] = None) -> str:
    """
    Assembles the final, detailed prompt for the generative model, including instructions,
    the JSON schema, learner profile, user context, and the source text.
    """
    prompt = f"""
You are an expert AI instructional designer. Your task is to generate a comprehensive course blueprint
from the provided source text, formatted as a perfect JSON object.

Follow these instructions precisely:
1.  **Analyze the Source Text**: Read the provided text chunks to understand the content.
2.  **Use Learner Profile**: Adjust the course to match the Learner Profile (tone, complexity, learning styles).
3.  **Use Context**: If a learner's interest is provided, emphasize related topics, but DO NOT add or remove content.
4.  **Create Modules**:
    - Create a comprehensive list of modules, with one module for each distinct major topic found in the source text.
    - The number of modules should be dictated by the source material, not a fixed number.
    - Do not summarize or combine distinct topics into a single module unless they are very small.
5.  **Estimate Time**: Provide a realistic "estimated_minutes" for each module (e.g., 5, 10, 15).
6.  **Define Objectives**: For each module, write 2-5 clear, measurable learning objectives.
    Each objective MUST start with a measurable verb (like "Define", "Apply", "Analyze").
7.  **Create Assessments**: For each module, write 2-5 assessment questions (e.g., multiple choice, short answer, true or false)
    that directly test the learning objectives.
    - **Do NOT** include answer choices, only the question.
8.  **Ensure Completeness**: The final blueprint must be comprehensive, fully covering all topics
    presented in the source text. Do not skip or omit information.
9.  **Format**: Respond with *only* the JSON object, adhering to the schema.

### JSON Schema:
{{
  "course_title": "<A concise and descriptive title for the course>",
  "course_description": "<A 1-2 sentence summary of what the course covers>",
  "modules": [
    {{
      "module_title": "<Title of Module 1>",
      "estimated_minutes": <int>,
      "learning_objectives": [
        "<Objective 1 for Module 1>",
        "<Objective 2 for Module 1>"
      ],
      "assessment_questions": [
        "<Question 1 for Module 1>",
        "<Question 2 for Module 1>"
      ]
    }},
    {{
      "module_title": "<Title of Module 2>",
      "estimated_minutes": <int>,
      "learning_objectives": [
        "<Objective 1 for Module 2>"
      ],
      "assessment_questions": [
        "<Question 1 for Module 2>"
      ]
    }}
  ]
}}

If an error occurs in formatting or structure, revise and correct the full output.

### Learner Profile:
{get_profile_context_prompt(learner_profile)}

### Context:
{get_user_context_prompt(context)}

### Source Text:
{formatted_chunks}
"""
    # If there are any validation errors, add them to the prompt for correction.
    if validation_errors:
        error_feedback = "\n".join(validation_errors)
        prompt += f"\n⚠️ Your previous response had validation issues. Please fix the following:\n{error_feedback}"
    return prompt

# Generates the prompt for the Revision Router. This model's only job is to clasify the request as "Patch" or "Regenerate."
def get_revision_router_prompt(feedback: str) -> str:
    """
    Call the model to classify the user's feedback as either a 'PATCH' (minor change)
    or 'REGENERATE' (major change) request.
    """
    return f"""You are an expert Instructional Design Project Manager.
Review the user's feedback on a course blueprint and categorize the request.

User Feedback: "{feedback}"

Determine if this request requires:
1. "PATCH": Small, specific changes (e.g., "change the title of module 1", "add a learning objective", "fix a typo").
2. "REGENERATE": Large, structural changes (e.g., "rewrite the whole course", "change the target audience", "merge all modules").

Respond with *only* the single word 'PATCH' or 'REGENERATE'.
"""

# Generates the prompt for the 'JSON Patcher'. 
def get_json_patch_prompt(feedback: str, current_blueprint_json: str, validation_errors: List[str]) -> str:
    """
    Creates a prompt for the JSON patcher model. Inputs are the user's feedback and the
    current JSON blueprint to be modified.
    """
    prompt = f"""
You are a JSON editing assistant. You have an existing Course Blueprint JSON and a user request.

User Request: "{feedback}"

Task: Surgically apply the user's requested change to the JSON.
- Modify the JSON to satisfy the user request. You MUST adhere to the user's request exactly.
- Do NOT change fields that are not requested.
- The output must be the complete, modified, and valid JSON matching the original schema.

Output only the modified JSON.

Existing Blueprint:
{current_blueprint_json}
"""
    # If there are any validation errors, add them to the prompt for correction.
    if validation_errors:
        error_feedback = "\n".join(validation_errors)
        prompt += f"\n⚠️ Your previous response had validation issues. Please fix the following:\n{error_feedback}"
    return prompt

def generate_blueprint_from_chunks(
    model: GenerativeModel,
    chunks: list,
    previous_errors: list = None,
    reviewer_feedback: Optional[str] = None,
    learner_profile: Dict[str, Any] | None = None,
    context: Optional[str] = None,
) -> str:
    """Generates the course blueprint by calling the Vertex AI API."""
    # Format the raw text chunks into a single string for the model prompt.
    formatted_chunks = "\n".join([
        f"- Page {c.get('page_number', 'N/A')}, Type: {c.get('element_type', 'text')}: \"{c.get('chunk_text', '')}\""
        for c in chunks if c.get('chunk_text', '')
    ])

    if not formatted_chunks:
        print("Warning: No valid text chunks found to process.")
        return "{}"

    # Include reviewer feedback in the prompt if it exists.
    feedback_context = (
        f"\nThe SME provided the following revision request: '{reviewer_feedback}'. "
        "Please incorporate this feedback when refining the blueprint.\n"
        if reviewer_feedback else ""
    )
        
    # Assemble the full prompt text.
    prompt_text = get_prompt(feedback_context + formatted_chunks, previous_errors, learner_profile, context)

    # Configure the generation settings for the model, including temperature and response format.
    generation_config = GenerationConfig(
        temperature=0.2,
        response_mime_type='application/json'
    )

    print("\n--- Sending Prompt to Model ---")
    # Call the generative model with the prompt and configuration.
    response = model.generate_content(prompt_text, generation_config=generation_config)

    try:
        # Safely extract the generated text from the model's response.
        return response.candidates[0].content.parts[0].text
    except (IndexError, AttributeError) as e:
        print(f"Warning: Could not extract text from model response. Response: {response}. Error: {e}")
        return "{}"

# Calls the router model to classify feedback as 'PATCH' or 'REGENERATE'.
# Returns the raw string response from the model.
def get_revision_route(model: GenerativeModel, feedback: str) -> str:
    """
    Calls the model to classify the user's feedback as either a 'PATCH' (minor change)
    or 'REGENERATE' (major change) request.
    """
    prompt = get_revision_router_prompt(feedback)
    
    generation_config = GenerationConfig(
        temperature=0.0 # We want this to be deterministic
    )
    
    print("--- Calling Model (Revision Router)... ---")
    
    try:
        # Generate the classification from the model.
        response = model.generate_content(prompt, generation_config=generation_config)
        action = response.candidates[0].content.parts[0].text.strip().upper()
        
        # Default to 'REGENERATE' if the model returns an unexpected value.
        if action not in ["PATCH", "REGENERATE"]:
            print(f"Warning: Router returned an unexpected value: '{action}'. Defaulting to REGENERATE.")
            return "REGENERATE"
            
        return action
    except Exception as e:
        # Default to 'REGENERATE' in case of any error during the routing process.
        print(f"An error occurred during routing: {e}. Defaulting to REGENERATE.")
        return "REGENERATE"

# Calls the patcher model to surgically edit a JSON string.
# This is a single-shot call, intended to be used inside a retry loop by an agent.   
def patch_blueprint_json(
    model: GenerativeModel, 
    feedback: str, 
    current_blueprint_json: str,
    previous_errors: list = None
) -> str:
    """
    Calls a model to apply a specific change to a JSON blueprint based on user feedback.
    """
    prompt = get_json_patch_prompt(feedback, current_blueprint_json, previous_errors)
    
    generation_config = GenerationConfig(
        temperature=0.1, # Low temp to follow instructions, but not zero
        response_mime_type='application/json'
    )
    
    print("--- Calling Model (JSON Patcher)... ---")
    
    try:
        # Generate the patched JSON.
        response = model.generate_content(prompt, generation_config=generation_config)
        return response.candidates[0].content.parts[0].text
    except (IndexError, AttributeError) as e:
        # Return an empty JSON object if text extraction fails.
        print(f"Warning: Could not extract text from patcher model. Response: {response}. Error: {e}")
        return "{}"
    except Exception as e:
        # Return an empty JSON object on any other unexpected error.
        print(f"An unexpected error occurred during model patching: {e}")
        return "{}"
