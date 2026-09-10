from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class Faculty(Base):
    __tablename__ = "faculty"

    faculty_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    designation = Column(String(100), nullable=False)
    department = Column(String(100), nullable=False)
    office_hours = Column(String(255), nullable=True)

    research_areas = relationship("FacultyResearchArea", back_populates="faculty", cascade="all, delete-orphan")
    projects = relationship("ResearchProject", back_populates="faculty", cascade="all, delete-orphan")


class FacultyResearchArea(Base):
    __tablename__ = "faculty_research_areas"

    faculty_id = Column(Integer, ForeignKey("faculty.faculty_id", ondelete="CASCADE"), primary_key=True)
    research_area = Column(String(255), primary_key=True)

    faculty = relationship("Faculty", back_populates="research_areas")


class ResearchProject(Base):
    __tablename__ = "research_project"

    project_id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    required_skill = Column(Text, nullable=True)
    status = Column(String(50), default="Open")
    created_at = Column(DateTime, default=datetime.utcnow)
    applicant_count = Column(Integer, default=0)
    faculty_id = Column(Integer, ForeignKey("faculty.faculty_id", ondelete="CASCADE"))

    faculty = relationship("Faculty", back_populates="projects")
    applications = relationship("Application", back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_project_title_status", "title", "status"),
    )


class Application(Base):
    __tablename__ = "application"

    application_id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("research_project.project_id", ondelete="CASCADE"))
    status = Column(String(50), default="Pending")
    applied_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("ResearchProject", back_populates="applications")


class ActiveProjectsView(Base):
    __tablename__ = "active_projects_view"

    project_id = Column(Integer, primary_key=True)
    title = Column(String(255))
    status = Column(String(50))
