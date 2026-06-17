from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import psycopg
    from psycopg.rows import dict_row
except ModuleNotFoundError:
    psycopg = None
    dict_row = None

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")


def resolve_db_path() -> Path:
    configured_db_path = os.getenv("DB_PATH")
    if configured_db_path:
        return Path(configured_db_path).expanduser()

    if os.getenv("NETLIFY"):
        return Path("/tmp/puma-data-hub.db")

    return BASE_DIR / "data.db"


DB_PATH = resolve_db_path()

TARGET_SITES = [
    {
        "source_site": "pumapremiumconsulting.com",
        "url": "https://pumapremiumconsulting.com",
    },
    {
        "source_site": "assessment-pumapremiumconsulting.com",
        "url": "https://assessment-pumapremiumconsulting.com",
    },
]
ALLOWED_SOURCES = {site["source_site"] for site in TARGET_SITES}
RESERVED_META_KEYS = {
    "source_site",
    "source",
    "site",
    "form_name",
    "form",
    "form_id",
    "formId",
    "submittedAt",
    "submitted_at",
    "metrics",
    "qualificationTier",
    "qualification_tier",
    "leadTier",
    "lead_tier",
    "routingAction",
    "routing_action",
    "executiveSummary",
    "executiveInsights",
    "recommendedPriorities",
    "emailSequence",
    "internalNotification",
    "crm",
    "connectorPayloads",
    "connector_payloads",
    "lead",
}
QUESTION_HINT_KEYS = [
    "question",
    "question_key",
    "question_label",
    "label",
    "prompt",
    "title",
    "name",
]
ANSWER_HINT_KEYS = [
    "answer",
    "value",
    "selected",
    "response",
    "result",
    "choice",
    "option",
    "option_label",
    "selected_option",
    "selected_option_label",
]
PAIR_COLLECTION_KEYS = {
    "answers",
    "responses",
    "questions",
    "assessment_answers",
    "assessment_responses",
}

