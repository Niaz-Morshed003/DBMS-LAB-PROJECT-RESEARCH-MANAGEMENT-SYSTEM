import uuid
from sqlalchemy.orm import Session
from sqlalchemy import text
import schemas

def get_faculties(db: Session, skip: int = 0, limit: int = 100):
    query = text("""
        SELECT faculty_id, name, designation, department, office_hours
        FROM faculty
        LIMIT :limit OFFSET :skip;
    """)
    results = db.execute(query, {"limit": limit, "skip": skip}).mappings().all()
    
    faculties = []
    for row in results:
        faculty_id = row["faculty_id"]
        area_query = text("""
            SELECT research_area 
            FROM faculty_research_areas 
            WHERE faculty_id = :faculty_id;
        """)
        areas = db.execute(area_query, {"faculty_id": faculty_id}).scalars().all()
        
        faculty_data = dict(row)
        faculty_data["research_areas"] = [{"faculty_id": faculty_id, "research_area": area} for area in areas]
        faculties.append(faculty_data)
        
    return faculties

def get_faculty_by_id(db: Session, faculty_id: int):
    query = text("""
        SELECT faculty_id, name, designation, department, office_hours
        FROM faculty
        WHERE faculty_id = :faculty_id;
    """)
    faculty = db.execute(query, {"faculty_id": faculty_id}).mappings().first()
    if not faculty:
        return None
    
    area_query = text("""
        SELECT research_area 
        FROM faculty_research_areas 
        WHERE faculty_id = :faculty_id;
    """)
    areas = db.execute(area_query, {"faculty_id": faculty_id}).scalars().all()
    
    result = dict(faculty)
    result["research_areas"] = [{"faculty_id": faculty_id, "research_area": area} for area in areas]
    return result

def create_faculty(db: Session, faculty: schemas.FacultyCreate):
    try:
        dummy_email = f"faculty_{uuid.uuid4().hex[:8]}@university.edu"
        
        insert_user_query = text("INSERT INTO `user` (email, role) VALUES (:email, 'faculty');")
        db.execute(insert_user_query, {"email": dummy_email})
        
        user_id_query = text("SELECT LAST_INSERT_ID();")
        user_id = db.execute(user_id_query).scalar()

        if not user_id:
            raise Exception("Failed to retrieve generated user_id.")

        insert_faculty_query = text("""
            INSERT INTO faculty (faculty_id, name, designation, department, office_hours)
            VALUES (:faculty_id, :name, :designation, :department, :office_hours);
        """)
        db.execute(insert_faculty_query, {
            "faculty_id": user_id,
            "name": faculty.name,
            "designation": faculty.designation,
            "department": faculty.department,
            "office_hours": faculty.office_hours
        })

        if faculty.research_areas:
            insert_area_query = text("""
                INSERT INTO faculty_research_areas (faculty_id, research_area)
                VALUES (:faculty_id, :research_area);
            """)
            for area in faculty.research_areas:
                db.execute(insert_area_query, {
                    "faculty_id": user_id,
                    "research_area": area
                })
        
        db.commit()
        return get_faculty_by_id(db, user_id)
    except Exception as e:
        db.rollback()
        raise e

def update_faculty(db: Session, faculty_id: int, faculty_update: schemas.FacultyUpdate):
    db_faculty = get_faculty_by_id(db, faculty_id)
    if not db_faculty:
        return None

    update_data = faculty_update.model_dump(exclude_unset=True)
    
    try:
        if "research_areas" in update_data:
            research_areas_data = update_data.pop("research_areas")
            
            delete_areas_query = text("""
                DELETE FROM faculty_research_areas 
                WHERE faculty_id = :faculty_id;
            """)
            db.execute(delete_areas_query, {"faculty_id": faculty_id})
            
            if research_areas_data:
                insert_area_query = text("""
                    INSERT INTO faculty_research_areas (faculty_id, research_area)
                    VALUES (:faculty_id, :research_area);
                """)
                for area in research_areas_data:
                    db.execute(insert_area_query, {
                        "faculty_id": faculty_id,
                        "research_area": area
                    })

        if update_data:
            set_clauses = [f"{key} = :{key}" for key in update_data.keys()]
            update_query_str = f"UPDATE faculty SET {', '.join(set_clauses)} WHERE faculty_id = :faculty_id;"
            update_data["faculty_id"] = faculty_id
            db.execute(text(update_query_str), update_data)

        db.commit()
        return get_faculty_by_id(db, faculty_id)
    except Exception as e:
        db.rollback()
        raise e

