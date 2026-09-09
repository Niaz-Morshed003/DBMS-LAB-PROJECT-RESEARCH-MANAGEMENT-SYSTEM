from sqlalchemy.orm import Session
from sqlalchemy import func
import models, schemas

def get_faculties(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Faculty).offset(skip).limit(limit).all()

def get_faculty_by_id(db: Session, faculty_id: int):
    return db.query(models.Faculty).filter(models.Faculty.faculty_id == faculty_id).first()

def create_faculty(db: Session, faculty: schemas.FacultyCreate):
    try:
        db_faculty = models.Faculty(
            name=faculty.name,
            designation=faculty.designation,
            department=faculty.department,
            office_hours=faculty.office_hours
        )
        db.add(db_faculty)
        db.flush()

        if faculty.research_areas:
            for area in faculty.research_areas:
                db_area = models.FacultyResearchArea(
                    faculty_id=db_faculty.faculty_id,
                    research_area=area
                )
                db.add(db_area)
        
        db.commit()
        db.refresh(db_faculty)
        return db_faculty
    except Exception as e:
        db.rollback()
        raise e

def update_faculty(db: Session, faculty_id: int, faculty_update: schemas.FacultyUpdate):
    db_faculty = get_faculty_by_id(db, faculty_id)
    if not db_faculty:
        return None

    update_data = faculty_update.model_dump(exclude_unset=True)
    
    if "research_areas" in update_data:
        research_areas_data = update_data.pop("research_areas")
        db.query(models.FacultyResearchArea).filter(
            models.FacultyResearchArea.faculty_id == faculty_id
        ).delete()
        
        if research_areas_data:
            for area in research_areas_data:
                db_area = models.FacultyResearchArea(
                    faculty_id=faculty_id,
                    research_area=area
                )
                db.add(db_area)

    for key, value in update_data.items():
        setattr(db_faculty, key, value)

    db.commit()
    db.refresh(db_faculty)
    return db_faculty

def delete_faculty(db: Session, faculty_id: int):
    db_faculty = get_faculty_by_id(db, faculty_id)
    if not db_faculty:
        return None
    
    db.delete(db_faculty)
    db.commit()
    return db_faculty

def create_project(db: Session, project: schemas.ResearchProjectCreate):
    db_project = models.ResearchProject(**project.model_dump())
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

def get_projects(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.ResearchProject).offset(skip).limit(limit).all()

def get_projects_by_faculty(db: Session, faculty_id: int):
    return db.query(models.ResearchProject).filter(models.ResearchProject.faculty_id == faculty_id).all()

def get_project_by_id(db: Session, project_id: int):
    return db.query(models.ResearchProject).filter(models.ResearchProject.project_id == project_id).first()

def update_project(db: Session, project_id: int, project_update: schemas.ResearchProjectUpdate):
    db_project = get_project_by_id(db, project_id)
    if not db_project:
        return None
    
    update_data = project_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_project, key, value)
        
    db.commit()
    db.refresh(db_project)
    return db_project

def delete_project(db: Session, project_id: int):
    db_project = get_project_by_id(db, project_id)
    if not db_project:
        return None
    db.delete(db_project)
    db.commit()
    return db_project

def get_applications_for_faculty(db: Session, faculty_id: int):
    return (
        db.query(models.Application)
        .join(models.ResearchProject, models.Application.project_id == models.ResearchProject.project_id)
        .filter(models.ResearchProject.faculty_id == faculty_id)
        .all()
    )

def get_department_project_summary(db: Session):
    return (
        db.query(
            models.Faculty.department,
            func.count(func.distinct(models.Faculty.faculty_id)).label("faculty_count"),
            func.count(models.ResearchProject.project_id).label("total_projects")
        )
        .outerjoin(models.ResearchProject, models.Faculty.faculty_id == models.ResearchProject.faculty_id)
        .group_by(models.Faculty.department)
        .having(func.count(models.Faculty.faculty_id) > 0)
        .all()
    )

def get_projects_above_average_applications(db: Session):
    avg_subquery = db.query(func.avg(models.ResearchProject.applicant_count)).scalar_subquery()
    return db.query(models.ResearchProject).filter(models.ResearchProject.applicant_count > avg_subquery).all()

def get_active_projects_from_view(db: Session):
    return db.query(models.ActiveProjectsView).all()

def update_application_status(db: Session, application_id: int, status_update: schemas.ApplicationStatusUpdate):
    db_app = db.query(models.Application).filter(models.Application.application_id == application_id).first()
    if not db_app:
        return None
    db_app.status = status_update.status
    db.commit()
    db.refresh(db_app)
    return db_app