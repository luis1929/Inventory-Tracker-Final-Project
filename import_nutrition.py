#!/usr/bin/env python3
"""
Import nutrition data into Supabase nutrition_table.
Usage: python3 import_nutrition.py

Data format: TSV with comma as decimal separator.
Columns: CLASIFICACION	PRODUCTO	Cantidad (g)	Calorias USDA	Proteina (g)	Grasa (g)	Carbohidrato (g)	Fibra (g)	Sodio (mg)	Calorias Proteina	Calorias Grasa	Calorias Carbohidratos	Total Calorias	Total Calorias Sin Fibra
"""

import os
import sys
import json
import csv
import io
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL', '').rstrip('/') + '/rest/v1'
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_KEY')

if not SUPABASE_KEY:
    print("ERROR: SUPABASE_SERVICE_KEY not found in .env")
    sys.exit(1)

HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'resolution=merge-duplicates',
}

TABLE = 'nutrition_table'

def parse_decimal(val):
    """Parse Colombian-format number (comma as decimal, spaces stripped)"""
    if val is None:
        return 0
    val = str(val).strip().replace(' ', '')
    if not val:
        return 0
    val = val.replace(',', '.')
    try:
        return float(val)
    except ValueError:
        return 0

def parse_tsv_data(content):
    """Parse TSV content with Colombian format"""
    reader = csv.DictReader(io.StringIO(content), delimiter='\t')
    records = []
    for row in reader:
        product = row.get('PRODUCTO', '').strip()
        if not product:
            continue
        rec = {
            'ingredient_name': product,
            'classification': row.get('CLASIFICACION', '').strip(),
            'calories_usda': parse_decimal(row.get('Calorias USDA', 0)),
            'protein_g': parse_decimal(row.get('Proteina (g)', 0)),
            'fat_g': parse_decimal(row.get('Grasa (g)', 0)),
            'carbs_g': parse_decimal(row.get('Carbohidrato (g)', 0)),
            'fiber_g': parse_decimal(row.get('Fibra (g)', 0)),
            'sodium_mg': parse_decimal(row.get('Sodio (mg)', 0)),
            'calories_protein': parse_decimal(row.get('Calorias Proteina', 0)),
            'calories_fat': parse_decimal(row.get('Calorias Grasa', 0)),
            'calories_carbs': parse_decimal(row.get('Calorias Carbohidratos', 0)),
            'total_calories': parse_decimal(row.get('Total Calorias', 0)),
            'total_calories_no_fiber': parse_decimal(row.get('Total Calorias Sin Fibra', 0)),
        }
        records.append(rec)
    return records

# ── Sample data from user ──
SAMPLE_TSV = """CLASIFICACION	PRODUCTO	Cantidad (g)	Calorias USDA	Proteina (g)	Grasa (g)	Carbohidrato (g)	Fibra (g)	Sodio (mg)	Calorias Proteina	Calorias Grasa	Calorias Carbohidratos	Total Calorias	Total Calorias Sin Fibra
ADEREZOS/CONDIMENTOS/ESPECIAS	AJI PICANTE 	 100,0 	12	1,29	0,76	0,8	0,6	633	5,16	6,84	3,2	15,2	14
ADEREZOS/CONDIMENTOS/ESPECIAS	ALBAHACA FRESCA	 100,0 	23,0	3,2	0,6	2,7	1,6	4,0	12,6	5,8	10,6	29,0	25,8
ADEREZOS/CONDIMENTOS/ESPECIAS	CANELA MOLIDA	 100,0 	247,0	4,0	1,2	80,6		10,0	16,0	11,2	322,4	349,5	349,5
ADEREZOS/CONDIMENTOS/ESPECIAS	COLOR (AZAFRAN)	 100,0 	310,0	11,4	5,9	65,4	3,9	148,0	45,6	52,7	261,6	359,9	352,1
ADEREZOS/CONDIMENTOS/ESPECIAS	CREMA DE COCO EN LATA KARI	 100,0 	169,0	1,6	17,0	2,1	0,0	23,0	6,4	153,0	8,4	167,8	167,8
ADEREZOS/CONDIMENTOS/ESPECIAS	CURCUMA	 100,0 	312,0	9,7	3,3	67,1	22,7	27,0	38,7	29,3	268,4	336,4	291,0
"""

def import_records(records):
    """POST records to Supabase in batches"""
    batch_size = 50
    total = len(records)
    for i in range(0, total, batch_size):
        batch = records[i:i + batch_size]
        url = f'{SUPABASE_URL}/{TABLE}'
        r = requests.post(url, headers=HEADERS, json=batch)
        if r.status_code in (200, 201):
            print(f'  OK ({i+1}-{min(i+batch_size, total)}/{total})')
        else:
            print(f'  ERROR ({i+1}-{min(i+batch_size, total)}/{total}): {r.status_code} {r.text[:200]}')

def main():
    # Check if file argument provided
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            content = f.read()
        print(f'Reading from file: {sys.argv[1]}')
    else:
        print('No file specified, using embedded sample data.')
        print('Usage: python3 import_nutrition.py <tsv_file>')
        content = SAMPLE_TSV

    records = parse_tsv_data(content)
    print(f'Parsed {len(records)} records')

    # Preview first 3
    for r in records[:3]:
        print(f'  - {r["ingredient_name"]}: {r["total_calories"]} cal, {r["protein_g"]}g protein')

    confirm = input(f'\nImport {len(records)} records to Supabase? (y/N): ')
    if confirm.lower() == 'y':
        import_records(records)
        print('Done!')
    else:
        print('Cancelled.')

if __name__ == '__main__':
    main()
