from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_READERS = {
    ".csv": pd.read_csv,
    ".xml": pd.read_xml,
    ".xlsx": pd.read_excel,
    ".xlsm": pd.read_excel,
}


def load_dataframe(filename: str, folder: str = "Data", subfolder: str = "csv", **read_kwargs) -> pd.DataFrame:
    """Carga un archivo (csv, xml, xlsx o xlsm) de una carpeta del proyecto a un DataFrame.

    `folder` es relativo a la raiz del proyecto (ej. "Leads"). `read_kwargs` se
    pasan tal cual al reader de pandas correspondiente (read_csv/read_xml/read_excel).
    """
    path = PROJECT_ROOT / folder / subfolder / filename
    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo: {path}")

    reader = _READERS.get(path.suffix.lower())
    if reader is None:
        raise ValueError(f"Formato no soportado: {path.suffix} (usa csv, xml, xlsx o xlsm)")

    return reader(path, **read_kwargs)


def save_dataframe_csv(df: pd.DataFrame, filename: str, subfolder: str = "csv", folder: str = "Data", **to_csv_kwargs) -> Path:
    """Guarda un DataFrame como CSV en una carpeta del proyecto, creandola si no existe.

    `folder` es relativo a la raiz del proyecto. Por default no incluye el indice;
    se puede sobreescribir via to_csv_kwargs.
    """
    out_dir = PROJECT_ROOT / folder / subfolder
    out_dir.mkdir(parents=True, exist_ok=True)

    path = out_dir / filename
    to_csv_kwargs.setdefault("index", False)
    df.to_csv(path, **to_csv_kwargs)
    return path


def save_dataframe_json(df: pd.DataFrame, filename: str, subfolder: str = "df_json", folder: str = "Data", **to_json_kwargs) -> Path:
    """Guarda un DataFrame como JSON en una carpeta del proyecto, creandola si no existe.

    `folder` es relativo a la raiz del proyecto. Por default usa orient="records"
    e indentado legible; se puede sobreescribir via to_json_kwargs.
    """
    out_dir = PROJECT_ROOT / folder / subfolder 
    out_dir.mkdir(parents=True, exist_ok=True)

    def _limpiar_recursivo(obj):
        if isinstance(obj, str):
            return obj.encode('utf-8', errors='replace').decode('utf-8')
        elif isinstance(obj, dict):
            return {k: _limpiar_recursivo(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_limpiar_recursivo(v) for v in obj]
        return obj

    df = df.map(_limpiar_recursivo)

    path = out_dir / filename
    to_json_kwargs.setdefault("orient", "records")
    to_json_kwargs.setdefault("indent", 2)
    to_json_kwargs.setdefault("force_ascii", False)
    df.to_json(path, **to_json_kwargs)
    return path
