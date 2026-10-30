import pandas as pd
from pymongo import MongoClient
from prospeccion.df_limpieza import save_dataframe_json



COMPANY_FIELDS = {
    "company_id": "_id",
    "coresignal_id": "coresignal_id",
    "outreach_status": "outreach_status",
    "created_at": "created_at",
    "updated_at": "updated_at",
    "company_name": "record.company_name",
    "source": "source",
    "industry": "record.industry",
    "founded_year": "record.founded_year",
    "hq_country": "record.hq_country",
    "hq_state": "record.hq_state",
    "hq_city": "record.hq_city",
    "employees_count_inferred": "record.employees_count_inferred",
}


# orden del catálogo (campo position): así la misma combinación siempre da el mismo código
PRODUCT_ORDER = ["pre_screener", "talent_acquisition", "contract_management"]

PRODUCT_CODES = {
    "pre_screener": "PS",
    "talent_acquisition": "TA",
    "contract_management": "CM",   # ajusta a tu codificación
}
NO_PRODUCT = "SIN_PRODUCTO"        # cuando products == []


def encode_products(products) -> str:
    if not isinstance(products, list) or not products:
        return NO_PRODUCT
    ordered = sorted(
        set(products),
        key=lambda k: (PRODUCT_ORDER.index(k) if k in PRODUCT_ORDER else 99, k),
    )
    return "-".join(PRODUCT_CODES.get(k, f"?{k}") for k in ordered)



# rutas que solo sirven para sacar la fecha de contacto
DATE_PATHS = ["updated_at", "created_at"]

COMPANY_PROJECTION = {p: 1 for p in [*COMPANY_FIELDS.values(), *DATE_PATHS]}
COMPANY_PROJECTION["products"] = 1





def get_path(doc: dict, path: str, default=None):
    cur = doc
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def flatten_company(doc: dict) -> dict:

    # Este es un ciclo
    row = {name: get_path(doc, path) for name, path in COMPANY_FIELDS.items()}
    row["company_id"] = str(row["company_id"])  # ObjectId -> str
    row["product"] = encode_products(get_path(doc, "products"))
    # los descalificados no tienen contact_flow, usamos disqualified.at como respaldo
    row["contact_date"] = (
        get_path(doc, "created_at") or get_path(doc, "updated_at")
    )
    return row


