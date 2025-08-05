import csv
from werkzeug.security import generate_password_hash

input_file = 'users_original.csv'
output_file = 'users_hashed.csv'

with open(input_file, mode='r', encoding='utf-8-sig') as infile, \
     open(output_file, mode='w', newline='', encoding='utf-8-sig') as outfile:
    
    # Detectar delimitador automáticamente
    dialect = csv.Sniffer().sniff(infile.read(1024))
    infile.seek(0)

    reader = csv.DictReader(infile, dialect=dialect)
    fieldnames = reader.fieldnames
    print("🔍 Encabezados detectados:", fieldnames)

    # Detectar columna de password
    password_column = None
    for col in fieldnames:
        if 'pass' in col.lower() or 'contraseña' in col.lower() or 'clave' in col.lower():
            password_column = col
            break

    if not password_column:
        raise ValueError("❌ No se encontró ninguna columna que parezca contener contraseñas.")

    print(f"✅ Columna de contraseña detectada: {password_column}")

    writer = csv.DictWriter(outfile, fieldnames=fieldnames, dialect=dialect)
    writer.writeheader()

    for row in reader:
        raw_password = row[password_column]
        hashed_password = generate_password_hash(raw_password)
        row[password_column] = hashed_password
        writer.writerow(row)

print(f"✅ CSV generado correctamente: {output_file}")
