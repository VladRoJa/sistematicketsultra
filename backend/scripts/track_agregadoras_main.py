#   backend\scripts\track_agregadoras_main.py


# backend/scripts/track_agregadoras_main.py

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd


WELLHUB_BRANCH_TO_TRACK_CANON = {
    "ULTRA - VILLAS DEL REY": "VILLAS_DEL_REY",
    "ULTRA - VILLA VERDE": "VILLA_VERDE",
    "ULTRA - INDEPENDENCIA": "INDEPENDENCIA",
    "ULTRA - TECNOLOGICO": "TEC_MXL",
    "ULTRA - SENDERO MEXICALI": "SEND_MXL",
    "ULTRA - SAN LUIS RIO COLORADO": "SAN_LUIS",
    "ULTRA - PABELLON ROSARITO": "PABELLON_RTO",
    "ULTRA - MISION ENSENADA": "MISION_ENS",
    "ULTRA - PASEO 2000": "PASEO_2000",
    "ULTRA - LOMA BONITA": "LOMA_BONITA",
    "ULTRA - SANTA FE": "SANTA_FE",
    "ULTRA - CARROUSEL": "CARROUSEL_TJ",
    "ULTRA - PAPALOTE": "PAPALOTE_TJ",
    "ULTRA - SENDERO CULIACAN": "SEND_CUL",
    "ULTRA - PASEO SAN ISIDRO": "SAN_ISIDRO_CUL",
    "ULTRA - PASEO AZAHARES": "AZAHARES_CUL",
    "ULTRA - SENDERO SANTA CATARINA": "STA_CATARINA",
    "ULTRA - SENDERO SALTILLO": "SEND_SALTILLO",
    "ULTRA - SENDERO CHIHUAHUA": "SEND_CHIH",
    "ULTRA - PASEO LA PAZ": "PASEO_LA_PAZ",
    "ULTRA - SENDERO IXTAPALUCA": "IXTAPALUCA",
    "ULTRA - INSURGENTES SUR": "INSURGENTES",
    "ULTRA - TLALNEPANTLA": "TLALNEPANTLA",
    "ULTRA - METEPEC": "METEPEC",
    "ULTRA SALTILLO VILLALTA": "SALTILLO_VILLALTA",
}

TOTALPASS_BRANCH_TO_TRACK_CANON = {
    "ULTRAGYM CARROUSEL": "CARROUSEL_TJ",
    "ULTRAGYM INDEPENDENCIA": "INDEPENDENCIA",
    "ULTRAGYM LOMA BONITA": "LOMA_BONITA",
    "ULTRAGYM PAPALOTE": "PAPALOTE_TJ",
    "ULTRAGYM VILLAS DEL REY": "VILLAS_DEL_REY",
    "ULTRAGYM VILLAS VERDE": "VILLA_VERDE",
    "ULTRAGYM TECNOLOGICO": "TEC_MXL",
    "ULTRAGYM SENDERO MEXICALI": "SEND_MXL",
    "ULTRAGYM SAN LUIS RIO COLORADO": "SAN_LUIS",
    "ULTRAGYM PABELLON ROSARITO": "PABELLON_RTO",
    "ULTRAGYM MISION ENSENADA": "MISION_ENS",
    "ULTRAGYM PASEO 2000": "PASEO_2000",
    "ULTRAGYM SANTA FE": "SANTA_FE",
    "ULTRAGYM SENDERO CULIACAN": "SEND_CUL",
    "ULTRAGYM PASEO SAN ISIDRO": "SAN_ISIDRO_CUL",
    "ULTRAGYM AZAHARES": "AZAHARES_CUL",
    "ULTRAGYM SENDERO SANTA CATARINA": "STA_CATARINA",
    "ULTRAGYM SALTILLO": "SEND_SALTILLO",
    "ULTRAGYM CHIHUAHUA": "SEND_CHIH",
    "ULTRAGYM LA PAZ": "PASEO_LA_PAZ",
    "ULTRA GYM IXTAPALUCA PLAZA SENDERO": "IXTAPALUCA",
    "ULTRAGYM INSURGENTES SUR": "INSURGENTES",
    "ULTRAGYM METEPEC": "METEPEC",
    "ULTRAGYM TLALNEPANTLA": "TLALNEPANTLA",
    "ULTRAGYM SALTILLO VILLALTA": "SALTILLO_VILLALTA",
}


def normalize_branch_text(raw_value: str | None) -> str:
    if not raw_value:
        return ""

    normalized = unicodedata.normalize("NFKD", str(raw_value))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.upper().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def normalize_agregadora_branch_to_track_canon(raw_branch: str) -> str | None:
    normalized = normalize_branch_text(raw_branch)

    if normalized in WELLHUB_BRANCH_TO_TRACK_CANON:
        return WELLHUB_BRANCH_TO_TRACK_CANON[normalized]

    if normalized in TOTALPASS_BRANCH_TO_TRACK_CANON:
        return TOTALPASS_BRANCH_TO_TRACK_CANON[normalized]

    return None


def parse_wellhub_checkins_excel(file_path: Path) -> pd.DataFrame:
    return pd.read_excel(file_path, sheet_name="Check-in details")


def parse_totalpass_resumen_excel(file_path: Path) -> pd.DataFrame:
    return pd.read_excel(file_path, sheet_name="Resumen del Grupo")


