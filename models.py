from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from database import Base

class User(Base):
    __tablename__ = "user"

    user_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="Student")

class Faculty(Base):
    __tablename__ = "faculty"

    faculty_id = Column(Integer, ForeignKey("user.user_id", ondelete="CASCADE"), primary_key=True)
    name = Column(String(255), nullable=False)
    designation = Column(String(255), nullable=False)
    department = Column(String(255), nullable=False)
    office_hours = Column(String(255), nullable=True)

class FacultyResearchArea(Base):
    __tablename__ = "faculty_research_areas"

    faculty_id = Column(Integer, ForeignKey("faculty.faculty_id", ondelete="CASCADE"), primary_key=True)
    research_area = Column(String(150), primary_key=True)

class ResearchProject(Base):
    __tablename__ = "research_project"

    project_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    faculty_id = Column(Integer, ForeignKey("faculty.faculty_id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    required_skill = Column(Text, nullable=True)
    status = Column(String(50), default="Active")
    applicant_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

class Student(Base):
    __tablename__ = "student"

    student_id = Column(Integer, ForeignKey("user.user_id", ondelete="CASCADE"), primary_key=True)
    name = Column(String(255), nullable=False)
    cgpa = Column(String(10), nullable=True)
    department = Column(String(255), nullable=True)
    semester = Column(String(50), nullable=True)
    github_link = Column(String(255), nullable=True)
    cv_link = Column(String(255), nullable=True)

class StudentSkill(Base):
    __tablename__ = "student_skills"

    student_id = Column(Integer, ForeignKey("student.student_id", ondelete="CASCADE"), primary_key=True)
    skill = Column(String(100), primary_key=True)

class StudentInterest(Base):
    __tablename__ = "student_interests"

    student_id = Column(Integer, ForeignKey("student.student_id", ondelete="CASCADE"), primary_key=True)
    research_area = Column(String(150), primary_key=True)

class Application(Base):
    __tablename__ = "application"

    project_id = Column(Integer, ForeignKey("research_project.project_id", ondelete="CASCADE"), primary_key=True, nullable=False)
    application_id = Column(Integer, primary_key=True, nullable=False)
    student_id = Column(Integer, nullable=False)
    cover_letter = Column(Text, nullable=True)
    status = Column(String(50), default="Pending")
    applied_at = Column(DateTime, server_default=func.now())
    applicant_name = Column(String(255), nullable=True)
    applicant_cgpa = Column(String(10), nullable=True)
    applicant_department = Column(String(255), nullable=True)
    applicant_semester = Column(String(50), nullable=True)
    applicant_github = Column(String(255), nullable=True)
    applicant_cv = Column(String(255), nullable=True)
    applicant_skills = Column(Text, nullable=True)
    applicant_interests = Column(Text, nullable=True)
    motivation = Column(Text, nullable=True)
    feedback = Column(Text, nullable=True)

class Notification(Base):
    __tablename__ = "notification"

    notification_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    faculty_id = Column(Integer, ForeignKey("faculty.faculty_id", ondelete="CASCADE"), nullable=True)
    student_id = Column(Integer, ForeignKey("student.student_id", ondelete="CASCADE"), nullable=True)
    type = Column(String(100), nullable=False)
    payload = Column(Text, nullable=False)
    status = Column(String(50), default="Pending")
    created_at = Column(DateTime, server_default=func.now())