from __future__ import annotations

import time
import pandas as pd
import requests


APOLLO_BASE_URL = "https://api.apollo.io/v1"
BATCH_SIZE = 10

class ApolloClient:
    """Cliente delgado sobre la REST API de Apollo.io."""

    def __init__(self, key: str, timeout: float = 15.0) -> None:
        self.api_key = key
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "X-Api-Key": self.api_key,
            }
        )

    def bulk_match(self, people: list[dict]) -> list[dict | None]:
        """Llama a People Bulk Enrichment (POST /v1/people/bulk_match).

        `people` son hasta 10 dicts de parametros de match (linkedin_url,
        first_name/last_name, email, domain, etc. -- lo que soporte Apollo).
        Devuelve una lista del mismo largo y orden que `people`, con None
        donde Apollo no encontro a la persona.
        """
        if not people:
            return []
        if len(people) > BATCH_SIZE:
            raise ValueError(f"bulk_match acepta un maximo de {BATCH_SIZE} personas por llamada")

        response = self.session.post(
            f"{APOLLO_BASE_URL}/people/bulk_match",
            json={"details": people},
            timeout=self.timeout,
        )
        response.raise_for_status()
        matches = response.json().get("matches") or []
        # defensivo: si Apollo devuelve menos entradas que las pedidas, rellenamos con None
        return (matches + [None] * len(people))[: len(people)]


PERSON_FIELDS = [
    "first_name",
    "last_name",
    "linkedin_url",
    "title",
    "email_status",
    "email",
    "organization_id",
    "employment_history",
    "state",
    "city",
    "country",
    "organization", 
    "departments",
    "subdepartments",
    "seniority",
    "functions",
    "revealed_for_current_team"
]


CURRENT_JOB_FIELDS = {
    "current_job_title": "title",
    "current_job_start_date": "start_date",
    "grade_level_job": "grade_level",
    "kind_job": "kind",
    "major_job": "major",
}


COMPANY_FIELDS = {
    "company_name": "name",
    "founded_year_company": "founded_year",
    "industry_company": "industry",
    "estimated_num_employees_company": "estimated_num_employees",
    "city_company": "city",
    "state_company": "state",
    "country_company": "country",
}


def _clean_person_record(person: dict | None) -> dict:

    if not person:
        return {field: pd.NA for field in PERSON_FIELDS}

    cleaned = {field: person.get(field) for field in PERSON_FIELDS}
    cleaned["employment_history"] = [
        job for job in (person.get("employment_history") or []) if job.get("current")
    ]

    empleos_actuales = cleaned["employment_history"]
    empleo_actual = empleos_actuales[0] if empleos_actuales else {}
    for column, key in CURRENT_JOB_FIELDS.items():
        cleaned[column] = empleo_actual.get(key)

    company_actual = cleaned["organization"] or {}
    for column, key in COMPANY_FIELDS.items():
        cleaned[column] = company_actual.get(key)

    return cleaned


def _clean_person(people: pd.DataFrame) -> pd.DataFrame:

    cleaned = people.reindex(columns=PERSON_FIELDS).copy()

    cleaned["employment_history"] = cleaned["employment_history"].map(
        lambda history: [job for job in history if job.get("current")]
        if isinstance(history, list)
        else []
    )

    empleo_actual = cleaned["employment_history"].map(lambda jobs: jobs[0] if jobs else {})
    for column, key in CURRENT_JOB_FIELDS.items():
        cleaned[column] = empleo_actual.map(lambda job, key=key: job.get(key))

    company_actual = cleaned["organization"].map(lambda org: org if isinstance(org, dict) else {})
    for column, key in COMPANY_FIELDS.items():
        cleaned[column] = company_actual.map(lambda org, key=key: org.get(key))

    return cleaned




def _row_to_match_params(row: pd.Series) -> dict:

    MATCH_FIELDS = [
    "first_name",
    "last_name",
    "name",
    "email",
    "hashed_email",
    "organization_name",
    "domain",
    "linkedin_url",]

    return {
        field: row[field]
        for field in MATCH_FIELDS
        if field in row.index and pd.notna(row[field])
    }


def enrich_people(
    people: pd.DataFrame,
    client: ApolloClient,
    delay: float = 1.0,
) -> pd.DataFrame:

    match_params = [_row_to_match_params(row) for _, row in people.iterrows()]

    records: list[dict] = []
    for i in range(0, len(match_params), BATCH_SIZE):
        batch = match_params[i : i + BATCH_SIZE]
        try:
            matches = client.bulk_match(batch)
        except requests.HTTPError:
            matches = [None] * len(batch)
       # records.extend(_clean_person(match) for match in matches)
        records.extend(match if match else {} for match in matches)
        time.sleep(delay)

    #return pd.DataFrame.from_records(records, columns=PERSON_FIELDS)
    return pd.DataFrame.from_records(records)