def coerce_company_types(df: pd.DataFrame) -> pd.DataFrame:
    for col in ("founded_year", "employees_count_inferred"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in ( "contact_date", "updated_at"):
        df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    return df




# nombre final de la columna -> ruta en el documento
USER_FIELDS = {
    "company_id": "company_id", # Cruce con companie prospect
    "first_name": "first_name",
    "last_name": "last_name",
    "linkedin_url": "linkedin_url",
    "title": "title",
    "seniority": "seniority",
    "email": "email",
    "email_status": "email_status",
    "city": "city",
    "state": "state",
    "country": "country",
    "created_at": "created_at",
    "is_primary": "is_primary",
    # la empresa según Apollo solo vive en raw_profile (en organization hay 5 campos)
    "company": "raw_profile.organization.name",
   # "company_domain": "raw_profile.organization.primary_domain",
    "founded_year_company": "raw_profile.organization.founded_year",
    "industry_company": "raw_profile.organization.industry",
    "estimated_num_employees_company": "raw_profile.organization.estimated_num_employees",
    "city_company": "raw_profile.organization.city",
    "state_company": "raw_profile.organization.state",
    "country_company": "raw_profile.organization.country",
    # momentum según Apollo, con la fecha del snapshot
   # "headcount_growth_6m": "raw_profile.organization.organization_headcount_six_month_growth",
   # "headcount_growth_12m": "raw_profile.organization.organization_headcount_twelve_month_growth",
   # "apollo_refreshed_at": "raw_profile.last_refreshed_at",
}

# campos que son lista: nos quedamos con el primer elemento
LIST_FIRST = {
    "departments_primary": "departments",
    "subdepartments_primary": "subdepartments",
    "functions_primary": "functions",
}

USER_PROJECTION = {
    "_id": 0,
    **{p: 1 for p in [*USER_FIELDS.values(), *LIST_FIRST.values(), "employment_history"]},
}


def flatten_user(doc: dict) -> dict:
    row = {name: get_path(doc, path) for name, path in USER_FIELDS.items()}

    for name, path in LIST_FIRST.items():
        lst = get_path(doc, path)
        row[name] = lst[0] if isinstance(lst, list) and lst else None

    # trabajo actual: el elemento de employment_history con current == True
    actual = next((j for j in (doc.get("employment_history") or []) if j.get("current")), {})
    row["current_job_title"] = actual.get("title")
    row["current_job_start_date"] = actual.get("start_date")
    
    return row


def coerce_user_types(df: pd.DataFrame) -> pd.DataFrame:
    for col in ("founded_year_company", "estimated_num_employees_company"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in ("created_at", ):
        df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    df["current_job_start_date"] = pd.to_datetime(df["current_job_start_date"], errors="coerce")
    return df


def first_user_per_company(df: pd.DataFrame) -> pd.DataFrame:
    """Un usuario por empresa: primero el is_primary, luego el más antiguo."""
    df["is_primary"] = df["is_primary"].fillna(False).astype(bool)
    return (
        df.sort_values(["created_at", "is_primary"], ascending=[False, True])
          .drop_duplicates("company_id", keep="first")
    )



OPORTUNITY_FIEL = {

   "opportunity_id": "_id", 
   "company_id" : "company_id",
   "pipeline_stage": "pipeline_stage",
   "status": "status", 
   "value_cents": "value_cents"

}

OPORTUNITY_PROJECTION = {p: 1 for p in OPORTUNITY_FIEL.values()}


def flatten_oportunity(doc: dict) -> dict:
    row = {name: get_path(doc, path) for name, path in OPORTUNITY_FIEL.items()}
    row["opportunity_id"] = str(row["opportunity_id"])
    row["company_id"] = str(row["company_id"]) if row["company_id"] else None
    
    return row




class Mongo:

    def __init__(self, usuario: str, password: str, cluster: str) -> None:
        self.user = usuario
        self.passw = password
        self.cluster = cluster

    def companies(self, name: str | None, query: dict | None = None) -> pd.DataFrame:
        client = MongoClient(f"mongodb+srv://{self.user}:{self.passw}@{self.cluster}/")
        db = client["jobbi_crm"]

        query = query or {"outreach_status": {"$in": ["contacted", "replied", "promoted"]}}
        docs = db.prospect_companies.find(query, COMPANY_PROJECTION)

        df = pd.DataFrame([flatten_company(d) for d in docs])
        if df.empty:
            return df
        df = coerce_company_types(df)

      #  save_dataframe_json(df=df, filename=name)
        return df

    def users(self, name: str, query: dict | None = None) -> pd.DataFrame:
         
         client = MongoClient(f"mongodb+srv://{self.user}:{self.passw}@{self.cluster}/")
         db = client["jobbi_crm"]

         if query is None:
          query = {}
         docs = db["prospect_contacts"].find(query, USER_PROJECTION)

         df = pd.DataFrame([flatten_user(d) for d in docs])
         if df.empty:
          return df
    
         df = first_user_per_company(coerce_user_types(df))

        # save_dataframe_json(df=df, filename=name)
         return df


    def oportunity(self, name: str, query: dict | None = None) -> pd.DataFrame:
             
             client = MongoClient(f"mongodb+srv://{self.user}:{self.passw}@{self.cluster}/")
             db = client["jobbi_crm"]
    
             if query is None:
              query = {}
             docs = db["opportunities"].find(query, OPORTUNITY_PROJECTION)
    
             df = pd.DataFrame([flatten_oportunity(d) for d in docs])
             if df.empty:
              return df
        
            # save_dataframe_json(df=df, filename=name)
             return df