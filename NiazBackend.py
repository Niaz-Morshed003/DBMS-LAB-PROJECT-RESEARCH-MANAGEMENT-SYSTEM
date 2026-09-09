from typing import List
from fastapi import FastAPI, HTTPException, status, Depends
from sqlalchemy.orm import Session

import models, schemas, crud
from database import engine, get_db

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Research Management Portal",
    description="Backend API meeting all 7 DBMS Lab Benchmarks",
    version="1.0.0"
)

@app.get("/faculties/", response_model=List[schemas.Faculty], tags=["Faculty Management"])
def read_faculties(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_faculties(db=db, skip=skip, limit=limit)

@app.get("/faculties/{faculty_id}", response_model=schemas.Faculty, tags=["Faculty Management"])
def read_faculty(faculty_id: int, db: Session = Depends(get_db)):
    db_faculty = crud.get_faculty_by_id(db=db, faculty_id=faculty_id)
    if db_faculty is None:
        raise HTTPException(status_code=404, detail="Faculty not found")
    return db_faculty

@app.post("/faculties/", response_model=schemas.Faculty, status_code=status.HTTP_201_CREATED, tags=["Faculty Management"])
def create_faculty(faculty: schemas.FacultyCreate, db: Session = Depends(get_db)):
    return crud.create_faculty(db=db, faculty=faculty)

@app.put("/faculties/{faculty_id}", response_model=schemas.Faculty, tags=["Faculty Management"])
def update_faculty(faculty_id: int, faculty: schemas.FacultyUpdate, db: Session = Depends(get_db)):
    updated_faculty = crud.update_faculty(db=db, faculty_id=faculty_id, faculty_update=faculty)
    if updated_faculty is None:
        raise HTTPException(status_code=404, detail="Faculty not found")
    return updated_faculty

@app.delete("/faculties/{faculty_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Faculty Management"])
def delete_faculty(faculty_id: int, db: Session = Depends(get_db)):
    deleted_faculty = crud.delete_faculty(db=db, faculty_id=faculty_id)
    if deleted_faculty is None:
        raise HTTPException(status_code=404, detail="Faculty not found")
    return None

@app.post("/projects/", response_model=schemas.ResearchProject, status_code=status.HTTP_201_CREATED, tags=["Project Management"])
def create_project(project: schemas.ResearchProjectCreate, db: Session = Depends(get_db)):
    return crud.create_project(db=db, project=project)

@app.get("/projects/", response_model=List[schemas.ResearchProject], tags=["Project Management"])
def read_all_projects(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_projects(db=db, skip=skip, limit=limit)

@app.get("/faculties/{faculty_id}/projects", response_model=List[schemas.ResearchProject], tags=["Project Management"])
def read_projects_by_faculty(faculty_id: int, db: Session = Depends(get_db)):
    return crud.get_projects_by_faculty(db=db, faculty_id=faculty_id)

@app.put("/projects/{project_id}", response_model=schemas.ResearchProject, tags=["Project Management"])
def update_project(project_id: int, project_update: schemas.ResearchProjectUpdate, db: Session = Depends(get_db)):
    updated_proj = crud.update_project(db=db, project_id=project_id, project_update=project_update)
    if not updated_proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated_proj

@app.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Project Management"])
def delete_project(project_id: int, db: Session = Depends(get_db)):
    deleted_proj = crud.delete_project(db=db, project_id=project_id)
    if not deleted_proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return None

@app.get("/faculties/{faculty_id}/applications", response_model=List[schemas.ApplicationResponse], tags=["Application Management"])
def read_faculty_applications(faculty_id: int, db: Session = Depends(get_db)):
    return crud.get_applications_for_faculty(db=db, faculty_id=faculty_id)

@app.put("/applications/{application_id}/status", response_model=schemas.ApplicationResponse, tags=["Application Management"])
def update_application_status(application_id: int, status_update: schemas.ApplicationStatusUpdate, db: Session = Depends(get_db)):
    updated_app = crud.update_application_status(db=db, application_id=application_id, status_update=status_update)
    if not updated_app:
        raise HTTPException(status_code=404, detail="Application not found")
    return updated_app

@app.get("/analytics/department-summary", response_model=List[schemas.DepartmentSummary], tags=["DBMS Lab Benchmarks"])
def read_department_summary(db: Session = Depends(get_db)):
    return crud.get_department_project_summary(db=db)

@app.get("/analytics/above-average-projects", response_model=List[schemas.ResearchProject], tags=["DBMS Lab Benchmarks"])
def read_above_average_projects(db: Session = Depends(get_db)):
    return crud.get_projects_above_average_applications(db=db)

@app.get("/views/active-projects", response_model=List[schemas.ActiveProjectViewResponse], tags=["DBMS Lab Benchmarks"])
def read_active_projects_view(db: Session = Depends(get_db)):
    return crud.get_active_projects_from_view(db=db)