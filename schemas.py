from pydantic import BaseModel, EmailStr
from typing import Optional, List

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    user_id: int
    email: EmailStr
    role: str
    message: str

class SendOTPRequest(BaseModel):
    email: EmailStr

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str

class StudentUniqueCheck(BaseModel):
    email: Optional[EmailStr] = None
    github_link: Optional[str] = None
    cv_link: Optional[str] = None
    exclude_id: Optional[int] = None

class AdminCreate(BaseModel):
    email: EmailStr
    password: str
    otp: Optional[str] = None

class AdminUpdate(BaseModel):
    email: Optional[EmailStr] = None
    current_password: str
    new_password: Optional[str] = None

class AdminDeleteRequest(BaseModel):
    current_password: str

class AdminResponse(BaseModel):
    admin_id: int
    email: EmailStr
    role: str

    class Config:
        from_attributes = True

class ResearchArea(BaseModel):
    faculty_id: int
    research_area: str

    class Config:
        from_attributes = True

class Faculty(BaseModel):
    faculty_id: int
    name: str
    designation: str
    department: str
    office_hours: Optional[str] = None
    email: EmailStr
    research_areas: Optional[List[ResearchArea]] = []

    class Config:
        from_attributes = True

class FacultyCreate(BaseModel):
    name: str
    email: EmailStr
    designation: str
    department: str
    office_hours: Optional[str] = None
    password: str
    research_areas: Optional[List[str]] = []
    otp: Optional[str] = None

class FacultyUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    office_hours: Optional[str] = None
    current_password: str
    new_password: Optional[str] = None
    research_areas: Optional[List[str]] = None

class FacultyDeleteRequest(BaseModel):
    current_password: str

class AdminFacultyEditRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    office_hours: Optional[str] = None
    research_areas: Optional[List[str]] = None

class AdminStudentEditRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    cgpa: Optional[str] = None
    department: Optional[str] = None
    semester: Optional[str] = None
    github_link: Optional[str] = None
    cv_link: Optional[str] = None
    skills: Optional[List[str]] = None
    interests: Optional[List[str]] = None

class AdminProjectEditRequest(BaseModel):
    """Admin proposes research-project edits. Nothing is applied directly —
    the owning faculty must Accept first (mirrors AdminFacultyEditRequest)."""
    title: Optional[str] = None
    description: Optional[str] = None
    required_skill: Optional[str] = None
    status: Optional[str] = None

class ResearchProjectCreate(BaseModel):
    title: str
    description: Optional[str] = None
    required_skill: Optional[str] = None
    status: Optional[str] = "Active"
    faculty_id: int
    current_password: str

class ResearchProjectUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    required_skill: Optional[str] = None
    status: Optional[str] = None
    current_password: str

class ResearchProjectDelete(BaseModel):
    current_password: str

class ResearchProjectResponse(BaseModel):
    project_id: int
    faculty_id: int
    title: str
    description: Optional[str] = None
    required_skill: Optional[str] = None
    status: str
    faculty_name: Optional[str] = None
    department: Optional[str] = None

    class Config:
        from_attributes = True

ResearchProject = ResearchProjectResponse

class ApplicationResponse(BaseModel):
    project_id: int
    application_id: int
    student_id: int
    cover_letter: Optional[str] = None
    status: str
    project_title: Optional[str] = None
    faculty_name: Optional[str] = None
    department: Optional[str] = None
    applicant_name: Optional[str] = None
    applicant_cgpa: Optional[str] = None
    applicant_department: Optional[str] = None
    applicant_semester: Optional[str] = None
    applicant_github: Optional[str] = None
    applicant_cv: Optional[str] = None
    applicant_skills: Optional[List[str]] = None
    applicant_interests: Optional[List[str]] = None
    motivation: Optional[str] = None
    feedback: Optional[str] = None

    class Config:
        from_attributes = True

class StudentResponse(BaseModel):
    student_id: int
    name: str
    cgpa: Optional[str] = None
    department: Optional[str] = None
    semester: Optional[str] = None
    github_link: Optional[str] = None
    cv_link: Optional[str] = None
    email: Optional[EmailStr] = None
    skills: Optional[List[str]] = []
    interests: Optional[List[str]] = []

    class Config:
        from_attributes = True

class StudentCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    cgpa: Optional[str] = None
    department: Optional[str] = None
    semester: Optional[str] = None
    github_link: Optional[str] = None
    cv_link: Optional[str] = None
    skills: Optional[List[str]] = []
    interests: Optional[List[str]] = []
    otp: Optional[str] = None

class StudentUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    cgpa: Optional[str] = None
    department: Optional[str] = None
    semester: Optional[str] = None
    github_link: Optional[str] = None
    cv_link: Optional[str] = None
    current_password: str
    new_password: Optional[str] = None
    skills: Optional[List[str]] = None
    interests: Optional[List[str]] = None

class StudentDeleteRequest(BaseModel):
    current_password: str

class ApplyRequest(BaseModel):
    student_id: int
    current_password: str
    name: Optional[str] = None
    cgpa: Optional[str] = None
    department: Optional[str] = None
    semester: Optional[str] = None
    github_link: Optional[str] = None
    cv_link: Optional[str] = None
    skills: Optional[List[str]] = []
    interests: Optional[List[str]] = []
    motivation: Optional[str] = None
    cover_letter: Optional[str] = None

class ApplicationStatusUpdate(BaseModel):
    status: str
    feedback: Optional[str] = None

class NotificationResponse(BaseModel):
    notification_id: int
    faculty_id: Optional[int] = None
    type: str
    payload: str
    status: str
    faculty_name: Optional[str] = None

    class Config:
        from_attributes = True

class NotificationAction(BaseModel):
    action: str

class SuperAdminFacultyEdit(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    office_hours: Optional[str] = None
    research_areas: Optional[List[str]] = None
    current_password: Optional[str] = None

class SuperAdminStudentEdit(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    cgpa: Optional[str] = None
    department: Optional[str] = None
    semester: Optional[str] = None
    github_link: Optional[str] = None
    cv_link: Optional[str] = None
    skills: Optional[List[str]] = None
    interests: Optional[List[str]] = None
    current_password: Optional[str] = None

class SuperAdminAdminEdit(BaseModel):
    email: Optional[EmailStr] = None
    current_password: Optional[str] = None

class SuperAdminProjectCreate(BaseModel):
    title: str
    description: Optional[str] = None
    required_skill: Optional[str] = None
    status: Optional[str] = "Active"
    faculty_id: int
    current_password: Optional[str] = None

class SuperAdminProjectUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    required_skill: Optional[str] = None
    status: Optional[str] = None
    faculty_id: Optional[int] = None
    current_password: Optional[str] = None

class ChatSend(BaseModel):
    message: str

class ChatRead(BaseModel):
    message_ids: Optional[List[int]] = None