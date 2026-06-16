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
    print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set", file=sys.stderr)

T_INGS = 'ingredient_table'
T_RECIPES = 'recipe_table'
T_RECIPE_INGS = 'recipe_ingredients_table'


def get_api_config():
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_SERVICE_KEY')
    if not url or not key:
        return None, None, 'Supabase credentials not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY in Vercel env vars.'
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
        return jsonify({'error': 'Name is required'}), 400
    r = api_req('POST', T_INGS, data=data,
                extra_headers={'Prefer': 'resolution=merge-duplicates'})
    if r.status_code not in (200, 201, 204):
        return jsonify({'error': r.text}), r.status_code
    return jsonify({'message': data['name'] + ' added/updated'})


@app.route('/api/ingredients/<name>', methods=['DELETE'])
def delete_ingredient(name):
    r = api_req('DELETE', T_INGS, params={'name': 'eq.' + name},
                extra_headers={'Prefer': 'return=representation'})
    if r.status_code == 200 and r.json():
        return jsonify({'message': name + ' removed'})
    return jsonify({'error': 'Not found'}), 404


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
        return jsonify({'error': 'Recipe name is required'}), 400

    r = api_req('POST', T_RECIPES,
                data={'recipe_name': data['recipe_name'],
                      'instructions': data.get('instructions', '')},
                extra_headers={'Prefer': 'return=representation'})
    if r.status_code == 409:
        return jsonify({'error': 'Recipe already exists'}), 409
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

    return jsonify({'message': 'Recipe added', 'recipe_id': recipeId})


@app.route('/api/recipes/<name>', methods=['DELETE'])
def delete_recipe(name):
    r = api_req('DELETE', T_RECIPES, params={'recipe_name': 'eq.' + name},
                extra_headers={'Prefer': 'return=representation'})
    if r.status_code == 200 and r.json():
        return jsonify({'message': name + ' removed'})
    return jsonify({'error': 'Not found'}), 404


@app.route('/api/recipes/<int:recipe_id>/check', methods=['GET'])
def check_recipe(recipe_id):
    r = api_req('GET', T_RECIPES, params={'recipe_id': 'eq.' + str(recipe_id)})
    recipeData = r.json()
    if not recipeData:
        return jsonify({'error': 'Recipe not found'}), 404

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
