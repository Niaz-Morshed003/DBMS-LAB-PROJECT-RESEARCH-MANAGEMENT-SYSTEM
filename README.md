# Research Management System — UIU

A role-based **Research Management Portal** for academic institutions, built with
**FastAPI**, **MySQL (raw SQL)** and a single-file responsive frontend. The system
connects **Students, Faculty members, Administrators and a Superadmin** through a
structured lifecycle of research projects — from proposal and application to
approval, supervision and analytics — with auditable decisions and email
notifications at every step.

---

## Highlights

- **Four distinct roles** — Student, Faculty, Admin, Superadmin — each with a
  dedicated dashboard, enforced server-side (header-based identity verified
  against the database on every sensitive call; roles cannot be spoofed).
- **Approval-driven workflows** — nothing sensitive happens silently. Sign-ups,
  designation changes, profile edits, project creation/deletion and account
  deletions all flow through Pending → Approve/Reject → Confirm stages.
- **Two-way proposal system** — admins can propose profile and project edits;
  faculty and students confirm with Yes/No. Every response is fed back to the
  originating admin as an in-app notification plus email.
- **Detailed notifications & emails** — every approval *and* every rejection
  carries its full detail (old → new values, applicant dossiers, project
  particulars) both in the Notification Hub and over Gmail SMTP (OTP, outcome,
  decision and proposal emails).
- **Permanent superadmin audit** — each admin action is mirrored into an
  immutable activity log with a rich detail popup (actor, applicant dossier,
  exact changes, request particulars), surviving even user deletions.
- **Statistics Hub** — department summaries, above-average analytics
  (`GROUP BY` + `HAVING`), popular/active project benchmarks and live graphs.
- **DBMS-complete backend** — raw-SQL DML, aggregations, INNER/LEFT JOINs,
  nested & correlated subqueries, a reusable VIEW, transactional multi-step
  operations with rollback, and documented indexes (see `INDEX_NOTES.md` and
  the criterion table below).

---

## Tech Stack

| Layer    | Technology                                              |
|----------|---------------------------------------------------------|
| Backend  | FastAPI, SQLAlchemy (engine/session only), PyMySQL      |
| Database | MySQL — every business operation is hand-written SQL   |
| Auth     | bcrypt password hashing, Gmail-SMTP OTP verification    |
| Email    | Gmail SMTP (App Password), console fallback for testing |
| Frontend | Single-file `frontend.html` (Tailwind CSS via CDN)      |
| Language | Python 3.13+, JavaScript, SQL                           |

---

## Role Capabilities

| Capability | Student | Faculty | Admin | Superadmin |
|---|:---:|:---:|:---:|:---:|
| Sign up (OTP-verified, approval-gated) | ✅ | ✅ | ✅ | — |
| Manage own profile | ✅ | ✅ | ✅ (own) | ✅ (own) |
| Browse faculty, projects, statistics | ✅ | ✅ | ✅ | ✅ |
| Apply to projects / withdraw | ✅ | — | — | — |
| Request project creation / deletion | — | ✅ (via approval) | — | — |
| Approve / reject applications with feedback | — | ✅ (own projects) | — | — |
| Approve / reject sign-ups & requests | — | — | ✅ | ✅ |
| Propose profile / project edits (faculty confirms) | — | — | ✅ | — |
| Edit anything directly (password-confirmed) | — | — | — | ✅ |
| Permanent audit log + detail popup | — | — | — | ✅ |
| Admin ↔ Superadmin channel | — | — | ✅ | ✅ |

---

## Key Workflows

1. **Onboarding** — Sign Up → 6-digit Gmail OTP → pending request → admin
   Accept/Reject → formal outcome email → login.
2. **Project application** — Student applies (motivation + password) →
   supervising faculty is emailed → faculty Approves/Rejects with feedback →
   student receives decision notification + email.
3. **Change proposals** — Admin proposes a profile/project edit → owner gets a
   detailed notification + email → Yes applies it, No keeps everything
   unchanged → the handling admin gets a feedback notification.
4. **Audit** — Every admin decision is permanently recorded and inspectable by
   the Superadmin with full applicant/change detail.

---

## DBMS Criteria Coverage

| Category | Requirement | Where in this project |
|---|---|---|
| DML | SELECT, INSERT, UPDATE, DELETE | Throughout `crud.py` (raw SQL) |
| Aggregation | ≥2 aggregates with GROUP BY and HAVING | `COUNT` + `AVG` with `GROUP BY`/`HAVING` in `get_departments_above_average_projects`; `COUNT`, `AVG` across Statistics |
| Joins | ≥2 JOIN types | `INNER JOIN` + `LEFT JOIN` in department/popular/active summaries |
| Subquery | Correlated or nested | Nested `AVG` benchmark; correlated `applicant_count` sync |
| View | Reusable VIEW in the app | `active_projects_view`, used by active-project listings |
| Transaction | Multi-step BEGIN/COMMIT/ROLLBACK | `START TRANSACTION` seed; app-level commits with `rollback()` on failure (apply, decisions, approvals) |
| Index | Manually created index + explanation | `idx_application_student`, `UNIQUE(email)`, FK/PK indexes — see `INDEX_NOTES.md` |

---

## Project Structure

```
├── NiazBackend.py        # FastAPI app — ~96 endpoints, auth middleware
├── crud.py               # All business logic (raw SQL, OTP, mail, audit)
├── models.py             # Table definitions (used for create_all only)
├── schemas.py            # Pydantic request/response models
├── database.py           # Engine + session (DATABASE_URL from .env)
├── frontend.html         # Entire UI — served at / (single-link)
├── research_management_db (5).sql  # Schema + seed data
├── INDEX_NOTES.md        # Index documentation (DBMS criterion)
├── migrate_passwords.py / generate_and_hash_passwords.py  # one-off scripts
└── .env                  # Local secrets (git-ignored, see .env.example)
```

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

Open `http://localhost:8000` (API + UI on one link) or the Live Server
frontend. Default superadmin is seeded from `.env` on first start.

---

*Developed as a DBMS lab project — United International University.*
