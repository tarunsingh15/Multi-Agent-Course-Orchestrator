# Note: Parts of this code were generated with Google's Gemini. The program was reviewed, modified, and tested to
# ensure functionality.
"""
Generates and revises lesson content using Retrieval-Augmented Generation (RAG) and Google Cloud services (Firestore for job tracking, GCS for file storage).

Key functions:

generate_lessons_from_blueprint:
Retrieves relevant text chunks from the parsed document embeddings, builds a context-rich prompt, and uses a generative model to create Markdown lessons aligned to the blueprint.

revise_single_lesson:
Uses evaluator feedback to produce an improved lesson version.

GCS utilities:
Load/save lesson artifacts and handle GCS URI parsing.
"""

from datetime import datetime, timezone
from google.cloud import firestore, storage
from vertexai.generative_models import GenerativeModel, GenerationConfig
import os
import json
from urllib.parse import unquote, urlparse
from typing import Optional, Dict, Any
import vertexai
from datetime import datetime, timezone
import time

from agents.rag_utils import RAGManager

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "amazing-math-473517-f9")
BUCKET_NAME = 'mari-uploads-ns-uc1-east4'

#===================================================================================
### Helper Functions found in GCS_IO.py added here to ensure docker works ###
# These are utility functions for interacting with Google Cloud Storage. They are
# included directly in this module to simplify the Docker container's dependencies.

def split_gcs_uri(gcs_uri: str):
    """Accepts either gs:// or https://storage.googleapis.com/..."""
    if gcs_uri.startswith("gs://"):
        parts = gcs_uri[5:].split("/", 1)
        return parts[0], parts[1]
    elif "storage.googleapis.com" in gcs_uri:
        parsed = urlparse(gcs_uri)
        path_parts = parsed.path.lstrip("/").split("/", 1)
        if len(path_parts) < 2:
            raise ValueError(f"Unexpected GCS URL format: {gcs_uri}")
        return path_parts[0], path_parts[1]
    else:
        raise ValueError(f"Not a valid GCS or HTTPS GCS URI: {gcs_uri}")
    
def download_json_from_uri(uri: str):
    """Download JSON either from a gs:// URI (private via GCS client)
       or from a public HTTPS URL."""
    
    if uri.startswith("gs://"):
        bucket_name, blob_name = split_gcs_uri(uri)
        client = storage.Client()
        blob = client.bucket(bucket_name).blob(blob_name)
        txt = blob.download_as_text()
        return json.loads(txt)
    elif uri.startswith("http://") or uri.startswith("https://"):
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        blob_name = uri.split(f"{BUCKET_NAME}/")[-1]
        blob_name = unquote(blob_name)  
        blob = bucket.blob(blob_name)
        return json.loads(blob.download_as_text())
    else:
        raise ValueError(f"Unsupported URI format: {uri}")
    
def download_text_from_uri(uri: str) -> str:
    """Downloads raw text content from a GCS URI."""
    try:
        bucket_name, blob_name = split_gcs_uri(uri)
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        content = blob.download_as_string().decode("utf-8")
        return content
    except Exception as e:
        print(f"Error downloading text from {uri}: {e}")
        return ""
#===================================================================================

