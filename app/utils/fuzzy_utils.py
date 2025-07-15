# app\utils\fuzzy_utils.py

import unicodedata
import re
from rapidfuzz import fuzz

def normalizar_texto(texto):
    """Quita acentos, espacios, mayúsculas y caracteres especiales."""
    if not texto:
        return ""
    texto = texto.lower().strip()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )  # elimina acentos
    texto = re.sub(r'[^a-z0-9]', '', texto)  # solo letras/números
    return texto

def buscar_similares(candidato, lista_existentes, umbral=85):
    """
    Busca nombres similares usando RapidFuzz. 
    Regresa lista de coincidencias con score >= umbral.
    """
    candidato_norm = normalizar_texto(candidato)
    similares = []
    for existente in lista_existentes:
        existente_norm = normalizar_texto(existente)
        score = fuzz.ratio(candidato_norm, existente_norm)
        if score >= umbral:
            similares.append({'nombre': existente, 'score': score})
    return similares
