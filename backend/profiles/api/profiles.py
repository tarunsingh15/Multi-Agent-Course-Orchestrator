"""
Provides CRUD (Create, Read, Update, Delete) operations for user profiles stored in Firestore, with validation via Pydantic.

Supports:
  Create
  List all
  Get by ID
  Update / Partial update
  Delete
"""
from typing import List, Optional, Dict, Any

from google.cloud import firestore
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator, ConfigDict

router = APIRouter()

def _profiles_collection():
    """Initializes the Firestore client and returns the 'profiles' collection reference."""
    db = firestore.Client()
    collection = db.collection("profiles")
    return collection

# Pydantic Schemas for data validation and serialization.
class ProfileBase(BaseModel):
    """
    Base model for a user profile, defining the core fields and their validators.
    This model is inherited by other models for specific operations (POST, PUT, GET).
    """
    uid: str | None = None
    complexity: str | None = None
    tone: str | None = None
    learningStyles: list[str] | None = None

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "tone": "conversational",
                "complexity": "beginner",
                "learningStyles": ["visual", "analogies"]
            }
        }
    )
    
    # Field validators ensure data integrity before processing.
    @field_validator("tone","complexity")
    @classmethod
    def non_empty_str(cls, v:str) -> str:
        """Validator to ensure that 'tone' and 'complexity' are non-empty strings."""
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Must be a non-empty string")
        return v.strip()
    
    @field_validator("learningStyles")
    @classmethod
    def non_empty_list(cls, v: List[str]) -> List[str]:
        """Validator to ensure 'learningStyles' is a non-empty list of non-empty strings."""
        if not v:
            raise ValueError("List cannot be empty")
        if any((not isinstance(x, str) or not x.strip()) for x in v):
            raise ValueError("All items in the list must be non-empty strings")
        return [x.strip() for x in v]
    
class ProfilePOST(ProfileBase):
    """Model for creating a new profile via a POST request."""
    pass

class ProfilePUT(ProfileBase):
    """Model for updating a profile via a PUT request."""
    pass

class ProfileGET(ProfileBase):
    """Model for representing a profile in a GET response."""
    pass

class ProfilePATCH(BaseModel):
    """
    Model for partially updating a profile via a PATCH request.
    All fields are optional to allow for updating only specific attributes.
    """
    tone: Optional[str] = None
    complexity: Optional[str] = None
    learningStyles: Optional[List[str]] = None

    # Field validators for optional fields, ensuring they are valid if provided.
    @field_validator("tone","complexity", mode='before')
    @classmethod
    def non_empty_str_optional(cls, v:Optional[str]) -> Optional[str]:
        """Validator for optional string fields. Ensures non-emptiness if a value is provided."""
        if v is not None and not v.strip():
            raise ValueError("Must be a non-empty string")
        return v.strip() if isinstance(v, str) else v
    
    @field_validator("learningStyles", mode='before')
    @classmethod
    def non_empty_list_optional(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validator for the optional 'learningStyles' list. Ensures non-emptiness if the list is provided."""
        if v is None:
            return v
        if not v:
            raise ValueError("List cannot be empty")
        if any((not isinstance(x, str) or not x.strip()) for x in v):
            raise ValueError("All items in the list must be non-empty strings")
        return [x.strip() for x in v]


def _doc_helper(doc) -> Dict[str, Any]:
    """Formats a Firestore document into a dictionary."""
    data = doc.to_dict()
    if not data:
        raise HTTPException(status_code=500, detail=f"Document {doc.id} has no data.")
    
    data["id"] = doc.id
    # Ensure essential fields are present in the document to prevent downstream errors.
    for k in ("tone", "complexity", "learningStyles"):
        if k not in data:
            raise HTTPException(status_code = 500, detail =f"Data format error in {doc.id}: Missing '{k}'")
    return data

# API ROUTES

@router.post("/", response_model=ProfileGET, status_code = status.HTTP_201_CREATED)
def create_profile(body: ProfilePOST):
    """
    Creates a new profile in the Firestore 'profiles' collection.
    """
    collection = _profiles_collection()
    # Add the new profile data (from the request body) to the collection.
    update_time, ref = collection.add(body.model_dump())
    snap = ref.get()
    return _doc_helper(snap)

@router.get("/", response_model = List[ProfileGET])
def list_profiles():
    """
    Retrieves a list of all profiles from the Firestore 'profiles' collection.
    """
    collection = _profiles_collection()
    # Stream all documents from the collection and format them for the response.
    return [_doc_helper(d) for d in collection.stream()]

@router.get("/{profile_id}", response_model=ProfileGET)
def get_profile(profile_id: str):
    """
    Retrieves a single profile by its document ID.
    """
    collection = _profiles_collection()
    snap = collection.document(profile_id).get()
    if not snap.exists:
        raise HTTPException(status_code =404, detail="Profile NOT FOUND")
    return _doc_helper(snap)

@router.put("/{profile_id}", response_model = ProfileGET)
def put_profile(profile_id: str, body: ProfilePUT):
    """
    Updates a profile using a PUT request. Fully replaces a profile by ID (or creates it if missing),
    while preventing changes to the existing uid field.
    """
    ref = _profiles_collection().document(profile_id)
    snap = ref.get()
    incoming = body.model_dump(exclude_unset=True)

    # Prevent modification of the UID if it's already set.
    if snap.exists:
        existing_uid = snap.to_dict().get("uid")
        incoming_uid = incoming.get("uid")
        if existing_uid and incoming_uid and incoming_uid != existing_uid:
            raise HTTPException(status_code=400, detail="UID once set cannot be changed")
    else:
        pass

    # Use set with merge=True to update or create the document.
    ref.set(incoming, merge=True)
    return _doc_helper(ref.get())

@router.patch("/{profile_id}", response_model=ProfileGET)
def patch_profile(profile_id: str, body: ProfilePATCH):
    """
    Partially updates a profile so only the fields provided in the request body will be modified.
    """
    collection = _profiles_collection()
    ref = collection.document(profile_id)

    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Profile NOT FOUND")
    
    # Get updates from the request body, excluding any fields that were not set.
    updates = body.model_dump(exclude_unset=True)
    updates.pop("uid", None)
    
    # Apply the updates to the document if there are any.
    if updates:
        ref.update(updates)
    return _doc_helper(ref.get())

@router.delete("/{profile_id}", status_code =status.HTTP_204_NO_CONTENT)
def delete_profile(profile_id: str):
    """
    Deletes a profile from the Firestore 'profiles' collection by its ID.
    """
    collection = _profiles_collection()
    ref = collection.document(profile_id)
    if not ref.get().exists:
        raise HTTPException(status_code =404, detail = "Profile NOT FOUND")
    ref.delete()
    # Return None with a 204 status code on successful deletion.
    return None