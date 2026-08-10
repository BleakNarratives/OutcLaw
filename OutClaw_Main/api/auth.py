import os, sqlite3, uuid
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext

SECRET_KEY = os.getenv("JWT_SECRET", "change-me")
ALGORITHM = "HS256"
# Use /tmp for writable storage on Vercel
DB_PATH = Path(__file__).parent.parent / "outclaw.db"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer()

def init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL, subscribed INTEGER DEFAULT 0)""")
        c.commit()

def _conn(): return sqlite3.connect(DB_PATH)

def get_user_by_email(email):
    with _conn() as c:
        row = c.execute("SELECT id,email,hashed_password,subscribed FROM users WHERE email=?", (email,)).fetchone()
    return {"id":row[0],"email":row[1],"hashed_password":row[2],"subscribed":bool(row[3])} if row else None

def get_user_by_id(uid):
    with _conn() as c:
        row = c.execute("SELECT id,email,hashed_password,subscribed FROM users WHERE id=?", (uid,)).fetchone()
    return {"id":row[0],"email":row[1],"hashed_password":row[2],"subscribed":bool(row[3])} if row else None

def create_user(email, password):
    if get_user_by_email(email): raise HTTPException(status_code=409, detail="Email already registered")
    uid = str(uuid.uuid4())
    with _conn() as c:
        c.execute("INSERT INTO users (id,email,hashed_password) VALUES (?,?,?)", (uid, email, pwd_context.hash(password)))
        c.commit()
    return {"id": uid, "email": email}

def authenticate_user(email, password):
    u = get_user_by_email(email)
    return u if u and pwd_context.verify(password, u["hashed_password"]) else None

def activate_subscription(uid):
    with _conn() as c: c.execute("UPDATE users SET subscribed=1 WHERE id=?", (uid,)); c.commit()

def deactivate_subscription(uid):
    with _conn() as c: c.execute("UPDATE users SET subscribed=0 WHERE id=?", (uid,)); c.commit()

def create_access_token(uid, email):
    exp = datetime.utcnow() + timedelta(days=30)
    return jwt.encode({"sub": uid, "email": email, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    try:
        p = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        uid = p.get("sub")
    except JWTError: raise HTTPException(status_code=401, detail="Invalid token")
    u = get_user_by_id(uid)
    if not u: raise HTTPException(status_code=401, detail="User not found")
    return u

def require_subscription(user: dict = Depends(get_current_user)):
    if not user.get("subscribed"): raise HTTPException(status_code=402, detail="Subscription required")
    return user
