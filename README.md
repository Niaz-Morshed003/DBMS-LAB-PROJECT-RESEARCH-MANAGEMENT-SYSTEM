# Research Management System (UIU): Complete Technical Documentation

## Abstract

The Research Management System is a role-based academic research portal that
digitises the full lifecycle of university research collaboration: faculty
publish research projects, students apply with credentials and motivation,
faculty review and decide, and administrators govern every sensitive
transition through explicit approval chains. A Superadmin holds absolute,
audit-logged authority above all roles. The system comprises **≈13,400 lines
of code**, **96 API endpoints**, **21 notification types**, **12 email
dispatches**, and a MySQL schema of 10 tables plus one reusable view — with
all business logic written in hand-authored SQL.

---

## 1. Introduction

In most departments, research collaboration still runs on word of mouth:
a faculty member announces a project, interested students email CVs, and
decisions disappear into inboxes. There is no record of who applied, who was
rejected and why, who changed whose profile, or who authorised what. This
project replaces that informal pipeline with a governed system in which
**no sensitive state change is silent**: every sign-up, edit, creation,
deletion and decision passes through a visible request → review → confirm
chain, is mirrored to the affected party's Notification Hub, is emailed in
full detail, and — for administrative acts — is preserved permanently in a
Superadmin audit log.

## 2. System Architecture

| Layer | Implementation |
|---|---|
| Backend | FastAPI (`NiazBackend.py`), ~96 endpoints in 8 tagged modules |
| Data access | Hand-written SQL via SQLAlchemy `text()`; ORM used only for `create_all` |
| Database | MySQL (`research_management_db`), 10 tables + 1 view |
| Authentication | bcrypt password hashing; per-request `X-User-Id` + `X-User-Role` headers verified against the `user` table by middleware — roles cannot be spoofed |
| Verification | 6-digit Gmail-SMTP OTP (10-minute validity, 60s/5-per-hour rate limits), separate stores for sign-up and password-reset codes |
| Email | Gmail SMTP with 12 distinct dispatch paths; automatic console fallback for testing |
| Frontend | One self-contained `frontend.html` (Tailwind CSS), served by the backend itself at `/` — a single link runs the whole system |

## 3. Roles and Access Control

| Capability | Student | Faculty | Admin | Superadmin |
|---|:---:|:---:|:---:|:---:|
| OTP-verified sign-up (approval-gated) | Yes | Yes | Yes | — |
| Manage own profile | Yes | Yes | Own only | Own only |
| Browse faculty, projects, statistics | Yes | Yes | Yes | Yes |
| Apply to projects / withdraw | Yes | — | — | — |
| Request project creation / deletion | — | Yes (via approval) | — | — |
| Decide applications with feedback | — | Yes (own projects) | — | — |
| Approve/reject sign-ups and requests | — | — | Yes | Yes |
| Propose profile/project edits (owner confirms) | — | — | Yes | — |
| Direct edit/delete (own-password confirmed) | — | — | — | Yes |
| Permanent audit log | — | — | — | Yes |

Students are explicitly barred from the Student Directory (HTTP 403);
admins have view-only project access and can never change passwords;
the Superadmin cannot delete its own account.

## 4. Feature and Function Catalogue

### 4.1 Authentication (`/auth/*`)
`POST /auth/login` (bcrypt verification), `POST /auth/send-otp`,
`POST /auth/signup/{faculty,admin,student}` (OTP-gated, creates a *pending*
request — never a direct account), `POST /auth/forgot-password`,
`POST /auth/reset-password`, `POST /auth/check-student-unique`
(case-insensitive duplicate detection for email, GitHub and CV links, plus
strict format validation: whitelisted mail domains, `github.com/*` URLs,
CGPA 0.00–4.00).

### 4.2 Student module (`/student/*`)
Profile view/edit (name, links, skills and interests save directly;
CGPA/department/semester require admin approval plus the student's own
confirmation), account-deletion request, project application (motivation and
current password mandatory; duplicate and inactive-project applications
rejected), application withdrawal (pending only, with faculty notification),
and a personal Notification Hub (decisions acknowledged; proposals answered
Yes/No with old → new detail boxes).

### 4.3 Faculty module (`/faculty/*`)
Own-profile management (designation changes need admin approval),
faculty directory, own-project management (creation is a *request*, edits are
direct, deletion is a request), others'-projects browser, own-applications
review with full applicant dossiers (CGPA, skills, links, motivation, all
applied projects and their statuses), Approve/Reject with mandatory feedback
on rejection (decisions are final and immutable), and the Student Directory
(all students or by department, with full profiles).

