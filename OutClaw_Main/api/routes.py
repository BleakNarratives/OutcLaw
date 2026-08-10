import os, sys
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
sys.path.insert(0, str(Path(__file__).parent.parent))
from api.auth import (
    create_user, authenticate_user, create_access_token,
    get_current_user, require_subscription, get_user_by_email,
    activate_subscription
)

router = APIRouter()

class RegisterIn(BaseModel): email: EmailStr; password: str
class LoginIn(BaseModel): email: EmailStr; password: str
class IracIn(BaseModel): issue: str; facts: str; jurisdiction: str = "federal"
class FoiaIn(BaseModel): agency: str; subject: str; date_range: str = ""
class GrievanceIn(BaseModel): incident: str; respondent: str; relief_sought: str

@router.post("/auth/register")
def register(body: RegisterIn):
    u = create_user(body.email, body.password)
    return {"token": create_access_token(u["id"], u["email"]), "user_id": u["id"]}

@router.post("/auth/login")
def login(body: LoginIn):
    u = authenticate_user(body.email, body.password)
    if not u: raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": create_access_token(u["id"], u["email"]), "user_id": u["id"]}

@router.get("/auth/me")
def me(user: dict = Depends(get_current_user)):
    return {"id": user["id"], "email": user["email"], "subscribed": user.get("subscribed", False)}

# Admin endpoint – manually activate a user after Ko‑fi payment
@router.post("/admin/activate")
def admin_activate(email: str, secret: str):
    if secret != os.getenv("ADMIN_SECRET", "change-me"):
        raise HTTPException(status_code=403, detail="Invalid secret")
    user = get_user_by_email(email)
    if not user: raise HTTPException(status_code=404, detail="User not found")
    activate_subscription(user["id"])
    return {"ok": True, "email": email}

@router.post("/legal/irac")
def run_irac(body: IracIn, user: dict = Depends(require_subscription)):
    try:
        from outclaw_irac import analyze
        return {"result": analyze(issue=body.issue, facts=body.facts, jurisdiction=body.jurisdiction)}
    except (ImportError, AttributeError):
        return {"result": f"[IRAC stub] {body.issue[:80]}", "note": "module not wired"}

@router.post("/legal/foia")
def run_foia(body: FoiaIn, user: dict = Depends(require_subscription)):
    try:
        from outclaw_foia import generate
        return {"result": generate(agency=body.agency, subject=body.subject, date_range=body.date_range)}
    except (ImportError, AttributeError):
        return {"result": f"[FOIA stub] {body.agency}", "note": "module not wired"}

@router.post("/legal/grievance")
def run_grievance(body: GrievanceIn, user: dict = Depends(require_subscription)):
    try:
        from outclaw_grievance_generator import generate
        return {"result": generate(incident=body.incident, respondent=body.respondent, relief_sought=body.relief_sought)}
    except (ImportError, AttributeError):
        return {"result": f"[Grievance stub] vs {body.respondent[:60]}", "note": "module not wired"}

@router.post("/legal/score")
def score_case(body: IracIn, user: dict = Depends(require_subscription)):
    try:
        from outclaw_scorer import score
        return {"score": score(issue=body.issue, facts=body.facts)}
    except (ImportError, AttributeError):
        return {"score": {"strength": "moderate", "note": "scorer stub"}}