### Main Function to Generate Lessons
def generate_lessons_from_blueprint(job_id: str):
    """
    Generates Markdown lesson content for each module in a course blueprint.
    - Pulls blueprint + learner profile from Firestore
    - Uses Gemini to create Markdown lessons
    - Uploads each lesson to GCS
    - Updates Firestore with public URIs
    """
    db = firestore.Client(project=PROJECT_ID)
    job_doc = db.collection("jobs").document(job_id).get()
    if not job_doc.exists:
        raise ValueError(f"Job {job_id} not found in Firestore")

    # Extract necessary data from the job document.
    job_data = job_doc.to_dict() or {}
    results = job_data.get("results", {})
    blueprint_gcs_uri = results.get("blueprint_gcs_uri")
    parsed_chunks_uri = results.get("parsed_chunks_gcs_uri")
    
    # Download the blueprint and get learner profile/context.
    blueprint = download_json_from_uri(blueprint_gcs_uri)
    learner_profile = job_data.get("learnerProfile", {})
    inputs = job_data.get("inputs", {}) 
    context: Optional[str] = inputs.get("context")

    if not blueprint:
        raise ValueError("No blueprint found for this job")

    modules = blueprint.get("modules", [])
    if not isinstance(modules, list):
        raise ValueError("Blueprint modules are not a list")

    # Initialize the generative model and GCS client.
    model = GenerativeModel("gemini-2.5-pro")
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)

    # Initialize the RAG manager for context retrieval.
    rag_manager = RAGManager()
    lessons_output = {}
    lesson_uris = {}

    # Iterate over each module in the blueprint to generate a lesson.
    for module in modules:
        if not isinstance(module, dict):
            continue  

        module_title = module.get("module_title", "Untitled Module")
        objectives = module.get("learning_objectives", [])
        assessments = module.get("assessment_questions", [])
        est_minutes = module.get("estimated_minutes", 10)
        
        # 1. Perform RAG retrieval to get relevant context for the module.
        print(f"Retrieving context for moduel: {module_title}")
        rag_query = f"{module_title} {' '.join(objectives)}"
        rag_context = ""
        
        if parsed_chunks_uri:
            rag_context = rag_manager.get_combined_context(rag_query, parsed_chunks_uri)
        else:
            print("WARNING: No parsed_chunks_uri found. SKippings internal RAG step")
            
        # 2. Construct the lesson generation prompt for the generative model.
        context_prompt_section = ""
        if context:
            context_prompt_section = f"""
User Learning Context (for emphasis only, do NOT introduce new topics):
- The learner is especially interested in: "{context.strip()}"

When writing the lesson:
- Emphasize and elaborate on parts of this module that relate to this context.
- You may reorder or expand explanations to better serve this focus.
- DO NOT introduce new topics or objectives that are not present in the module.
"""

        prompt = f"""
You are an expert Instructional Designer creating educational lesson content.

Your task: Generate a complete, well-structured Markdown lesson for the module using the details provided below to match the user's learner profile.

# CONTENT GUIDELINES

## STRICT GROUNDING INSTRUCTIONS (CRITICAL)
1. **Source of Truth**: You MUST base your content primarily on the provided "RAG Context" below.
2. **No Hallucinations**: Do not invent facts, statistics or historical events not present in the context or general knowledge.
3. **Citations**: If you reference a specific concept from the "Uploaded Materials", append [Source: User Doc]. If you reference an "External Reference", append [Source: OpenLibrary/External].
4. **Copyright**": Do not reproduce large blocks of text verbatim. Synthesize and summarize the information.

{rag_context}

## What You Can Use
✓ General educational knowledge equivalent to what appears in:
  - Encyclopedia entries (Wikipedia, Britannica)
  - Government educational resources
  - Open-access academic publications
  - Standard textbook concepts (express in your own words)
  - Widely-known facts and principles in the field

✓ Create original examples, scenarios, and explanations
✓ Use analogies and thought experiments
✓ Design practice activities aligned with objectives

## What You Cannot Use
✗ Direct quotes or close paraphrasing from specific textbooks
✗ Proprietary course materials or paid curricula
✗ Subscription-only journal content
✗ Specific commercial course platforms

## Scope Requirements
- Address ALL learning objectives provided
- Stay within the module's defined scope
- Do not introduce objectives not listed below
- If information seems insufficient, provide high-level explanation using foundational concepts

{context_prompt_section}

# MODULE INFORMATION

**Module Title:** {module_title}

**Estimated Duration:** {est_minutes} minutes

**Learning Objectives:**
{chr(10).join(f"{i+1}. {obj}" for i, obj in enumerate(objectives)) if objectives else "None provided"}

**Assessment Focus Areas:**
{chr(10).join(f"- {q}" for q in assessments[:3]) if assessments else "Context will be derived from objectives"}

**Learner Profile:**
{learner_profile}

# OUTPUT FORMAT

Structure your lesson exactly as follows in valid Markdown:

## {module_title}
**Estimated Time: {est_minutes} minutes**

### Introduction
[2-3 paragraphs introducing the topic, explaining its importance, and previewing what will be covered. Connect to real-world applications where relevant.]

### Objective: [First Learning Objective]
[2-3 paragraphs explaining the concept clearly at the appropriate level]

**Example:** [One concrete, original example or scenario that illustrates the concept]

**Practice:** [Optional: A brief activity or thought exercise if appropriate]

### Objective: [Second Learning Objective]
[Continue the same pattern for each objective]

###Objective: [Additional Objectives]
[Repeat for all objectives provided]

### Key Takeaways
- [3-5 bullet points summarizing the most important concepts]

### Reflection
[1-2 thought-provoking questions or a brief reflection prompt that encourages learners to connect the material to their own context]

### Further Learning/References
[2-4 references following the guidelines below]

# REFERENCE GUIDELINES

Include 2-4 high-quality public resources when available. 

**PRIORITY ORDER** (use higher-priority sources first):

**TIER 1 - Primary Authoritative Sources (USE THESE FIRST):**

**U.S. Government Resources (.gov domains):**
- NASA: https://www.nasa.gov/ (space, science, technology)
- NOAA: https://www.noaa.gov/ (climate, weather, oceans)
- CDC: https://www.cdc.gov/ (health, medicine)
- NIH: https://www.nih.gov/ (biomedical research)
- NIST: https://www.nist.gov/ (standards, technology, physics)
- USGS: https://www.usgs.gov/ (geology, geography, natural resources)
- USA.gov: https://www.usa.gov/ (civics, government)
- Energy.gov: https://www.energy.gov/ (energy, physics)

**Open Academic:**
- arXiv: https://arxiv.org/ (physics, math, CS, engineering)
- PubMed Central: https://www.ncbi.nlm.nih.gov/pmc/ (biomedical, open access)
- PLOS: https://plos.org/ (open science journals)
- Directory of Open Access Journals: https://doaj.org/

**Technology & Standards:**
- MDN Web Docs: https://developer.mozilla.org/
- Python Documentation: https://docs.python.org/
- W3C: https://www.w3.org/
- IETF RFCs: https://www.ietf.org/rfc/

**International Organizations:**
- WHO: https://www.who.int/ (global health)
- UNESCO: https://www.unesco.org/ (education, science, culture)
- UN Data: https://data.un.org/ (statistics, development)
- World Bank: https://www.worldbank.org/ (economics, development data)
- OECD: https://www.oecd.org/ (economics, policy, statistics)

**TIER 2 - Academic & Educational Resources:**

**Open Academic:**
- arXiv: https://arxiv.org/ (physics, math, CS, engineering)
- PubMed Central: https://www.ncbi.nlm.nih.gov/pmc/ (biomedical, open access)
- PLOS: https://plos.org/ (open science journals)
- Directory of Open Access Journals: https://doaj.org/

**Educational Platforms (Open Content):**
- MIT OpenCourseWare: https://ocw.mit.edu/
- OpenStax: https://openstax.org/ (free peer-reviewed textbooks)
- Stanford Encyclopedia of Philosophy: https://plato.stanford.edu/
- Internet Archive Scholar: https://scholar.archive.org/

**TIER 3 - General Reference (USE ONLY IF NO TIER 1-2 SOURCES AVAILABLE):**
- Wikibooks: https://en.wikibooks.org/wiki/[topic]
- Wikiversity: https://en.wikiversity.org/wiki/[topic]
- Wikipedia: https://en.wikipedia.org/wiki/[topic] (last resort for general overviews)

**Selection Strategy:**
1. ALWAYS check for government or organizational sources first (.gov, .int, .org)
2. Prefer peer-reviewed open access publications for academic topics
3. Use specialized educational platforms before general encyclopedias
4. Only use Wikipedia if no Tier 1-2 sources cover the topic adequately

**Format:**

All references MUST use Markdown hyperlink syntax so they are fully clickable and navigable.

Use the exact format:
- [Short description](Full URL)

**Format & Navigability Rules:**

1. **MANDATORY LINKING:** Every reference MUST be a fully clickable Markdown hyperlink.

2. **SYNTAX:** Use the exact format:
   - [Descriptive Source Title](https://example.org) - short description

3. **NO PLAIN TEXT REFERENCES:** 
   - Do NOT list authors, dates, publishers, or ISBNs.
   - Do NOT include any reference without a URL.
   - If a valid URL cannot be confirmed, exclude the reference entirely.

4. **URL SAFETY RULE:** 
   - If you are not 100% certain that a specific deep link exists, you MUST link to the organization’s main landing page, topic directory, or search portal.
   - Example of a safe fallback:  
     - [NASA — Official Site](https://www.nasa.gov/)  
     - NOT: guessed deep links like `https://www.nasa.gov/climate/overview-12345`

5. **LABELS:** 
   - Link text must be clear and descriptive (e.g., “CDC — Nutrition Basics”).
   - Avoid vague labels like “Click here,” “Learn more,” or auto-generated article titles.

6. **MAXIMUM:** 4 references total.

# EXECUTION INSTRUCTIONS

1. **Output ONLY valid Markdown** - no code blocks, no wrapper formatting
2. Start directly with the `## {module_title}` heading
3. Do NOT include these instructions in your output
4. Do NOT add meta-commentary, explanations, or preambles
5. Do NOT wrap the output in ```markdown ``` code blocks
6. Ensure all content directly supports the learning objectives
7. Match the tone and complexity to the learner profile
8. Use clear, engaging language with concrete examples
9. Make the lesson self-contained and immediately useful
10. Return raw Markdown text that can be directly saved as a .md file

Begin generating the lesson now - output the Markdown directly:"""
  
        # 3. Call the model and get the generated lesson text.
        response = model.generate_content(prompt)
        markdown_text = response.text.strip()
        lessons_output[module_title] = markdown_text

        # 4. Upload the generated Markdown to a new blob in GCS.
        safe_name = module_title.replace(" ", "_").lower() + ".md"
        blob_path = f"jobs/{job_id}/lessons/{safe_name}"
        blob = bucket.blob(blob_path)
        blob.upload_from_string(markdown_text, content_type="text/markdown")

        uri = f"gs://{BUCKET_NAME}/{blob_path}"
        lesson_uris[module_title] = uri

        # Log the update in Firestore for this specific module.
        print(f"Generated and uploaded lesson for module: {module_title}")
        db.collection("jobs").document(job_id).update({
            "updateLog": firestore.ArrayUnion([{
                "time": datetime.now(timezone.utc),
                "message": f'Lesson for module "{module_title}" generated and uploaded.'
            }])
        })
        
    # 5. After all lessons are generated, update the main job document in Firestore.
    merged_results = {**results, "lesson_gcs_uris": lesson_uris}
    db.collection("jobs").document(job_id).update({
        "status": "LESSON_GENERATED",
        "results": merged_results,
        "updateLog": firestore.ArrayUnion([{
                "time": datetime.now(timezone.utc),
                "message": 'Lessons generated successfully! They can be viewable in UI'  
        }])
    })

    print(f"Lessons generated and stored for job {job_id}")
    return {"lesson_uris": lesson_uris, "lesson_markdown_by_module": lessons_output}

