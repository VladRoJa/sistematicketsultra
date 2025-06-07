import csv
from werkzeug.security import generate_password_hash

# 🔧 Cambia este nombre si tu archivo tiene otro nombre:
input_file = 'users_original.csv'
output_file = 'users_hashed.csv'

# Leer el CSV original
with open(input_file, mode='r', encoding='utf-8-sig') as infile, open(output_file, mode='w', newline='', encoding='utf-8-sig') as outfile:
    reader = csv.DictReader(infile, delimiter=';')
    fieldnames = reader.fieldnames
    writer = csv.DictWriter(outfile, fieldnames=fieldnames, delimiter=';')
    
    writer.writeheader()
    
    for row in reader:
        raw_password = row['password']
        hashed_password = generate_password_hash(raw_password)
        row['password'] = hashed_password
        writer.writerow(row)

print("✅ CSV generado correctamente: users_hashed.csv")