app = FastAPI(title="Puma Lead Hub", version="2.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3030",
        "http://127.0.0.1:3030",
        "https://pumapremiumconsulting.com",
        "https://www.pumapremiumconsulting.com",
        "https://assessment-pumapremiumconsulting.com",
        "https://www.assessment-pumapremiumconsulting.com",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def sql_placeholder() -> str:
    return "%s" if USE_POSTGRES else "?"


def sql_placeholders(count: int) -> str:
    return ", ".join(sql_placeholder() for _ in range(count))


def get_connection() -> Any:
    if USE_POSTGRES:
        if psycopg is None or dict_row is None:
            raise RuntimeError("psycopg non installato: esegui `pip install -r requirements.txt`.")
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def postgres_column_default(connection: Any, table_name: str, column_name: str) -> str | None:
    row = connection.execute(
        """
        SELECT column_default
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s
          AND column_name = %s
        """,
        (table_name, column_name),
    ).fetchone()
    if not row:
        return None
    return row["column_default"]


def next_form_answers_ids(connection: Any, count: int) -> list[int]:
    if count <= 0:
        return []
    connection.execute("LOCK TABLE form_answers IN EXCLUSIVE MODE")
    row = connection.execute("SELECT COALESCE(MAX(id), 0) AS max_id FROM form_answers").fetchone()
    start = int(row["max_id"]) + 1
    return list(range(start, start + count))


def schema_statements() -> list[str]:
    if USE_POSTGRES:
        return [
            """
            CREATE TABLE IF NOT EXISTS form_submissions (
                id BIGSERIAL PRIMARY KEY,
                source_site TEXT NOT NULL,
                form_name TEXT,
                full_name TEXT,
                email TEXT,
                phone TEXT,
                company TEXT,
                message TEXT,
                submitted_at TEXT NOT NULL,
                client_ip TEXT,
                user_agent TEXT,
                raw_payload TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS form_answers (
                id BIGSERIAL PRIMARY KEY,
                submission_id BIGINT NOT NULL,
                source_site TEXT NOT NULL,
                question_key TEXT NOT NULL,
                answer_value TEXT NOT NULL,
                position INTEGER NOT NULL,
                FOREIGN KEY(submission_id) REFERENCES form_submissions(id) ON DELETE CASCADE
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_form_submissions_source_site
                ON form_submissions(source_site);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_form_submissions_submitted_at
                ON form_submissions(submitted_at DESC);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_form_answers_submission_id
                ON form_answers(submission_id, position);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_form_answers_source_site
                ON form_answers(source_site);
            """,
        ]

    return [
        """
        CREATE TABLE IF NOT EXISTS form_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_site TEXT NOT NULL,
            form_name TEXT,
            full_name TEXT,
            email TEXT,
            phone TEXT,
            company TEXT,
            message TEXT,
            submitted_at TEXT NOT NULL,
            client_ip TEXT,
            user_agent TEXT,
            raw_payload TEXT NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS form_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL,
            source_site TEXT NOT NULL,
            question_key TEXT NOT NULL,
            answer_value TEXT NOT NULL,
            position INTEGER NOT NULL,
            FOREIGN KEY(submission_id) REFERENCES form_submissions(id) ON DELETE CASCADE
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_form_submissions_source_site
            ON form_submissions(source_site);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_form_submissions_submitted_at
            ON form_submissions(submitted_at DESC);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_form_answers_submission_id
            ON form_answers(submission_id, position);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_form_answers_source_site
            ON form_answers(source_site);
        """,
    ]


def init_db() -> None:
    with get_connection() as connection:
        for statement in schema_statements():
            connection.execute(statement)
        connection.commit()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_source_site(source_site: Any) -> str:
    source = str(source_site or "").strip().lower()
    if not source:
        raise HTTPException(status_code=422, detail="Campo source_site obbligatorio.")

    if "://" in source:
        parsed = urlparse(source)
        source = parsed.netloc or parsed.path

    if source.startswith("www."):
        source = source[4:]
    source = source.rstrip("/")

    if source not in ALLOWED_SOURCES:
        raise HTTPException(status_code=422, detail=f"Sorgente non valida: {source}.")
    return source


def normalize_if_allowed(source_site: Any) -> str | None:
    try:
        return normalize_source_site(source_site)
    except HTTPException:
        return None


def scalar_to_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text if text else None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return None


def extract_first_text(value: Any) -> str | None:
    text = scalar_to_text(value)
    if text is not None:
        return text

    if isinstance(value, list):
        for item in value:
            nested_text = extract_first_text(item)
            if nested_text:
                return nested_text
        return None

    if isinstance(value, dict):
        for nested in value.values():
            nested_text = extract_first_text(nested)
            if nested_text:
                return nested_text

    return None


def first_non_empty(payload: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        if key not in payload:
            continue
        text = extract_first_text(payload.get(key))
        if text:
            return text
    return None


def extract_lead_fields(payload: dict[str, Any]) -> dict[str, str | None]:
    full_name = first_non_empty(
        payload,
        [
            "full_name",
            "name",
            "nome",
            "lead_name",
            "customer_name",
            "client_name",
            "executive_name",
            "contact_name",
            "fullName",
        ],
    )
    if not full_name:
        first_name = first_non_empty(payload, ["first_name", "first", "contact_first_name"])
        last_name = first_non_empty(payload, ["last_name", "last", "contact_last_name"])
        if first_name or last_name:
            full_name = " ".join(part for part in [first_name, last_name] if part)

    return {
        "form_name": first_non_empty(payload, ["form_name", "form", "form_id", "formId"]),
        "full_name": full_name,
        "email": first_non_empty(
            payload,
            ["email", "mail", "e_mail", "email_address", "work_email", "business_email", "contact_email"],
        ),
        "phone": first_non_empty(
            payload,
            ["phone", "telefono", "mobile", "tel", "contact_phone", "mobile_phone", "whatsapp"],
        ),
        "company": first_non_empty(
            payload,
            ["company", "azienda", "organization", "impresa", "company_name", "organization_name", "business_name"],
        ),
        "message": first_non_empty(
            payload,
            ["message", "messaggio", "notes", "note", "comment", "additional_notes", "details"],
        ),
    }


def merge_payload_with_nested_lead(payload: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(payload)
    nested_lead = payload.get("lead")
    if not isinstance(nested_lead, dict):
        return merged

    for key, value in nested_lead.items():
        if key not in merged:
            merged[key] = value

    if "first_name" not in merged and "firstName" in nested_lead:
        merged["first_name"] = nested_lead.get("firstName")
    if "last_name" not in merged and "lastName" in nested_lead:
        merged["last_name"] = nested_lead.get("lastName")
    if "full_name" not in merged:
        first_name = extract_first_text(merged.get("first_name"))
        last_name = extract_first_text(merged.get("last_name"))
        if first_name or last_name:
            merged["full_name"] = " ".join(part for part in [first_name, last_name] if part)
    if "company_name" not in merged and "company" in nested_lead:
        merged["company_name"] = nested_lead.get("company")
    if "email_address" not in merged and "email" in nested_lead:
        merged["email_address"] = nested_lead.get("email")
    if "contact_phone" not in merged and "phone" in nested_lead:
        merged["contact_phone"] = nested_lead.get("phone")
    return merged


def infer_source_site(request: Request, payload: dict[str, Any]) -> str:
    explicit_source = (
        payload.get("source_site")
        or payload.get("source")
        or payload.get("site")
        or request.headers.get("x-source-site")
    )
    if explicit_source:
        return normalize_source_site(explicit_source)

    for header_name in ["origin", "referer"]:
        header_value = request.headers.get(header_name)
        if not header_value:
            continue
        inferred = normalize_if_allowed(header_value)
        if inferred:
            return inferred

    nested_lead = payload.get("lead")
    if isinstance(nested_lead, dict):
        for hint_key in ["website", "domain", "source_site", "source"]:
            if hint_key in nested_lead:
                inferred = normalize_if_allowed(nested_lead.get(hint_key))
                if inferred:
                    return inferred

    raise HTTPException(status_code=422, detail="Campo source_site mancante o non riconoscibile.")


def append_payload_value(payload: dict[str, Any], key: str, value: str) -> None:
    if key not in payload:
        payload[key] = value
        return

    current = payload[key]
    if isinstance(current, list):
        current.append(value)
        return

    payload[key] = [current, value]


async def parse_submission_payload(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "").lower()

    if "application/json" in content_type:
        raw_body = await request.body()
        if not raw_body:
            return {}
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=400, detail="JSON non valido.") from exc

        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="Payload non valido.")
        return payload

    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form = await request.form()
        payload: dict[str, Any] = {}
        for key, value in form.multi_items():
            if hasattr(value, "filename"):
                text_value = str(getattr(value, "filename", "")).strip()
            else:
                text_value = str(value).strip()
            append_payload_value(payload, key, text_value)
        return payload

    raw_body = await request.body()
    if not raw_body:
        return {}
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=415,
            detail="Content-Type non supportato. Usa JSON, form-urlencoded o multipart/form-data.",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Payload non valido.")
    return payload


def flatten_answers(value: Any, key_path: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    if isinstance(value, str):
        maybe_json = parse_json_like_string(value)
        if maybe_json is not None:
            return flatten_answers(maybe_json, key_path)

    if isinstance(value, dict):
        direct_question_answers = extract_question_answer_entries_from_dict(value)
        if direct_question_answers:
            return direct_question_answers
        for nested_key, nested_value in value.items():
            child_key = f"{key_path}.{nested_key}" if key_path else str(nested_key)
            entries.extend(flatten_answers(nested_value, child_key))
        return entries

    if isinstance(value, list):
        base_key = key_path.split(".")[-1].split("[")[0]
        if base_key in PAIR_COLLECTION_KEYS:
            for item in value:
                if isinstance(item, dict):
                    direct_question_answers = extract_question_answer_entries_from_dict(item)
                    if direct_question_answers:
                        entries.extend(direct_question_answers)
                        continue
                entries.extend(flatten_answers(item, key_path))
            return entries
        for index, item in enumerate(value, start=1):
            if isinstance(item, (dict, list)):
                entries.extend(flatten_answers(item, f"{key_path}[{index}]"))
                continue

            text = scalar_to_text(item)
            if text:
                entries.append((key_path, text))
        return entries

    text = scalar_to_text(value)
    if text:
        entries.append((key_path, text))
    return entries


def parse_json_like_string(value: str) -> Any | None:
    text = value.strip()
    if len(text) < 2:
        return None
    if not ((text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]"))):
        return None

    try:
        return json.loads(text)
    except Exception:
        return None


def answer_values_from_unknown(value: Any) -> list[str]:
    if isinstance(value, str):
        maybe_json = parse_json_like_string(value)
        if maybe_json is not None:
            return answer_values_from_unknown(maybe_json)
        text = scalar_to_text(value)
        return [text] if text else []

    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(answer_values_from_unknown(item))
        return values

    if isinstance(value, dict):
        values: list[str] = []
        for key in ANSWER_HINT_KEYS:
            if key in value:
                values.extend(answer_values_from_unknown(value[key]))
        if values:
            return values

        for nested_value in value.values():
            text = scalar_to_text(nested_value)
            if text:
                values.append(text)
        return values

    text = scalar_to_text(value)
    return [text] if text else []


def unique_preserve_order(values: list[str]) -> list[str]:
    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        marker = normalized.lower()
        if marker in seen:
            continue
        seen.add(marker)
        unique_values.append(normalized)
    return unique_values


def extract_question_answer_entries_from_dict(data: dict[str, Any]) -> list[tuple[str, str]]:
    question = first_non_empty(data, QUESTION_HINT_KEYS)
    if not question:
        return []

    candidate_answers: list[str] = []
    for key in ANSWER_HINT_KEYS:
        if key in data:
            candidate_answers.extend(answer_values_from_unknown(data[key]))

    if not candidate_answers:
        for fallback_key in ["answers", "selections", "selected_options", "selectedOptions"]:
            if fallback_key in data:
                candidate_answers.extend(answer_values_from_unknown(data[fallback_key]))

    candidate_answers = unique_preserve_order(candidate_answers)
    if not candidate_answers:
        return []
    return [(question, answer) for answer in candidate_answers]


def extract_answer_entries(payload: dict[str, Any]) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for key, value in payload.items():
        key_text = str(key).strip()
        if not key_text or key_text in RESERVED_META_KEYS:
            continue

        flattened = flatten_answers(value, key_text)
        for question_key, answer_value in flattened:
            question = question_key.strip()
            answer = answer_value.strip()
            if not question or not answer:
                continue

            dedupe_key = (question.lower(), answer.lower())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            entries.append((question, answer))

    return entries


def save_lead_submission(
    source_site: str,
    lead_fields: dict[str, str | None],
    raw_payload: dict[str, Any],
    answer_entries: list[tuple[str, str]],
    client_ip: str | None,
    user_agent: str | None,
) -> tuple[int, str, int]:
    submitted_at = utc_now_iso()
    payload_json = json.dumps(raw_payload, ensure_ascii=False)
    params = (
        source_site,
        lead_fields["form_name"],
        lead_fields["full_name"],
        lead_fields["email"],
        lead_fields["phone"],
        lead_fields["company"],
        lead_fields["message"],
        submitted_at,
        client_ip,
        user_agent,
        payload_json,
    )

    with get_connection() as connection:
        insert_submission_sql = f"""
            INSERT INTO form_submissions (
                source_site,
                form_name,
                full_name,
                email,
                phone,
                company,
                message,
                submitted_at,
                client_ip,
                user_agent,
                raw_payload
            )
            VALUES ({sql_placeholders(11)})
        """
        if USE_POSTGRES:
            cursor = connection.execute(f"{insert_submission_sql} RETURNING id", params)
            inserted = cursor.fetchone()
            if not inserted:
                raise HTTPException(status_code=500, detail="Errore salvataggio lead.")
            submission_id = int(inserted["id"])
        else:
            cursor = connection.execute(insert_submission_sql, params)
            submission_id = int(cursor.lastrowid)

        if answer_entries:
            answer_rows = [
                (submission_id, source_site, question, answer, position)
                for position, (question, answer) in enumerate(answer_entries, start=1)
            ]

            manual_id_required = False
            if USE_POSTGRES:
                id_default = postgres_column_default(connection, "form_answers", "id")
                manual_id_required = id_default is not None and not str(id_default).strip()

            if manual_id_required:
                manual_ids = next_form_answers_ids(connection, len(answer_rows))
                insert_answers_sql = f"""
                    INSERT INTO form_answers (
                        id,
                        submission_id,
                        source_site,
                        question_key,
                        answer_value,
                        position
                    )
                    VALUES ({sql_placeholders(6)})
                """
                connection.executemany(
                    insert_answers_sql,
                    [
                        (manual_id, *row)
                        for manual_id, row in zip(manual_ids, answer_rows)
                    ],
                )
            else:
                insert_answers_sql = f"""
                    INSERT INTO form_answers (
                        submission_id,
                        source_site,
                        question_key,
                        answer_value,
                        position
                    )
                    VALUES ({sql_placeholders(5)})
                """
                connection.executemany(insert_answers_sql, answer_rows)

        connection.commit()

    return submission_id, submitted_at, len(answer_entries)


def query_leads(source_site: str | None, limit: int) -> list[dict[str, Any]]:
    with get_connection() as connection:
        if source_site:
            source = normalize_source_site(source_site)
            limit_with_source_sql = f"""
                SELECT
                    id,
                    source_site,
                    form_name,
                    full_name,
                    email,
                    phone,
                    company,
                    message,
                    submitted_at
                FROM form_submissions
                WHERE source_site = {sql_placeholder()}
                ORDER BY id DESC
                LIMIT {sql_placeholder()}
            """
            submission_rows = connection.execute(
                limit_with_source_sql,
                (source, limit),
            ).fetchall()
        else:
            limit_all_sql = f"""
                SELECT
                    id,
                    source_site,
                    form_name,
                    full_name,
                    email,
                    phone,
                    company,
                    message,
                    submitted_at
                FROM form_submissions
                ORDER BY id DESC
                LIMIT {sql_placeholder()}
            """
            submission_rows = connection.execute(
                limit_all_sql,
                (limit,),
            ).fetchall()

        if not submission_rows:
            return []

        submission_ids = [int(row["id"]) for row in submission_rows]
        placeholders = sql_placeholders(len(submission_ids))
        answer_rows = connection.execute(
            f"""
            SELECT
                submission_id,
                question_key,
                answer_value,
                position
            FROM form_answers
            WHERE submission_id IN ({placeholders})
            ORDER BY submission_id DESC, position ASC
            """,
            tuple(submission_ids),
        ).fetchall()

    grouped_answers: dict[int, list[dict[str, Any]]] = {}
    for row in answer_rows:
        submission_id = int(row["submission_id"])
        grouped_answers.setdefault(submission_id, []).append(
            {
                "question_key": row["question_key"],
                "answer_value": row["answer_value"],
                "position": row["position"],
            }
        )

    items: list[dict[str, Any]] = []
    for row in submission_rows:
        item = dict(row)
        answers = grouped_answers.get(int(row["id"]), [])
        item["answers"] = answers
        item["answer_count"] = len(answers)
        items.append(item)
    return items


def query_lead_summary() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                source_site,
                COUNT(*) AS total_leads,
                MAX(submitted_at) AS last_submitted_at
            FROM form_submissions
            GROUP BY source_site
            ORDER BY source_site
            """
        ).fetchall()

    summary_by_source = {row["source_site"]: dict(row) for row in rows}
    output: list[dict[str, Any]] = []
    for site in TARGET_SITES:
        source = site["source_site"]
        if source in summary_by_source:
            output.append(summary_by_source[source])
        else:
            output.append(
                {
                    "source_site": source,
                    "total_leads": 0,
                    "last_submitted_at": None,
                }
            )
    return output


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/")
def index() -> FileResponse:
    if not STATIC_DIR.exists():
        raise HTTPException(status_code=404, detail="Dashboard static non disponibile in questo runtime.")
    return FileResponse(STATIC_DIR / "index.html")


def serve_root_static_asset(filename: str, media_type: str | None = None) -> FileResponse:
    asset_path = STATIC_DIR / filename
    if not asset_path.exists():
        raise HTTPException(status_code=404, detail=f"Asset non trovato: {filename}")
    return FileResponse(asset_path, media_type=media_type)


@app.get("/styles.css")
def styles_css() -> FileResponse:
    return serve_root_static_asset("styles.css", media_type="text/css")


@app.get("/app.js")
def app_js() -> FileResponse:
    return serve_root_static_asset("app.js", media_type="application/javascript")


@app.get("/api/sources")
def sources() -> dict[str, Any]:
    return {"sources": [site["source_site"] for site in TARGET_SITES]}


@app.post("/api/leads")
async def receive_lead(request: Request) -> dict[str, Any]:
    payload = await parse_submission_payload(request)
    source_site = infer_source_site(request, payload)
    lead_context = merge_payload_with_nested_lead(payload)
    lead_fields = extract_lead_fields(lead_context)
    answer_entries = extract_answer_entries(payload)

    if not any(
        [
            lead_fields["full_name"],
            lead_fields["email"],
            lead_fields["phone"],
            lead_fields["company"],
            lead_fields["message"],
        ]
    ) and not answer_entries:
        raise HTTPException(
            status_code=422,
            detail="Nessun dato cliente o risposta valida trovata nel payload del form.",
        )

    lead_id, submitted_at, answer_count = save_lead_submission(
        source_site=source_site,
        lead_fields=lead_fields,
        raw_payload=payload,
        answer_entries=answer_entries,
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {
        "message": "Lead salvata con successo.",
        "lead_id": lead_id,
        "source_site": source_site,
        "submitted_at": submitted_at,
        "answer_count": answer_count,
    }


@app.get("/api/leads")
def leads(
    source_site: str | None = Query(default=None),
    limit: int = Query(default=300, ge=1, le=3000),
) -> dict[str, Any]:
    items = query_leads(source_site=source_site, limit=limit)
    return {"count": len(items), "items": items}


@app.get("/api/lead-summary")
def lead_summary() -> dict[str, Any]:
    return {"summary": query_lead_summary()}