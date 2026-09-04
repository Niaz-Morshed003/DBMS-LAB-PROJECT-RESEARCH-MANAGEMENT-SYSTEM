DROP DATABASE IF EXISTS research_management_db;
CREATE DATABASE research_management_db;
USE research_management_db;

CREATE TABLE User (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL
);

CREATE TABLE Student (
    student_id INT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    cgpa DECIMAL(3, 2),
    department VARCHAR(100),
    semester VARCHAR(50),
    github_link VARCHAR(255),
    cv_link VARCHAR(255),
    FOREIGN KEY (student_id) REFERENCES User(user_id) ON DELETE CASCADE
);

CREATE TABLE Faculty (
    faculty_id INT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    designation VARCHAR(100),
    department VARCHAR(100),
    office_hours VARCHAR(255),
    FOREIGN KEY (faculty_id) REFERENCES User(user_id) ON DELETE CASCADE
);

CREATE TABLE Research_Project (
    project_id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    required_skill TEXT,
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    applicant_count INT DEFAULT 0,
    faculty_id INT NOT NULL,
    FOREIGN KEY (faculty_id) REFERENCES Faculty(faculty_id) ON DELETE CASCADE
);

CREATE TABLE Application (
    project_id INT NOT NULL,
    application_id INT NOT NULL,
    student_id INT NOT NULL,
    cover_letter TEXT,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50),
    PRIMARY KEY (project_id, application_id),
    FOREIGN KEY (project_id) REFERENCES Research_Project(project_id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES Student(student_id) ON DELETE CASCADE
);

CREATE TABLE Student_Skills (
    student_id INT NOT NULL,
    skill VARCHAR(100) NOT NULL,
    PRIMARY KEY (student_id, skill),
    FOREIGN KEY (student_id) REFERENCES Student(student_id) ON DELETE CASCADE
);

CREATE TABLE Faculty_Research_Areas (
    faculty_id INT NOT NULL,
    research_area VARCHAR(150) NOT NULL,
    PRIMARY KEY (faculty_id, research_area),
    FOREIGN KEY (faculty_id) REFERENCES Faculty(faculty_id) ON DELETE CASCADE
);

CREATE INDEX idx_application_student ON Application(student_id);

CREATE VIEW Active_Projects_View AS
SELECT project_id, title, status 
FROM Research_Project;