# Lesson Revision Prompt
def get_lesson_revision_prompt(module_title: str, failed_markdown: str, critique_reasoning: str, learner_profile: Dict[str, Any], context: Optional[str] = None) -> str:
    """
    Creates the prompt for revising a lesson based on evaluator feedback after failing quality checks
    """
    profile_prompt_section = ""

    if learner_profile:
        tone = learner_profile.get("tone")
        complexity = learner_profile.get("complexity")
        styles = learner_profile.get("learningStyles", [])

        profile_instructions = []
        if tone:
            profile_instructions.append(f"- Adopt a '{tone}' tone.")
        if complexity:
            profile_instructions.append(f"- Target a '{complexity}' complexity level.")
        if styles:
            style_str = ", ".join(styles)
            profile_instructions.append(f"- Incorporate learning styles such as: {style_str}.")

        if profile_instructions:
            profile_prompt_section = "\nLearner Profile Preferences:\n" + "\n".join(profile_instructions)

    return f"""
You are an expert instructional designer. Your task is to revise a lesson module that has failed a quality check.

## FAILED MODULE: {module_title}

## EVALUATOR'S CRITIQUE:
"{critique_reasoning}"

## FAILED LESSON CONTENT:
---
{failed_markdown}
---

## USER LEARNER PROFILE:
{profile_prompt_section}

## USER CONTEXT:
The user specifically wants {context.strip()}

## YOUR TASK:
Rewrite the "FAILED LESSON CONTENT" to directly address all points in the "EVALUATOR'S CRITIQUE".
-   If the critique mentions factual errors, you MUST correct them.
-   If the critique mentions confusing language, you MUST rewrite it for clarity.
-   If the critique mentions missing alignment, you MUST add content to align with the objectives.
-   Do NOT change the module title.
-   The output MUST be the complete, revised lesson in valid Markdown format.

Return *only* the revised Markdown.
"""

