from typing import List
import logging
import os
from fastapi import FastAPI, HTTPException, status, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

import models, schemas, crud
from database import engine, get_db

logger = logging.getLogger("research-portal")
logging.basicConfig(level=logging.INFO)

try:
    models.Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"[DATABASE WARNING] Could not run create_all on startup: {e}")

try:
    crud.ensure_superadmin()
except Exception as e:
    print(f"[SUPERADMIN WARNING] Could not ensure superadmin: {e}")

app = FastAPI(
    title="Research Management Portal (Role-Based)",
    description="Backend API with Admin, Faculty, and Student Management",
    version="2.2.0"
)

def _cors_origins():
    # Local defaults keep existing behaviour unchanged.
    origins = ["http://127.0.0.1:5501", "http://localhost:5501"]
    extra = os.environ.get("FRONTEND_URL", "").strip()
    if extra:
        # Comma-separated list supported, e.g. "https://app.vercel.app,https://x.onrender.com"
        for part in extra.split(","):
            part = part.strip().rstrip("/")
            if part and part not in origins:
                origins.append(part)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ---- Single-link deploy: serve frontend.html from backend root ----
# Local Live Server flow keeps working unchanged. On Render the same URL
# serves both UI (/) and API (/auth/..., /admin/...), so one public link
# is enough to share with everyone.
@app.get("/", include_in_schema=False)
def serve_frontend():
    here = os.path.abspath(os.path.dirname(__file__))
    path = os.path.join(here, "frontend.html")
    if os.path.exists(path):
        return FileResponse(path, media_type="text/html")
    return {"message": "Research Management Portal API. UI file not found on server."}

# ---- Server-side role verification (anti-spoof) ----
# Frontend injects X-User-Id + X-User-Role on every fetch (see frontend.html).
# Sensitive endpoints verify the pair against the user table instead of
# trusting the role string alone.
SENSITIVE_PREFIXES = (
    "/admin/students", "/admin/notifications", "/admin/proposal-responses",
    "/admin/applications", "/faculty/students",
    "/faculty/applications", "/faculty/notifications",
    "/student/",
)

def _check_auth(request: Request, db: Session):
    path = request.url.path
    # Public: auth, statistics, read-only project/faculty browsing
    if path.startswith("/auth/") or path.startswith("/statistics/"):
        return
    needs_auth = (
        path.startswith(SENSITIVE_PREFIXES)
        or path.startswith("/superadmin/")
        or (request.method in ("POST", "PUT", "DELETE")
            and (path.startswith("/admin/") or path.startswith("/faculty/") or path.startswith("/student/")))
    )
    if not needs_auth:
        return
    uid = request.headers.get("X-User-Id") or request.query_params.get("user_id")
    role = (request.headers.get("X-User-Role") or request.query_params.get("role") or "").strip().lower()
    # Legacy faculty endpoints also pass faculty_id/student_id as query param — accept as identity
    if not uid:
        uid = (request.query_params.get("faculty_id")
               or request.query_params.get("student_id"))
    if not uid or not role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Missing X-User-Id / X-User-Role headers. Please log in again.")
    row = db.execute(text("SELECT user_id, role FROM user WHERE user_id = :uid"),
                     {"uid": uid}).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user.")
    if str(row.role).strip().lower() != role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Role mismatch for this user.")
    # Read-only project/application browsing is open to any logged-in role
    # (faculty/student UIs and Statistics Hub depend on it).
    if request.method == "GET" and (
        path == "/admin/projects" or path.startswith("/admin/projects/")
        or path == "/admin/applications" or path.startswith("/admin/applications/")
    ):
        return
    if path.startswith("/admin/") and role not in ("admin", "superadmin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Admin access required.")
    if path.startswith("/superadmin/") and role != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Superadmin access required.")

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # CORS preflight (OPTIONS) never carries auth headers — let it pass so
    # CORSMiddleware can answer it. Otherwise browsers block every
    # authenticated call while non-browser clients keep working.
    if request.method == "OPTIONS":
        return await call_next(request)
    if request.url.path.startswith(("/admin", "/faculty", "/student")):
        db = next(get_db())
        try:
            _check_auth(request, db)
        except HTTPException as e:
            return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
        finally:
            try:
                db.close()
            except Exception:
                pass
    try:
        return await call_next(request)
    except Exception as e:
        logger.exception("Unhandled error on %s: %s", request.url.path, e)
        raise

@app.post("/auth/login", response_model=schemas.LoginResponse, tags=["Authentication Module"])
def login(login_data: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = crud.authenticate_user(db=db, login_data=login_data)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "role": user["role"],
        "message": f"Successfully logged in as {user['role']}"
    }

