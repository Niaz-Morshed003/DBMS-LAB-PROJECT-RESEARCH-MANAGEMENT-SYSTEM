from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

class FacultyResearchAreaSchema(BaseModel):
    faculty_id: int
    research_area: str

    class Config:
        from_attributes = True

class FacultyBase(BaseModel):
    name: str
    designation: str
    department: str
    office_hours: Optional[str] = None

class FacultyCreate(FacultyBase):
    research_areas: Optional[List[str]] = []

class FacultyUpdate(BaseModel):
    name: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    office_hours: Optional[str] = None
    research_areas: Optional[List[str]] = None

class Faculty(FacultyBase):
    faculty_id: int
    research_areas: List[FacultyResearchAreaSchema] = []

    class Config:
        from_attributes = True


class ResearchProjectBase(BaseModel):
    title: str
    description: Optional[str] = None
    required_skill: Optional[str] = None
    status: Optional[str] = "Open"

class ResearchProjectCreate(ResearchProjectBase):
    faculty_id: int

class ResearchProjectUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    required_skill: Optional[str] = None
    status: Optional[str] = None

class ResearchProject(ResearchProjectBase):
    project_id: int
    faculty_id: int
    applicant_count: Optional[int] = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ApplicationResponse(BaseModel):
    application_id: int
    student_id: int
    project_id: int
    status: str
    applied_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ApplicationStatusUpdate(BaseModel):
    status: str

class DepartmentSummary(BaseModel):
    department: str
    faculty_count: int
    total_projects: int

class ActiveProjectViewResponse(BaseModel):
    project_id: int
    title: str
    status: str

    class Config:
        from_attributes = True