def revise_single_lesson(job_id: str, module_title: str, critique_reasoning: str):
    """
    Revises a single lesson based on feedback, generates a new version,
    and uploads it to GCS, preserving the old version.
    """
    print(f"Starting revision for job {job_id}, module: {module_title}")
    db = firestore.Client(project=PROJECT_ID)
    job_ref = db.collection("jobs").document(job_id)
    job_doc = job_ref.get()

    if not job_doc.exists:
        raise Exception(f"Job not found: {job_id}")

    # Fetch all necessary data from the job document.
    job_data = job_doc.to_dict()
    
    learner_profile = job_data.get("learnerProfile", {})
    inputs = job_data.get("inputs", {})
    context = inputs.get("context", "")
    results = job_data.get("results", {})
    lesson_uris = results.get("lesson_gcs_uris", {})

    # Find the URI for the specific module to be revised.
    module_uri = lesson_uris.get(module_title)
    if not module_uri:
        raise Exception(f"Could not find lesson URI for module: {module_title}")

    # Download the content of the failed lesson.
    print(f"Downloading failed lesson: {module_uri}")
    failed_markdown = download_text_from_uri(module_uri)
    if not failed_markdown:
        raise Exception(f"Failed to download markdown for module: {module_title}")

    # Initialize the generative model.
    vertexai.init(project=PROJECT_ID, location="us-central1")
    model = GenerativeModel("gemini-2.5-pro")
    
    # Construct the revision prompt.
    prompt = get_lesson_revision_prompt(
        module_title, 
        failed_markdown, 
        critique_reasoning, 
        learner_profile, 
        context
    )
    
    generation_config = GenerationConfig(
        temperature=0.2
    )
    
    # Call the model to get the revised lesson.
    print(f"Calling model to revise: {module_title}")
    response = model.generate_content(prompt, generation_config=generation_config)
    revised_markdown = response.text.strip()

    # Upload the revised lesson to GCS with a new, timestamped filename to preserve history.
    storage_client = storage.Client(project=PROJECT_ID)
    bucket_name, blob_name = split_gcs_uri(module_uri)
    bucket = storage_client.bucket(bucket_name)

    timestamp = int(time.time())
    base_name = blob_name.replace(".md", "")
    new_blob_name = f"{base_name}_rev{timestamp}.md"
    new_blob = bucket.blob(new_blob_name)
    print(f"Uploading revised lesson to: {new_blob_name}")
    new_blob.upload_from_string(revised_markdown, content_type="text/markdown")
    new_uri = f"gs://{bucket_name}/{new_blob_name}"

    # Log the revision event in Firestore.
    job_ref.update({
        "updateLog": firestore.ArrayUnion([{
            "time": datetime.now(timezone.utc),
            "message": f'Lesson for module "{module_title}" was revised based on feedback. New version: {new_blob_name}'
        }])
    })

    return {
        "message": f"Module '{module_title}' revised.",
        "new_uri": new_uri
    }