### 4.4 Admin module (`/admin/*`)
Admin roster (own record only editable), faculty and student listings with
department filters, project and application browsers, the Pending Approval
Hub (sign-ups with OTP-match badges, designation and deletion requests,
project creation/deletion, profile changes), edit *proposals* (never direct
edits) to any faculty, student or project, a Proposal Responses inbox showing
which owner accepted or rejected each proposal, and a private channel to the
Superadmin.

### 4.5 Superadmin module (`/superadmin/*`)
Direct, password-confirmed CRUD over every user and project (owners are
notified by in-app message and email), pending-request adjudication, the
immutable audit log and admin-activity record with a full-detail popup
(actor, applicant dossier, exact old → new changes, request particulars),
the admin channel, and self-account management.

### 4.6 Statistics, Search, Chat
Department summaries, popular-project benchmarks (average applications per
active project), active-project tracking via a SQL VIEW, departments above
the per-department average (`GROUP BY` + `HAVING` + nested `AVG` subquery,
with the arithmetic shown live: total ÷ departments = average), live graphs,
role-scoped global search (2+ characters, 50 hits), and a persistent
Superadmin ↔ Admin message channel with unread badges and email alerts.

## 5. Notification System — Complete Matrix

Every notification lives in the `notification` table with a JSON payload and
a status of Pending, Accepted, Rejected, Acknowledged,
AwaitingFacultyConfirmation or AwaitingStudentConfirmation.

| # | Type | Trigger (what causes it) | Recipient hub |
|---|---|---|---|
| 1–3 | AdminSignup, FacultySignup, StudentSignup | A sign-up form + OTP is submitted | Admin Hub (Pending) |
| 4 | DesignationChange | Faculty edits own designation | Admin Hub → then faculty (AwaitingFacultyConfirmation) |
| 5 | AccountDeletion | Faculty requests account removal | Admin Hub |
| 6 | AdminFacultyEditRequest | Admin proposes a faculty-profile edit | That faculty (Pending) |
| 7 | AdminStudentEditRequest | Admin proposes a student-profile edit | That student (Pending) |
| 8 | AdminProjectEditRequest | Admin proposes a project edit | Owning faculty (Pending) |
| 9 | ProjectCreation | Faculty requests a new project | Admin Hub → then faculty (confirm) |
| 10 | ProjectDeletion | Faculty requests project removal | Admin Hub |
| 11–14 | …CreationResult, …DeletionResult, AccountDeletionResult, DesignationChangeResult | Admin rejects (or the outcome of) the above | Requesting faculty (acknowledge) |
| 15–16 | StudentProfileChange (+Result) | Student requests CGPA/dept/semester change; admin accepts → student confirms, or admin rejects with full detail | Admin Hub → student |
| 17 | StudentAccountDeletion (+Result) | Student requests deletion | Admin Hub → student |
| 18 | ProjectApplication | Student applies | Owning faculty |
| 19 | ApplicationDecision | Faculty approves/rejects (feedback attached) | Applicant student |
| 20 | SuperAdminProjectUpdate | Superadmin edits a project directly | Owning faculty |
| 21 | ProposalResponse | Any owner answers any proposal | The handling admin (feedback inbox) |
| — | AdminActivity / SuperAdminAction | Any admin/superadmin act | Superadmin audit only (never deleted) |

The governing rule: **rejections always name the exact rejected request**,
and **approvals that need a second confirmation say so explicitly** — no
generic "your request was rejected" dead-ends exist in the system.

## 6. Email System — Complete Matrix

| # | Email | Sent exactly when | To |
|---|---|---|---|
| 1 | Sign-up OTP | Send-code is pressed (6 digits, 10 min) | The applicant |
| 2 | Password-reset OTP | Forgot-password is pressed | The registered user |
| 3 | Sign-up outcome | Admin accepts/rejects a sign-up (role-specific wording) | The applicant |
| 4 | Profile-change approved | Admin approves a student/faculty change ("now your Yes/No turn") | The requester |
| 5 | Profile-change rejected | Admin rejects, with the exact rejected detail | The requester |
| 6 | Admin proposal notice | Admin proposes any profile/project edit | The owner (faculty/student) |
| 7 | New application | A student applies (name, CGPA, motivation) | Supervising faculty |
| 8 | Application receipt | Same moment, as acknowledgement | The applicant student |
| 9 | Application decision | Faculty approves/rejects (feedback included) | The applicant student |
| 10 | Project request outcome | Admin accepts/rejects creation/deletion | The faculty |
| 11 | Response-to-originator | An owner answers a proposal | Only the handling admin |
| 12 | Withdrawal / deletion / direct-edit notices | Withdrawals, carried-out deletions, superadmin edits, chat messages | The affected party / channel peer |

