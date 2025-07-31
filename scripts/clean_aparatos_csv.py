# scripts\clean_aparatos_csv.py

import csv

INPUT_FILE = 'aparatos_original.csv'  # Cambia por el nombre de tu archivo original
OUTPUT_FILE = 'aparatos_clean.csv'    # El archivo limpio que genera

def limpiar_csv(input_file, output_file):
    with open(input_file, mode='r', encoding='utf-8') as infile, \
         open(output_file, mode='w', encoding='utf-8', newline='') as outfile:

        reader = csv.DictReader(infile, delimiter=';')
        campos_salida = [campo for campo in reader.fieldnames if campo != 'id']
        writer = csv.DictWriter(outfile, fieldnames=campos_salida, delimiter=';')
        writer.writeheader()

        for row in reader:
            row_salida = {campo: row[campo].replace('"','') for campo in campos_salida}
            writer.writerow(row_salida)

    print(f"✅ CSV limpio generado: {output_file}")

if __name__ == '__main__':
    limpiar_csv(INPUT_FILE, OUTPUT_FILE)
