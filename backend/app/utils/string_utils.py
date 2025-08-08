#app\utils\string_utils.py


import re

def normalizar_campo(texto):
    if not texto:
        return ""
    texto = re.sub(r'[^\w\sáéíóúÁÉÍÓÚñÑ.,-]', '', texto) # permite letras, números, algunos signos
    texto = re.sub(r'\s+', ' ', texto) # quita espacios dobles
    texto = texto.strip()
    return texto[:1].upper() + texto[1:].lower() if texto else ""
