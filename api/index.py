import os
import sys
import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: Configura SUPABASE_URL y SUPABASE_SERVICE_KEY en las variables de entorno", file=sys.stderr)

T_INGS = 'ingredient_table'
T_RECIPES = 'recipe_table'
T_RECIPE_INGS = 'recipe_ingredients_table'


def get_api_config():
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_SERVICE_KEY')
    if not url or not key:
        return None, None, 'Credenciales de Supabase no configuradas. Agrega SUPABASE_URL y SUPABASE_SERVICE_KEY en las variables de entorno de Vercel.'
    api_url = url.rstrip('/') + '/rest/v1'
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
    }
    return api_url, headers, None


def api_req(method, table, data=None, params=None, extra_headers=None):
    api_url, headers, err = get_api_config()
    if err:
        return type('Response', (), {'status_code': 500, 'json': lambda: {'error': err}, 'text': err})()
    h = headers.copy()
    if extra_headers:
        h.update(extra_headers)
    url = f'{api_url}/{table}'
    r = requests.request(method, url, headers=h, json=data, params=params)
    return r


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/ingredients')
def ingredients_page():
    return render_template('ingredients.html')


@app.route('/recipes')
def recipes_page():
    return render_template('recipes.html')


@app.route('/shopping-list')
def shopping_list_page():
    return render_template('shopping_list.html')


@app.route('/analytics')
def analytics_page():
    return render_template('analytics.html')


@app.route('/api/ingredients', methods=['GET'])
def get_ingredients():
    r = api_req('GET', T_INGS)
    if r.status_code != 200:
        return jsonify({'error': r.text}), r.status_code
    return jsonify(r.json())


@app.route('/api/ingredients', methods=['POST'])
def add_ingredient():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': 'El nombre es obligatorio'}), 400
    r = api_req('POST', T_INGS, data=data,
                extra_headers={'Prefer': 'resolution=merge-duplicates'})
    if r.status_code not in (200, 201, 204):
        return jsonify({'error': r.text}), r.status_code
    return jsonify({'message': data['name'] + ' agregado/actualizado'})


@app.route('/api/ingredients/<name>', methods=['DELETE'])
def delete_ingredient(name):
    r = api_req('DELETE', T_INGS, params={'name': 'eq.' + name},
                extra_headers={'Prefer': 'return=representation'})
    if r.status_code == 200 and r.json():
        return jsonify({'message': name + ' eliminado'})
    return jsonify({'error': 'Ingrediente no encontrado'}), 404


@app.route('/api/recipes', methods=['GET'])
def get_recipes():
    r = api_req('GET', T_RECIPES)
    if r.status_code != 200:
        return jsonify({'error': r.text}), r.status_code
    recipes = r.json()
    for recipe in recipes:
        r2 = api_req('GET', T_RECIPE_INGS,
                     params={'recipe_id': 'eq.' + str(recipe['recipe_id']),
                             'select': 'ingredient_name,quantity_needed,measure'})
        recipe['ingredients'] = r2.json() if r2.status_code == 200 else []
    return jsonify(recipes)


@app.route('/api/recipes', methods=['POST'])
def add_recipe():
    data = request.get_json()
    if not data or not data.get('recipe_name'):
        return jsonify({'error': 'El nombre de la receta es obligatorio'}), 400

    r = api_req('POST', T_RECIPES,
                data={'recipe_name': data['recipe_name'],
                      'instructions': data.get('instructions', '')},
                extra_headers={'Prefer': 'return=representation'})
    if r.status_code == 409:
        return jsonify({'error': 'La receta ya existe'}), 409
    if r.status_code != 201:
        return jsonify({'error': r.text}), r.status_code

    recipe = r.json()[0]
    recipeId = recipe['recipe_id']

    for ing in data.get('ingredients', []):
        api_req('POST', T_RECIPE_INGS, data={
            'recipe_id': recipeId,
            'ingredient_name': ing['ingredient_name'],
            'quantity_needed': ing['quantity_needed'],
            'measure': ing['measure'],
        })

    return jsonify({'message': 'Receta agregada', 'recipe_id': recipeId})


@app.route('/api/recipes/<name>', methods=['DELETE'])
def delete_recipe(name):
    r = api_req('DELETE', T_RECIPES, params={'recipe_name': 'eq.' + name},
                extra_headers={'Prefer': 'return=representation'})
    if r.status_code == 200 and r.json():
        return jsonify({'message': name + ' eliminada'})
    return jsonify({'error': 'Receta no encontrada'}), 404


@app.route('/api/recipes/<int:recipe_id>/check', methods=['GET'])
def check_recipe(recipe_id):
    r = api_req('GET', T_RECIPES, params={'recipe_id': 'eq.' + str(recipe_id)})
    recipeData = r.json()
    if not recipeData:
        return jsonify({'error': 'Receta no encontrada'}), 404

    recipe = recipeData[0]
    r2 = api_req('GET', T_RECIPE_INGS,
                 params={'recipe_id': 'eq.' + str(recipe_id),
                         'select': 'ingredient_name,quantity_needed,measure,ingredient_table(count,cost)'})
    ingredients = r2.json()

    totalCost = 0.0
    missingCost = 0.0
    shoppingList = []
    allAvailable = True
    details = []

    for item in ingredients:
        qtyNeeded = item['quantity_needed']
        measure = item['measure']
        stock = item['ingredient_table']['count']
        cost = item['ingredient_table']['cost']

        missing = max(0.0, qtyNeeded - stock)
        ingCost = qtyNeeded * cost
        ingMissingCost = missing * cost
        totalCost += ingCost
        missingCost += ingMissingCost

        details.append({
            'name': item['ingredient_name'],
            'needed': qtyNeeded,
            'measure': measure,
            'have': stock,
            'missing': missing,
            'cost': ingCost,
        })

        if missing > 0:
            allAvailable = False
            shoppingList.append({
                'name': item['ingredient_name'],
                'qty': missing,
                'measure': measure,
                'cost': ingMissingCost,
            })

    return jsonify({
        'recipe_name': recipe['recipe_name'],
        'instructions': recipe['instructions'],
        'details': details,
        'total_cost': totalCost,
        'missing_cost': missingCost,
        'shopping_list': shoppingList,
        'all_available': allAvailable,
    })