def delete_faculty(db: Session, faculty_id: int):
    db_faculty = get_faculty_by_id(db, faculty_id)
    if not db_faculty:
        return None
    
    query = text("DELETE FROM faculty WHERE faculty_id = :faculty_id;")
    db.execute(query, {"faculty_id": faculty_id})
    db.commit()
    return db_faculty

def create_project(db: Session, project: schemas.ResearchProjectCreate):
    query = text("""
        INSERT INTO research_project (title, description, required_skill, status, faculty_id)
        VALUES (:title, :description, :required_skill, :status, :faculty_id);
    """)
    db.execute(query, project.model_dump())
    db.commit()
    
    project_id = db.execute(text("SELECT LAST_INSERT_ID();")).scalar()
    return get_project_by_id(db, project_id)

def get_projects(db: Session, skip: int = 0, limit: int = 100):
    query = text("SELECT * FROM research_project LIMIT :limit OFFSET :skip;")
    result = db.execute(query, {"limit": limit, "skip": skip})
    return result.mappings().all()

def get_projects_by_faculty(db: Session, faculty_id: int):
    query = text("SELECT * FROM research_project WHERE faculty_id = :faculty_id;")
    result = db.execute(query, {"faculty_id": faculty_id})
    return result.mappings().all()

def get_project_by_id(db: Session, project_id: int):
    query = text("SELECT * FROM research_project WHERE project_id = :project_id;")
    result = db.execute(query, {"project_id": project_id})
    return result.mappings().first()

def update_project(db: Session, project_id: int, project_update: schemas.ResearchProjectUpdate):
    db_project = get_project_by_id(db, project_id)
    if not db_project:
        return None
    
    update_data = project_update.model_dump(exclude_unset=True)
    if update_data:
        set_clauses = [f"{key} = :{key}" for key in update_data.keys()]
        update_query_str = f"UPDATE research_project SET {', '.join(set_clauses)} WHERE project_id = :project_id;"
        update_data["project_id"] = project_id
        db.execute(text(update_query_str), update_data)
        db.commit()
        
    return get_project_by_id(db, project_id)

def delete_project(db: Session, project_id: int):
    db_project = get_project_by_id(db, project_id)
    if not db_project:
        return None
    
    query = text("DELETE FROM research_project WHERE project_id = :project_id;")
    db.execute(query, {"project_id": project_id})
    db.commit()
    return db_project

def get_applications_for_faculty(db: Session, faculty_id: int):
    query = text("""
        SELECT a.* 
        FROM application a
        INNER JOIN research_project rp ON a.project_id = rp.project_id
        WHERE rp.faculty_id = :faculty_id;
    """)
    result = db.execute(query, {"faculty_id": faculty_id})
    return result.mappings().all()

def get_department_project_summary(db: Session):
    query = text("""
        SELECT 
            f.department,
            COUNT(DISTINCT f.faculty_id) AS faculty_count,
            COUNT(rp.project_id) AS total_projects
        FROM faculty f
        LEFT OUTER JOIN research_project rp ON f.faculty_id = rp.faculty_id
        GROUP BY f.department
        HAVING COUNT(f.faculty_id) > 0;
    """)
    result = db.execute(query)
    return result.mappings().all()

def get_projects_above_average_applications(db: Session):
    query = text("""
        SELECT * 
        FROM research_project 
        WHERE applicant_count > (
            SELECT AVG(applicant_count) 
            FROM research_project
        );
    """)
    result = db.execute(query)
    return result.mappings().all()

def get_active_projects_from_view(db: Session):
    query = text("SELECT * FROM active_projects_view;")
    result = db.execute(query)
    return result.mappings().all()

def update_application_status(db: Session, application_id: int, status_update: schemas.ApplicationStatusUpdate):
    query = text("""
        UPDATE application 
        SET status = :status 
        WHERE application_id = :application_id;
    """)
    db.execute(query, {"status": status_update.status, "application_id": application_id})
    db.commit()
    
    fetch_query = text("SELECT * FROM application WHERE application_id = :application_id;")
    result = db.execute(fetch_query, {"application_id": application_id})
    return result.mappings().first()