@app.post("/auth/send-otp", tags=["Authentication Module"])
def send_otp(req: schemas.SendOTPRequest, db: Session = Depends(get_db)):
    try:
        return crud.send_verification_otp(db=db, email=req.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/auth/forgot-password", tags=["Authentication Module"])
def forgot_password(req: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    try:
        return crud.send_password_reset_otp(db=db, email=req.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/auth/reset-password", tags=["Authentication Module"])
def reset_password(req: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    try:
        return crud.reset_password_with_otp(db=db, email=req.email, otp=req.otp,
                                            new_password=req.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/auth/check-student-unique", tags=["Authentication Module"])
def check_student_unique(req: schemas.StudentUniqueCheck, db: Session = Depends(get_db)):
    try:
        crud.check_student_unique(db=db, email=req.email, github_link=req.github_link, cv_link=req.cv_link, exclude_id=req.exclude_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/auth/signup/faculty", tags=["Authentication Module"])
def signup_faculty(faculty: schemas.FacultyCreate, db: Session = Depends(get_db)):
    if not faculty.otp or not crud.verify_otp(email=faculty.email, otp=faculty.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired verification code. Please request a new code.")
    try:
        # Create pending signup notification for admin approval
        created = crud.request_faculty_signup(db=db, faculty=faculty)
        return {"message": "Signup request submitted and pending admin approval. You will receive an email with the outcome."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/auth/signup/admin", tags=["Authentication Module"])
def signup_admin(admin: schemas.AdminCreate, db: Session = Depends(get_db)):
    if not admin.otp or not crud.verify_otp(email=admin.email, otp=admin.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired verification code. Please request a new code.")
    try:
        # Create pending admin signup notification for admin approval
        created = crud.request_admin_signup(db=db, admin=admin)
        return {"message": "Admin signup request submitted and pending approval. You will receive an email with the outcome."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/admin/admins", response_model=List[schemas.AdminResponse], tags=["Admin Module - Admin Management"])
def admin_get_all_admins(db: Session = Depends(get_db)):
    return crud.get_admins(db=db)

@app.get("/admin/admins/{admin_id}", response_model=schemas.AdminResponse, tags=["Admin Module - Admin Management"])
def admin_get_admin_by_id(admin_id: int, db: Session = Depends(get_db)):
    admin = crud.get_admin_by_id(db=db, admin_id=admin_id)
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    return admin

@app.post("/admin/admins", response_model=schemas.AdminResponse, status_code=status.HTTP_201_CREATED, tags=["Admin Module - Admin Management"])
def admin_create_admin(admin: schemas.AdminCreate, db: Session = Depends(get_db)):
    try:
        return crud.create_admin(db=db, admin=admin)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/admin/admins/{admin_id}", response_model=schemas.AdminResponse, tags=["Admin Module - Admin Management"])
def admin_update_admin(admin_id: int, admin_update: schemas.AdminUpdate, db: Session = Depends(get_db)):
    try:
        updated = crud.update_admin(db=db, admin_id=admin_id, admin_update=admin_update)
        if not updated:
            raise HTTPException(status_code=404, detail="Admin not found")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/admin/admins/{admin_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Admin Module - Admin Management"])
def admin_delete_admin(admin_id: int, db: Session = Depends(get_db), del_req: schemas.AdminDeleteRequest | None = None, current_password: str | None = None):
    try:
        pwd = (del_req.current_password if del_req else None) or current_password
        if not pwd:
            raise HTTPException(status_code=400, detail="current_password required (body or ?current_password=)")
        deleted = crud.delete_admin(db=db, admin_id=admin_id, current_password=pwd)
        if not deleted:
            raise HTTPException(status_code=404, detail="Admin not found")
        return None
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

@app.get("/admin/faculties", response_model=List[schemas.Faculty], tags=["Admin Module - Faculty Management"])
def admin_get_faculties(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_faculties(db=db, skip=skip, limit=limit)

@app.get("/admin/faculties/{faculty_id}", response_model=schemas.Faculty, tags=["Admin Module - Faculty Management"])
def admin_get_faculty_by_id(faculty_id: int, db: Session = Depends(get_db)):
    faculty = crud.get_faculty_by_id(db=db, faculty_id=faculty_id)
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
    return faculty

@app.post("/admin/faculties", response_model=schemas.Faculty, status_code=status.HTTP_201_CREATED, tags=["Admin Module - Faculty Management"])
def admin_create_faculty(faculty: schemas.FacultyCreate, db: Session = Depends(get_db)):
    try:
        return crud.create_faculty(db=db, faculty=faculty)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/admin/faculties/{faculty_id}", response_model=schemas.Faculty, tags=["Admin Module - Faculty Management"])
def admin_update_faculty(faculty_id: int, faculty: schemas.FacultyUpdate, db: Session = Depends(get_db)):
    try:
        updated = crud.update_faculty(db=db, faculty_id=faculty_id, faculty_update=faculty)
        if not updated:
            raise HTTPException(status_code=404, detail="Faculty not found")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/admin/faculties/{faculty_id}/request-edit", tags=["Admin Module - Faculty Management"])
def admin_request_faculty_edit(faculty_id: int, edit: schemas.AdminFacultyEditRequest, db: Session = Depends(get_db), x_user_id: str | None = Header(None, alias="X-User-Id")):
    try:
        try:
            _actor = int(x_user_id) if x_user_id is not None else None
        except (TypeError, ValueError):
            _actor = None
        return crud.request_faculty_edit_by_admin(db=db, faculty_id=faculty_id, edit=edit, actor_id=_actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/admin/faculties/{faculty_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Admin Module - Faculty Management"])
def admin_delete_faculty(faculty_id: int, db: Session = Depends(get_db)):
    deleted = crud.delete_faculty(db=db, faculty_id=faculty_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Faculty not found")
    return None

@app.get("/admin/students", tags=["Admin Module - Student Management"])
def admin_get_students(db: Session = Depends(get_db)):
    return crud.get_all_students(db=db)

@app.put("/admin/students/{student_id}/request-edit", tags=["Admin Module - Student Management"])
def admin_request_student_edit(student_id: int, edit: schemas.AdminStudentEditRequest, db: Session = Depends(get_db), x_user_id: str | None = Header(None, alias="X-User-Id")):
    try:
        try:
            _actor = int(x_user_id) if x_user_id is not None else None
        except (TypeError, ValueError):
            _actor = None
        return crud.request_student_edit_by_admin(db=db, student_id=student_id, edit=edit, actor_id=_actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/admin/projects/{project_id}/request-edit", tags=["Admin Module - Project Management"])
def admin_request_project_edit(project_id: int, edit: schemas.AdminProjectEditRequest, db: Session = Depends(get_db), x_user_id: str | None = Header(None, alias="X-User-Id")):
    # Phase-2: admin proposes project edits from anywhere a project is visible.
    # Nothing is applied directly — the owning faculty must Accept first.
    try:
        try:
            _actor = int(x_user_id) if x_user_id is not None else None
        except (TypeError, ValueError):
            _actor = None
        return crud.request_project_edit_by_admin(db=db, project_id=project_id, edit=edit, actor_id=_actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/admin/proposal-responses", tags=["Admin Module - Notifications"])
def admin_get_proposal_responses(admin_id: int, db: Session = Depends(get_db), x_user_id: str | None = Header(None, alias="X-User-Id"), x_user_role: str | None = Header(None, alias="X-User-Role")):
    # Phase-2: feedback notifications for the handling admin — which
    # faculty/student accepted or rejected the admin's proposals, in detail.
    try:
        role = (x_user_role or "").strip().lower()
        if role not in ("admin", "superadmin"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
        if role == "admin":
            try:
                if int(x_user_id) != int(admin_id):
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only view your own responses.")
            except (TypeError, ValueError):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-User-Id header.")
        return crud.get_admin_responses(db=db, admin_id=admin_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/admin/proposal-responses/{notification_id}/ack", tags=["Admin Module - Notifications"])
def admin_ack_proposal_response(notification_id: int, admin_id: int, db: Session = Depends(get_db), x_user_id: str | None = Header(None, alias="X-User-Id"), x_user_role: str | None = Header(None, alias="X-User-Role")):
    try:
        role = (x_user_role or "").strip().lower()
        if role not in ("admin", "superadmin"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
        if role == "admin":
            try:
                if int(x_user_id) != int(admin_id):
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only acknowledge your own responses.")
            except (TypeError, ValueError):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-User-Id header.")
        return crud.ack_admin_response(db=db, notification_id=notification_id, admin_id=admin_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/admin/notifications", response_model=List[schemas.NotificationResponse], tags=["Admin Module - Notifications"])
def admin_get_notifications(db: Session = Depends(get_db)):
    return crud.get_pending_notifications(db=db)

@app.post("/admin/notifications/{notification_id}", tags=["Admin Module - Notifications"])
def admin_handle_notification(notification_id: int, action_data: schemas.NotificationAction, db: Session = Depends(get_db), x_user_id: str | None = Header(None, alias="X-User-Id")):
    try:
        try:
            _actor = int(x_user_id) if x_user_id is not None else None
        except (TypeError, ValueError):
            _actor = None
        return crud.handle_notification(db=db, notification_id=notification_id, action=action_data.action, actor_id=_actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/admin/projects", response_model=List[schemas.ResearchProject], tags=["Admin Module - Project Management"])
def admin_get_all_projects(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_projects(db=db, skip=skip, limit=limit)

@app.get("/admin/projects/faculty/{faculty_id}", response_model=List[schemas.ResearchProject], tags=["Admin Module - Project Management"])
def admin_get_projects_by_faculty(faculty_id: int, db: Session = Depends(get_db)):
    return crud.get_projects_by_faculty(db=db, faculty_id=faculty_id)

@app.get("/admin/projects/{project_id}", response_model=schemas.ResearchProject, tags=["Admin Module - Project Management"])
def admin_get_project_by_id(project_id: int, db: Session = Depends(get_db)):
    proj = crud.get_project_by_id(db=db, project_id=project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj

@app.get("/admin/applications", response_model=List[schemas.ApplicationResponse], tags=["Admin Module - Application Management"])
def admin_get_all_applications(db: Session = Depends(get_db)):
    return crud.get_all_applications(db=db)

@app.get("/admin/applications/project/{project_id}", response_model=List[schemas.ApplicationResponse], tags=["Admin Module - Application Management"])
def admin_get_applications_by_project(project_id: int, db: Session = Depends(get_db)):
    return crud.get_applications_for_project(db=db, project_id=project_id)

@app.get("/admin/applications/faculty/{faculty_id}", response_model=List[schemas.ApplicationResponse], tags=["Admin Module - Application Management"])
def admin_get_applications_by_faculty(faculty_id: int, db: Session = Depends(get_db)):
    return crud.get_applications_for_faculty(db=db, faculty_id=faculty_id)

@app.get("/faculty/faculties", response_model=List[schemas.Faculty], tags=["Faculty Module - Faculty Management"])
def faculty_get_all_faculties(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_faculties(db=db, skip=skip, limit=limit)

@app.get("/faculty/faculties/{faculty_id}", response_model=schemas.Faculty, tags=["Faculty Module - Faculty Management"])
def faculty_get_faculty_by_id(faculty_id: int, db: Session = Depends(get_db)):
    faculty = crud.get_faculty_by_id(db=db, faculty_id=faculty_id)
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
    return faculty

@app.put("/faculty/faculties/{faculty_id}", response_model=schemas.Faculty, tags=["Faculty Module - Faculty Management"])
def faculty_update_own_profile(faculty_id: int, faculty_update: schemas.FacultyUpdate, db: Session = Depends(get_db)):
    try:
        updated = crud.update_faculty(db=db, faculty_id=faculty_id, faculty_update=faculty_update)
        if not updated:
            raise HTTPException(status_code=404, detail="Faculty not found")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/faculty/faculties/{faculty_id}/delete-request", tags=["Faculty Module - Faculty Management"])
def faculty_request_deletion(faculty_id: int, del_req: schemas.FacultyDeleteRequest, db: Session = Depends(get_db)):
    try:
        return crud.request_delete_faculty(db=db, faculty_id=faculty_id, current_password=del_req.current_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/faculty/students", tags=["Faculty Module - Student Management"])
def faculty_get_all_students(role: str | None = None, x_user_role: str | None = Header(None, alias="X-User-Role"), db: Session = Depends(get_db)):
    role_str = x_user_role if isinstance(x_user_role, str) else (role if isinstance(role, str) else "")
    user_role = role_str.strip().lower()
    if user_role == "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Students are not authorized to view the Student Directory.")
    return crud.get_all_students(db=db)

@app.get("/faculty/students/{student_id}/detail", tags=["Faculty Module - Student Management"])
def faculty_get_student_detail(student_id: int, role: str | None = None, x_user_role: str | None = Header(None, alias="X-User-Role"), db: Session = Depends(get_db)):
    role_str = x_user_role if isinstance(x_user_role, str) else (role if isinstance(role, str) else "")
    user_role = role_str.strip().lower()
    if user_role == "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Students are not authorized to view the Student Directory.")
    student = crud.get_student_by_id(db=db, student_id=student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    apps = crud.get_applications_for_student(db=db, student_id=student_id)
    student["applications"] = apps
    return student


@app.get("/faculty/projects", response_model=List[schemas.ResearchProject], tags=["Faculty Module - Project Management"])
def faculty_get_all_projects(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_projects(db=db, skip=skip, limit=limit)

@app.get("/faculty/projects/faculty/{faculty_id}", response_model=List[schemas.ResearchProject], tags=["Faculty Module - Project Management"])
def faculty_get_projects_by_faculty(faculty_id: int, db: Session = Depends(get_db)):
    return crud.get_projects_by_faculty(db=db, faculty_id=faculty_id)

@app.get("/faculty/projects/{project_id}", response_model=schemas.ResearchProject, tags=["Faculty Module - Project Management"])
def faculty_get_project_by_id(project_id: int, db: Session = Depends(get_db)):
    proj = crud.get_project_by_id(db=db, project_id=project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj

@app.post("/faculty/projects", tags=["Faculty Module - Project Management"])
def faculty_create_project(project: schemas.ResearchProjectCreate, db: Session = Depends(get_db)):
    try:
        return crud.request_project_creation(db=db, project=project)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/faculty/projects/{project_id}", response_model=schemas.ResearchProject, tags=["Faculty Module - Project Management"])
def faculty_update_project(project_id: int, project_update: schemas.ResearchProjectUpdate, faculty_id: int, db: Session = Depends(get_db)):
    try:
        updated = crud.update_project(db=db, project_id=project_id, project_update=project_update, faculty_id=faculty_id)
        if not updated:
            raise HTTPException(status_code=404, detail="Project not found")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

@app.delete("/faculty/projects/{project_id}", tags=["Faculty Module - Project Management"])
def faculty_delete_project(project_id: int, faculty_id: int, db: Session = Depends(get_db), del_req: schemas.ResearchProjectDelete | None = None, current_password: str | None = None):
    try:
        pwd = (del_req.current_password if del_req else None) or current_password
        if not pwd:
            raise HTTPException(status_code=400, detail="current_password required (body or ?current_password=)")
        result = crud.delete_project(db=db, project_id=project_id, faculty_id=faculty_id, current_password=pwd)
        if not result:
            raise HTTPException(status_code=404, detail="Project not found")
        return result
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

@app.get("/faculty/applications", response_model=List[schemas.ApplicationResponse], tags=["Faculty Module - Application Management"])
def faculty_get_all_applications(db: Session = Depends(get_db)):
    return crud.get_all_applications(db=db)

@app.get("/faculty/applications/project/{project_id}", response_model=List[schemas.ApplicationResponse], tags=["Faculty Module - Application Management"])
def faculty_get_applications_by_project(project_id: int, db: Session = Depends(get_db)):
    return crud.get_applications_for_project(db=db, project_id=project_id)

@app.get("/faculty/applications/faculty/{faculty_id}", response_model=List[schemas.ApplicationResponse], tags=["Faculty Module - Application Management"])
def faculty_get_applications_by_faculty(faculty_id: int, db: Session = Depends(get_db)):
    return crud.get_applications_for_faculty(db=db, faculty_id=faculty_id)

@app.put("/faculty/projects/{project_id}/applications/{application_id}/status", response_model=schemas.ApplicationResponse, tags=["Faculty Module - Application Management"])
def faculty_update_application_status(project_id: int, application_id: int, status_update: schemas.ApplicationStatusUpdate, db: Session = Depends(get_db)):
    try:
        updated_app = crud.update_application_status(db=db, project_id=project_id, application_id=application_id, status_update=status_update)
        if not updated_app:
            raise HTTPException(status_code=404, detail="Application not found")
        return updated_app
    except ValueError as ve:
        raise HTTPException(status_code=403, detail=str(ve))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/statistics/department-summary", tags=["Statistics Module"])
def read_department_summary(db: Session = Depends(get_db)):
    try:
        return crud.get_department_project_summary(db=db) or []
    except Exception as e:
        logger.exception('statistics error: %s', e)
        return []

@app.get("/statistics/popular-projects", tags=["Statistics Module"])
def read_popular_projects(db: Session = Depends(get_db)):
    try:
        return crud.get_projects_above_average_applications(db=db) or []
    except Exception as e:
        logger.exception('statistics error: %s', e)
        return []

@app.get("/statistics/active-projects", tags=["Statistics Module"])
def read_active_projects(db: Session = Depends(get_db)):
    try:
        return crud.get_active_projects_from_view(db=db) or []
    except Exception as e:
        logger.exception('statistics error: %s', e)
        return []

@app.get("/statistics/departments", tags=["Statistics Module"])
def read_all_departments(db: Session = Depends(get_db)):
    try:
        return crud.get_all_departments(db=db) or []
    except Exception as e:
        logger.exception('statistics error: %s', e)
        return []

@app.get("/statistics/department-summary/{department}", tags=["Statistics Module"])
def read_department_summary_detail(department: str, db: Session = Depends(get_db)):
    try:
        return crud.get_department_summary_detail(db=db, department=department) or {}
    except Exception as e:
        logger.exception('statistics error: %s', e)
        return {}

@app.get("/statistics/popular-projects/overall", tags=["Statistics Module"])
def read_popular_projects_overall(db: Session = Depends(get_db)):
    try:
        return crud.get_popular_projects_overall(db=db) or {}
    except Exception as e:
        logger.exception('statistics error: %s', e)
        return {}

@app.get("/statistics/popular-projects/{department}", tags=["Statistics Module"])
def read_popular_projects_by_dept(department: str, db: Session = Depends(get_db)):
    try:
        return crud.get_popular_projects_by_department(db=db, department=department) or {}
    except Exception as e:
        logger.exception('statistics error: %s', e)
        return {}

@app.get("/statistics/departments-above-average", tags=["Statistics Module"])
def read_departments_above_average(db: Session = Depends(get_db)):
    # DBMS-criteria showcase: COUNT + AVG with GROUP BY + HAVING (nested subquery).
    try:
        return crud.get_departments_above_average_projects(db=db) or {}
    except Exception as e:
        logger.exception('statistics error: %s', e)
        return {}

@app.get("/statistics/active-projects/{department}", tags=["Statistics Module"])
def read_active_projects_by_dept(department: str, db: Session = Depends(get_db)):
    try:
        result = crud.get_active_projects_by_department(db=db, department=department)
        return result if isinstance(result, list) else []
    except Exception as e:
        logger.exception('statistics error: %s', e)
        return []

@app.get("/faculty/notifications", response_model=List[schemas.NotificationResponse], tags=["Faculty Module - Notifications"])
def faculty_get_notifications_general(db: Session = Depends(get_db)):
    try:
        return crud.get_notifications(db=db) or []
    except Exception as e:
        logger.exception('statistics error: %s', e)
        return []

@app.get("/faculty/{faculty_id}/notifications", response_model=List[schemas.NotificationResponse], tags=["Faculty Module - Notifications"])
def faculty_get_notifications(faculty_id: int, db: Session = Depends(get_db)):
    try:
        return crud.get_faculty_notifications(db=db, faculty_id=faculty_id) or []
    except Exception as e:
        logger.exception('statistics error: %s', e)
        return []

@app.post("/faculty/{faculty_id}/notifications/{notification_id}/respond", tags=["Faculty Module - Notifications"])
def faculty_respond_to_notification(faculty_id: int, notification_id: int, action_data: schemas.NotificationAction, db: Session = Depends(get_db)):
    try:
        return crud.handle_faculty_notification_response(db=db, notification_id=notification_id, faculty_id=faculty_id, action=action_data.action)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/auth/signup/student", tags=["Authentication Module"])
def signup_student(student: schemas.StudentCreate, db: Session = Depends(get_db)):
    if not student.otp or not crud.verify_otp(email=student.email, otp=student.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired verification code. Please request a new code.")
    try:
        crud.request_student_signup(db=db, student=student)
        return {"message": "Signup request submitted and pending admin approval. You will receive an email with the outcome."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/student/students/{student_id}", tags=["Student Module - Profile"])
def student_get_profile(student_id: int, db: Session = Depends(get_db)):
    s = crud.get_student_by_id(db=db, student_id=student_id)
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    return s

@app.put("/student/students/{student_id}", tags=["Student Module - Profile"])
def student_update_profile(student_id: int, upd: schemas.StudentUpdate, db: Session = Depends(get_db)):
    try:
        r = crud.update_student(db=db, student_id=student_id, upd=upd)
        if not r:
            raise HTTPException(status_code=404, detail="Student not found")
        return r
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/student/students/{student_id}/delete-request", tags=["Student Module - Profile"])
def student_request_deletion(student_id: int, req: schemas.StudentDeleteRequest, db: Session = Depends(get_db)):
    try:
        return crud.request_delete_student(db=db, student_id=student_id, current_password=req.current_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/student/projects/{project_id}/apply", tags=["Student Module - Applications"])
def student_apply(project_id: int, req: schemas.ApplyRequest, db: Session = Depends(get_db)):
    try:
        return crud.apply_to_project(db=db, project_id=project_id, req=req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/student/{student_id}/applications", tags=["Student Module - Applications"])
def student_get_applications(student_id: int, db: Session = Depends(get_db)):
    try:
        return crud.get_applications_for_student(db=db, student_id=student_id) or []
    except Exception:
        return []

@app.delete("/student/applications/{project_id}/{application_id}", tags=["Student Module - Applications"])
def student_withdraw_application(project_id: int, application_id: int, student_id: int, db: Session = Depends(get_db)):
    try:
        return crud.withdraw_application(db=db, project_id=project_id, application_id=application_id, student_id=student_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/student/{student_id}/notifications", tags=["Student Module - Notifications"])
def student_get_notifications(student_id: int, db: Session = Depends(get_db)):
    try:
        return crud.get_student_notifications(db=db, student_id=student_id) or []
    except Exception:
        return []

@app.post("/student/{student_id}/notifications/{notification_id}/respond", tags=["Student Module - Notifications"])
def student_respond(student_id: int, notification_id: int, action_data: schemas.NotificationAction, db: Session = Depends(get_db)):
    try:
        return crud.handle_student_notification_response(db=db, notification_id=notification_id, student_id=student_id, action=action_data.action)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/student/{student_id}/notifications/{notification_id}/ack", tags=["Student Module - Notifications"])
def student_ack(student_id: int, notification_id: int, db: Session = Depends(get_db)):
    try:
        return crud.ack_student_notification(db=db, notification_id=notification_id, student_id=student_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/faculty/applications/{project_id}/{application_id}/detail", tags=["Faculty Module - Application Management"])
def faculty_get_application_detail(project_id: int, application_id: int, db: Session = Depends(get_db)):
    d = crud.get_application_full_for_faculty(db=db, project_id=project_id, application_id=application_id)
    if not d:
        raise HTTPException(status_code=404, detail="Application not found")
    return d

@app.post("/faculty/applications/{project_id}/{application_id}/decision", tags=["Faculty Module - Application Management"])
def faculty_decide_application(project_id: int, application_id: int, upd: schemas.ApplicationStatusUpdate, db: Session = Depends(get_db)):
    try:
        return crud.decide_application(db=db, project_id=project_id, application_id=application_id, status=upd.status, feedback=upd.feedback)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ================= SUPERADMIN MODULE =================
def _actor_id(x_user_id: str | None = Header(None, alias="X-User-Id")) -> int:
    try:
        return int(x_user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Missing X-User-Id header. Please log in again.")


@app.get("/superadmin/users", tags=["Superadmin Module"])
def superadmin_list_users(role: str, db: Session = Depends(get_db),
                          actor: int = Depends(_actor_id)):
    r = (role or "").strip().lower()
    try:
        if r == "admin":
            crud._sa_actor(db, actor)
            return crud.get_admins(db=db)
        if r == "faculty":
            crud._sa_actor(db, actor)
            return crud.get_faculties(db=db, skip=0, limit=1000)
        if r == "student":
            crud._sa_actor(db, actor)
            return crud.get_all_students(db=db)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    raise HTTPException(status_code=400, detail="role must be admin, faculty or student")


@app.put("/superadmin/faculties/{faculty_id}", tags=["Superadmin Module"])
def superadmin_edit_faculty(faculty_id: int, edit: schemas.SuperAdminFacultyEdit,
                            db: Session = Depends(get_db), actor: int = Depends(_actor_id)):
    try:
        return crud.superadmin_update_faculty(db=db, actor_id=actor, faculty_id=faculty_id, edit=edit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/superadmin/students/{student_id}", tags=["Superadmin Module"])
def superadmin_edit_student(student_id: int, edit: schemas.SuperAdminStudentEdit,
                            db: Session = Depends(get_db), actor: int = Depends(_actor_id)):
    try:
        return crud.superadmin_update_student(db=db, actor_id=actor, student_id=student_id, edit=edit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/superadmin/admins/{target_id}", tags=["Superadmin Module"])
def superadmin_edit_admin(target_id: int, edit: schemas.SuperAdminAdminEdit,
                          db: Session = Depends(get_db), actor: int = Depends(_actor_id)):
    try:
        return crud.superadmin_update_admin(db=db, actor_id=actor, target_id=target_id, edit=edit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/superadmin/me", tags=["Superadmin Module"])
def superadmin_edit_self(edit: schemas.AdminUpdate, db: Session = Depends(get_db),
                         actor: int = Depends(_actor_id)):
    try:
        return crud.superadmin_update_self(db=db, actor_id=actor, email=edit.email,
                                           current_password=edit.current_password,
                                           new_password=edit.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/superadmin/users/{target_id}", tags=["Superadmin Module"])
def superadmin_delete_user(target_id: int, current_password: str | None = None,
                           db: Session = Depends(get_db), actor: int = Depends(_actor_id)):
    try:
        return crud.superadmin_delete_user(db=db, actor_id=actor, target_id=target_id,
                                           current_password=current_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/superadmin/projects", tags=["Superadmin Module"])
def superadmin_list_projects(db: Session = Depends(get_db), actor: int = Depends(_actor_id)):
    try:
        crud._sa_actor(db, actor)
        return crud.get_projects(db=db, skip=0, limit=1000)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@app.post("/superadmin/projects", tags=["Superadmin Module"])
def superadmin_create_project(proj: schemas.SuperAdminProjectCreate,
                              db: Session = Depends(get_db), actor: int = Depends(_actor_id)):
    try:
        return crud.superadmin_create_project(db=db, actor_id=actor, title=proj.title,
                                              description=proj.description,
                                              required_skill=proj.required_skill,
                                              status=proj.status, faculty_id=proj.faculty_id,
                                              current_password=proj.current_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/superadmin/projects/{project_id}", tags=["Superadmin Module"])
def superadmin_update_project(project_id: int, edit: schemas.SuperAdminProjectUpdate,
                              db: Session = Depends(get_db), actor: int = Depends(_actor_id)):
    try:
        return crud.superadmin_update_project(db=db, actor_id=actor, project_id=project_id, edit=edit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/superadmin/projects/{project_id}", tags=["Superadmin Module"])
def superadmin_delete_project(project_id: int, current_password: str | None = None,
                              db: Session = Depends(get_db), actor: int = Depends(_actor_id)):
    try:
        return crud.superadmin_delete_project(db=db, actor_id=actor, project_id=project_id,
                                              current_password=current_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/superadmin/audit", tags=["Superadmin Module"])
def superadmin_audit(limit: int = 100, db: Session = Depends(get_db),
                     actor: int = Depends(_actor_id)):
    try:
        return crud.get_audit_log(db=db, actor_id=actor, limit=min(limit, 500))
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@app.get("/superadmin/admin-activities", tags=["Superadmin Module"])
def superadmin_admin_activities(limit: int = 200, db: Session = Depends(get_db),
                                actor: int = Depends(_actor_id)):
    try:
        return crud.get_admin_activity_log(db=db, actor_id=actor, limit=min(limit, 500))
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@app.get("/superadmin/chat/threads", tags=["Superadmin Channel"])
def superadmin_chat_threads(db: Session = Depends(get_db), actor: int = Depends(_actor_id)):
    try:
        crud._sa_actor(db, actor)
        return crud.chat_unread_for_superadmin(db=db)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@app.get("/superadmin/chat/{admin_id}", tags=["Superadmin Channel"])
def superadmin_chat_thread(admin_id: int, db: Session = Depends(get_db),
                           actor: int = Depends(_actor_id)):
    try:
        crud._sa_actor(db, actor)
        return crud.chat_thread(db=db, admin_id=admin_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@app.post("/superadmin/chat/{admin_id}", tags=["Superadmin Channel"])
def superadmin_chat_send(admin_id: int, msg: schemas.ChatSend, db: Session = Depends(get_db),
                         actor: int = Depends(_actor_id)):
    try:
        crud._sa_actor(db, actor)
        return crud.chat_send(db=db, admin_id=admin_id, sender="superadmin", message=msg.message)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/superadmin/chat/{admin_id}/read", tags=["Superadmin Channel"])
def superadmin_chat_read(admin_id: int, body: schemas.ChatRead, db: Session = Depends(get_db),
                         actor: int = Depends(_actor_id)):
    try:
        crud._sa_actor(db, actor)
        return crud.chat_mark_read(db=db, admin_id=admin_id, reader="superadmin",
                                   message_ids=body.message_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/admin/chat/thread", tags=["Superadmin Channel"])
def admin_chat_thread(db: Session = Depends(get_db), actor: int = Depends(_actor_id)):
    try:
        me = db.execute(text("SELECT user_id, role FROM user WHERE user_id = :u"),
                        {"u": actor}).fetchone()
        if not me or str(me.role).strip().lower() != "admin":
            raise HTTPException(status_code=403, detail="Admin access required.")
        return crud.chat_thread(db=db, admin_id=actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/admin/chat/unread", tags=["Superadmin Channel"])
def admin_chat_unread(db: Session = Depends(get_db), actor: int = Depends(_actor_id)):
    me = db.execute(text("SELECT user_id, role FROM user WHERE user_id = :u"),
                    {"u": actor}).fetchone()
    if not me or str(me.role).strip().lower() != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return crud.chat_unread_for_admin(db=db, admin_id=actor)


@app.post("/admin/chat/send", tags=["Superadmin Channel"])
def admin_chat_send(msg: schemas.ChatSend, db: Session = Depends(get_db),
                    actor: int = Depends(_actor_id)):
    try:
        me = db.execute(text("SELECT user_id, role FROM user WHERE user_id = :u"),
                        {"u": actor}).fetchone()
        if not me or str(me.role).strip().lower() != "admin":
            raise HTTPException(status_code=403, detail="Admin access required.")
        return crud.chat_send(db=db, admin_id=actor, sender="admin", message=msg.message)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/admin/chat/read", tags=["Superadmin Channel"])
def admin_chat_read(body: schemas.ChatRead, db: Session = Depends(get_db),
                    actor: int = Depends(_actor_id)):
    try:
        me = db.execute(text("SELECT user_id, role FROM user WHERE user_id = :u"),
                        {"u": actor}).fetchone()
        if not me or str(me.role).strip().lower() != "admin":
            raise HTTPException(status_code=403, detail="Admin access required.")
        return crud.chat_mark_read(db=db, admin_id=actor, reader="admin",
                                   message_ids=body.message_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