## 7. Traced End-to-End Workflows

**A. Student onboarding:** form + OTP → `StudentSignup` (Pending, OTP-match
badge visible) → admin Accept creates `user` + `student` rows and emails
approval → login. Reject emails the reason path and records a detailed result.

**B. Project application:** apply (password + motivation) → row inserted,
`applicant_count` synced, `ProjectApplication` + email to faculty → faculty
opens the dossier, Approves/Rejects with feedback (immutable) →
`ApplicationDecision` + email to student → acknowledge.

**C. Admin project-edit proposal:** Propose Edit from list, search or faculty
detail → duplicate-guarded single `AdminProjectEditRequest` + detailed email
→ faculty Yes writes to `research_project`, No leaves it untouched → handling
admin receives feedback notification + email.

**D. Destructive requests:** account/project deletions execute only on admin
Accept (contact captured *before* deletion for the record and the notice
email); rejections keep everything and explain exactly what was refused.

## 8. Database Design

`user` (auth root; `user_id` reused as faculty/student PK with cascading
FKs) → `faculty` + `faculty_research_areas` → `research_project`
(`applicant_count` maintained by correlated subqueries) → `application`
(composite PK, per-application profile snapshot + motivation + feedback) →
`notification` (nullable faculty/student owners, typed JSON payloads) →
`superadmin_chat`. Supporting evidence of rigour: `active_projects_view`
(VIEW), `idx_application_student` and `UNIQUE(email)` with written rationale
(`INDEX_NOTES.md`), `INNER`/`LEFT JOIN` discipline so empty sides are never
silently dropped, and every multi-step write committed atomically with
rollback on failure.

## 9. Strengths

1. **Governance by construction.** The database can never reach a sensitive
   state through the UI without a recorded approval — creation, deletion and
   privilege-adjacent edits all require a second party's explicit Yes.
2. **Rejections with evidence.** Rejected parties see precisely which fields
   and values were refused, in-app and by email — the single most common
   failure of comparable student projects, absent here.
3. **Spoof-proof authorisation.** Roles are re-verified against the `user`
   table per request; the client-supplied role string is never trusted.
4. **Permanent accountability.** The Superadmin audit survives the deletion of
   the very users it describes (contacts frozen at handling time), with a
   structured detail popup instead of raw JSON.
5. **Idempotency where it matters.** Double-submits (observed in testing:
   two identical proposals one second apart) are blocked in the UI and
   rejected in the backend.
6. **DBMS-complete implementation.** DML, multi-aggregate `GROUP BY` +
   `HAVING`, both JOIN types, nested and correlated subqueries, a consumed
   VIEW, transactional writes and documented indexes — all inside real
   features, verified live (54 running projects / 7 departments / 7.7 average
   at the time of writing).
7. **Single-link deployment.** Backend serves API and UI from one origin; the
   same build runs on localhost and on a server unchanged.

## 10. Limitations and Future Work

OTP and mail depend on a Gmail App Password (console fallback exists for
evaluation); there is no pagination on large lists beyond the 50-hit search
cap; audit search is chronological only; and file uploads (CVs, avatars) are
links rather than stored objects. Natural next steps: refresh-token sessions,
paginated listings, full-text search, and in-system file storage.

## 11. Conclusion

The system meets its goal: a complete, governed, auditable research
collaboration portal in which every actor's powers, every request's fate and
every decision's author are visible, notified, emailed and permanently
recorded.

---

## Run Locally

```powershell
# 1. Create schema + seed
mysql -u root -p < "research_management_db (5).sql"

# 2. Configure secrets
copy .env.example .env   # then fill Gmail + superadmin values

# 3. Install & run
pip install -r requirements.txt
uvicorn NiazBackend:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` (API + UI on one link). Default superadmin is
seeded from `.env` on first start.

*Developed as a DBMS lab project — United International University.*