@app.route('/api/shopping-list', methods=['GET'])
def global_shopping_list():
    r = api_req('GET', T_RECIPES)
    recipes = r.json() if r.status_code == 200 else []
    allMissing = {}

    for recipe in recipes:
        rid = recipe['recipe_id']
        r2 = api_req('GET', T_RECIPE_INGS,
                     params={'recipe_id': 'eq.' + str(rid),
                             'select': 'ingredient_name,quantity_needed,measure,ingredient_table(count,cost)'})
        for item in r2.json():
            name = item['ingredient_name']
            needed = item['quantity_needed']
            measure = item['measure']
            stock = item['ingredient_table']['count']
            cost = item['ingredient_table']['cost']
            missing = max(0.0, needed - stock)

            if missing > 0:
                if name not in allMissing:
                    allMissing[name] = {'qty': 0, 'measure': measure, 'cost': cost}
                allMissing[name]['qty'] += missing

    shoppingList = [{'name': k, 'qty': round(v['qty'], 2), 'measure': v['measure'], 'cost': v['cost']}
                    for k, v in allMissing.items()]
    totalCost = sum(s['qty'] * s['cost'] for s in shoppingList)
    return jsonify({'shopping_list': shoppingList, 'total_cost': round(totalCost, 2)})


@app.route('/api/recipes/<int:recipe_id>', methods=['PUT'])
def update_recipe(recipe_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Datos requeridos'}), 400

    if 'recipe_name' in data or 'instructions' in data:
        updateData = {}
        if 'recipe_name' in data:
            updateData['recipe_name'] = data['recipe_name']
        if 'instructions' in data:
            updateData['instructions'] = data['instructions']
        r = api_req('PATCH', T_RECIPES, data=updateData,
                    params={'recipe_id': 'eq.' + str(recipe_id)})
        if r.status_code not in (200, 204):
            return jsonify({'error': r.text}), r.status_code

    if 'ingredients' in data:
        api_req('DELETE', T_RECIPE_INGS, params={'recipe_id': 'eq.' + str(recipe_id)})
        for ing in data['ingredients']:
            api_req('POST', T_RECIPE_INGS, data={
                'recipe_id': recipe_id,
                'ingredient_name': ing['ingredient_name'],
                'quantity_needed': ing['quantity_needed'],
                'measure': ing['measure'],
            })

    return jsonify({'message': 'Receta actualizada'})


@app.route('/api/ingredients/export', methods=['GET'])
def export_ingredients():
    r = api_req('GET', T_INGS)
    if r.status_code != 200:
        return jsonify({'error': r.text}), r.status_code
    data = r.json()
    csv = 'Nombre,Unidad,Cantidad,Costo/Unidad,Valor Total\n'
    for ing in data:
        total = parseFloat(ing['count']) * parseFloat(ing['cost'])
        csv += f"{ing['name']},{ing['measure']},{ing['count']},{ing['cost']},{total}\n"
    return csv, 200, {'Content-Type': 'text/csv', 'Content-Disposition': 'attachment; filename=inventario.csv'}


@app.route('/api/analytics', methods=['GET'])
def analytics():
    ings = api_req('GET', T_INGS)
    ingredients = ings.json() if ings.status_code == 200 else []

    value = 0.0
    lowCount = 0
    outCount = 0
    okCount = 0
    ingValues = []

    for ing in ingredients:
        c = parseFloat(ing['count'])
        cost = parseFloat(ing['cost'])
        total = c * cost
        value += total
        if c <= 0:
            outCount += 1
        elif c < 5:
            lowCount += 1
        else:
            okCount += 1
        ingValues.append({'name': ing['name'], 'value': round(total, 2),
                          'count': c, 'measure': ing['measure']})

    ingValues.sort(key=lambda x: x['value'], reverse=True)

    recs = api_req('GET', T_RECIPES)
    recipes = recs.json() if recs.status_code == 200 else []

    recipeCosts = []
    for recipe in recipes:
        r2 = api_req('GET', T_RECIPE_INGS,
                     params={'recipe_id': 'eq.' + str(recipe['recipe_id']),
                             'select': 'ingredient_name,quantity_needed,measure,ingredient_table(count,cost)'})
        items = r2.json()
        costTotal = sum(item['quantity_needed'] * item['ingredient_table']['cost'] for item in items)
        recipeCosts.append({
            'recipe_id': recipe['recipe_id'],
            'recipe_name': recipe['recipe_name'],
            'cost': round(costTotal, 2),
            'ingredient_count': len(items),
        })

    recipeCosts.sort(key=lambda x: x['cost'], reverse=True)

    return jsonify({
        'ingredient_count': len(ingredients),
        'recipe_count': len(recipes),
        'total_inventory_value': round(value, 2),
        'health': {
            'ok': okCount,
            'low': lowCount,
            'out': outCount,
        },
        'top_ingredients_by_value': ingValues[:10],
        'recipe_costs': recipeCosts,
    })


def parseFloat(v):
    try:
        return float(v)
    except:
        return 0.0
