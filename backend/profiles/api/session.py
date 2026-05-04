"""
Resolves a user session by email:

  If the user exists, returns their UID and profile
  If not, creates a new UID, default profile, and email-to-UID mapping
"""
from fastapi import APIRouter
from google.cloud import firestore
from pydantic import BaseModel, EmailStr
from utils.idgen import generate_uid

router = APIRouter()
db = firestore.Client()

#Input validation for the email inputs
class ResolveEmailBody(BaseModel):
    email : EmailStr

def _norm(e: str) -> str:
    """Normalizes an email string by stripping whitespace and converting to lowercase."""
    return e.strip().lower()

def _get_def_profile(uid):
    """Returns a dictionary containing the default profile for a new user."""
    return {
            "uid": uid,
            "complexity": "intermediate",
            "tone":"casual",
            "learningStyles":["reading"],
        }

@router.post("/resolve-email")
def resolve_email(body: ResolveEmailBody):
    """
    Resolves a user's email to a UID and profile.
    Creates a new user and profile if one does not already exist.
    """
    email = body.email
    n = _norm(email)

    # points to lookup document
    users_ref = db.collection("users").document(n)
    profiles_ref = db.collection("profiles")
    
    # Using Transactions to prevent any race conditions
    transaction = db.transaction()

    @firestore.transactional
    def run(tx: firestore.Transaction):
        """
        Executes the logic for resolving the email within a transaction.
        """
        mapping = users_ref.get(transaction=tx)
        
        # Case 1: The user already exists.
        if mapping.exists:
            data = mapping.to_dict()
            uid = data["uid"]
            prof_doc_id = data.get("profileDocId")

            # If a direct profile document ID exists, fetch that profile.
            if prof_doc_id: 
                prof_ref = profiles_ref.document(prof_doc_id)
                prof_snap = prof_ref.get(transaction=tx)
                if prof_snap.exists:
                    profile_data = prof_snap.to_dict()
                    profile_data["id"] = prof_snap.id
                    return {"uid": uid, "profile": profile_data, "created": False, "message": "Welcome back!!"}
            
            # Fallback: If no direct ID, find the profile by querying for the UID.
            uid_mapping_in_profile = profiles_ref.where("uid", "==", uid).limit(1).stream(transaction=tx)
            prof_snap_list = list(uid_mapping_in_profile)
            
            if prof_snap_list:
                prof_snap = prof_snap_list[0]
                # Update the user mapping with the found profile ID for faster lookups next time.
                tx.update(users_ref , {"profileDocId": prof_snap.id})
                
                profile_data = prof_snap.to_dict()
                profile_data["id"] = prof_snap.id
                return {"uid": uid, "profile": profile_data, "created": False ,"message": "Welcome back!!"}
            pass
            
        # Case 2: This is a new user.
        uid = generate_uid()
        new_prof_ref = profiles_ref.document()
        default_prof = _get_def_profile(uid)

        tx.set(new_prof_ref, default_prof)      #creates a profile collection
        tx.set(users_ref, {"profileDocId": new_prof_ref.id, "uid": uid})
        
        default_prof["id"] = new_prof_ref.id
        return {"uid": uid, "profile": default_prof, "created": True, "message": "Welcome User!!!"}     #created = True --> when a new profile/mapping is created
    
    return run(transaction) #executes transactions and returns its result


            



