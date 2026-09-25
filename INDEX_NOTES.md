# Database Indexes — Why Each Index Was Added
Research Management System (`research_management_db`) · DBMS Lab Project

This document is the **written explanation** for every manually created index
in the project (DBMS criterion: *"At least one manually created index with a
written explanation of why it was added"*). All indexes below are defined in
`research_management_db (5).sql` (ALTER TABLE section) and are actively used
by the backend's raw-SQL queries in `crud.py`.

## 1. `user.email` — UNIQUE KEY (`email`)
- **Why:** Login (`SELECT ... FROM user WHERE email = ...` on every sign-in),
  duplicate-email checks (`_email_taken`, signup OTP flow) and password-reset
  lookups all filter by exact email. A UNIQUE index makes these O(log n)
  instead of full-table scans **and** guarantees at the database level that
  two accounts can never share an email (data integrity, not just app logic).

## 2. `application.student_id` — KEY `idx_application_student`
- **Why:** This is the **only manually named secondary index** in the schema.
  Almost every student-facing query filters by it: "My Applications"
  (`WHERE student_id = ... ORDER BY applied_at DESC`), withdraw
  (`WHERE project_id AND student_id`), faculty application-detail joins and
  applicant-count syncs. Without it, each of these would scan the whole
  `application` table.

## 3. `research_project.faculty_id` — KEY (`faculty_id`)
- **Why:** "Projects by faculty", "applications for faculty" (which first
  selects `project_id ... WHERE faculty_id = ...`), department summaries and
  the `JOIN faculty f ON rp.faculty_id` used across the Statistics module all
  filter/join on this column.

## 4. Composite PRIMARY KEYs (also indexes)
- `application (project_id, application_id)` — applications are always
  addressed per project (`WHERE project_id AND application_id`), so the
  leftmost column serves project-scoped lookups directly.
- `faculty_research_areas (faculty_id, research_area)`,
  `student_skills (student_id, skill)`,
  `student_interests (student_id, research_area)` — all filtered by their
  leftmost id column when loading profiles/directories.
- `user (user_id)`, `faculty (faculty_id)`, `student (student_id)`,
  `research_project (project_id)` — single-column PKs backing every
  `WHERE ... id = ...` lookup and every FOREIGN KEY join.

## 5. Foreign-key indexes (used by every JOIN in the app)
- The FK columns above (`research_project.faculty_id`,
  `application.project_id/student_id`, etc.) back the INNER/LEFT JOINs in
  `get_department_project_summary`, `get_popular_projects_*`,
  `get_active_projects_*`, `get_departments_above_average_projects` and the
  correlated subquery that syncs `applicant_count`.

## How to demonstrate (viva)
1. `SHOW INDEX FROM application;` → point at `idx_application_student`.
2. `EXPLAIN SELECT * FROM application WHERE student_id = 1;` → `key` column
   shows `idx_application_student` (not `ALL`/full scan).
3. Drop it in a test copy and re-run EXPLAIN to show the difference.
