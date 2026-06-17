import os
import sys
import json
import uuid
import requests
from urllib.parse import quote
from datetime import timedelta
from functools import wraps
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, session, redirect

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))
app.secret_key = os.getenv('FLASK_SECRET', os.urandom(32).hex())
app.permanent_session_lifetime = timedelta(days=7)

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_KEY')
SUPABASE_ANON = os.getenv('SUPABASE_ANON_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: Configura SUPABASE_URL y SUPABASE_SERVICE_KEY en las variables de entorno", file=sys.stderr)

ADMIN_EMAILS = set()
admin_emails_env = os.getenv('ADMIN_EMAILS', '')
if admin_emails_env:
    ADMIN_EMAILS = set(e.strip().lower() for e in admin_emails_env.split(',') if e.strip())

T_INGS = 'ingredient_table'
T_RECIPES = 'recipe_table'
T_RECIPE_INGS = 'recipe_ingredients_table'
T_USERS = 'user_profiles'
T_MENU = 'menu_board'
T_MENU_RECIPE = 'menu_recipe_items'
T_NUTRITION = 'nutrition_table'
T_SALES = 'daily_sales'
T_SALE_ITEMS = 'sale_items'


def get_api_config():
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_SERVICE_KEY')
    if not url or not key:
        return None, None, 'Credenciales de Supabase no configuradas'
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


def auth_req(method, path, data=None, token=None):
    if not SUPABASE_URL:
        return type('Response', (), {'status_code': 500, 'json': lambda: {'error': 'No configurado'}, 'text': ''})()
    url = SUPABASE_URL.rstrip('/') + '/auth/v1/' + path.lstrip('/')
    headers = {
        'apikey': SUPABASE_ANON or '',
        'Content-Type': 'application/json',
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'
    r = requests.request(method, url, headers=headers, json=data)
    return r


def _ensure_demo_session():
    if 'user' not in session:
        session.permanent = True
        session['user'] = {
            'id': '00000000-0000-0000-0000-000000000000',
            'email': 'demo@kitchenmaster.app',
            'token': '',
        }


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        _ensure_demo_session()
        return f(*args, **kwargs)
    return decorated


def api_auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        _ensure_demo_session()
        return f(*args, **kwargs)
    return decorated


def is_admin(email):
    if not email:
        return False
    email = email.lower()
    if email in ADMIN_EMAILS:
        return True
    r = api_req('GET', T_USERS, params={'email': 'eq.' + email, 'select': 'role'})
    if r.status_code == 200:
        profiles = r.json()
        if profiles and profiles[0].get('role') == 'admin':
            return True
    return False


def sync_user_profile(user_id, email):
    role = 'admin' if email.lower() in ADMIN_EMAILS else 'user'
    api_req('POST', T_USERS,
            data={'id': user_id, 'email': email, 'role': role},
            extra_headers={'Prefer': 'resolution=merge-duplicates'})


@app.context_processor
def inject_admin():
    user = session.get('user', {})
    return {'is_admin': is_admin(user.get('email', ''))}


# ── Auth Routes ──

@app.route('/login')
def login_page():
    return redirect('/')


@app.route('/register')
def register_page():
    return redirect('/')


@app.route('/api/auth/signup', methods=['POST'])
def auth_signup():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Email y contraseña requeridos'}), 400
    if len(data['password']) < 6:
        return jsonify({'error': 'La contraseña debe tener al menos 6 caracteres'}), 400

    r = auth_req('POST', 'signup', data={
        'email': data['email'],
        'password': data['password'],
    })
    body = r.json()
    if r.status_code not in (200, 201, 204):
        return jsonify({'error': body.get('msg') or body.get('error_description') or body.get('message') or 'Error al registrar'}), r.status_code

    if body.get('user') and body.get('access_token'):
        session.permanent = True
        session['user'] = {
            'id': body['user']['id'],
            'email': body['user']['email'],
            'token': body['access_token'],
        }
        sync_user_profile(body['user']['id'], body['user']['email'])
        return jsonify({'message': 'Cuenta creada', 'user': {'email': body['user']['email']}})

    return jsonify({'message': 'Revisa tu email para confirmar la cuenta. Por ahora, usa el modo demo.', 'confirmation_sent': True})


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Email y contraseña requeridos'}), 400

    r = auth_req('POST', 'token?grant_type=password', data={
        'email': data['email'],
        'password': data['password'],
    })
    body = r.json()
    if r.status_code not in (200, 201):
        return jsonify({'error': body.get('error_description') or body.get('msg') or body.get('message') or 'Credenciales inválidas'}), 401

    session.permanent = True
    session['user'] = {
        'id': body['user']['id'],
        'email': body['user']['email'],
        'token': body['access_token'],
    }
    sync_user_profile(body['user']['id'], body['user']['email'])
    return jsonify({'message': 'Inicio de sesión exitoso', 'user': {'email': body['user']['email']}})


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    token = None
    if 'user' in session:
        token = session['user'].get('token')
    session.clear()
    if token:
        try:
            auth_req('POST', 'logout', token=token)
        except:
            pass
    return jsonify({'message': 'Sesión cerrada'})


@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    if 'user' not in session:
        return jsonify({'user': None})
    return jsonify({'user': {'email': session['user']['email'], 'id': session['user']['id']}})


@app.route('/forgot-password')
def forgot_password_page():
    return render_template('forgot_password.html')


@app.route('/reset-password')
def reset_password_page():
    return render_template('reset_password.html')


@app.route('/api/auth/recover', methods=['POST'])
def auth_recover():
    data = request.get_json()
    if not data or not data.get('email'):
        return jsonify({'error': 'Email requerido'}), 400

    site_url = request.host_url.rstrip('/')
    r = auth_req('POST', 'recover', data={'email': data['email'], 'redirect_to': site_url + '/reset-password'})
    body = r.json()
    if r.status_code not in (200, 201, 204):
        return jsonify({'error': body.get('msg') or body.get('error_description') or 'Error al enviar email'}), r.status_code

    return jsonify({'message': 'Revisa tu email. Recibirás un enlace para restablecer tu contraseña.'})


@app.route('/api/auth/update-password', methods=['PUT'])
def auth_update_password():
    data = request.get_json()
    if not data or not data.get('password'):
        return jsonify({'error': 'Nueva contraseña requerida'}), 400
    if len(data['password']) < 6:
        return jsonify({'error': 'Mínimo 6 caracteres'}), 400

    token = data.get('token')
    h = {}
    if token:
        h['Authorization'] = f'Bearer {token}'

    r = requests.put(
        SUPABASE_URL.rstrip('/') + '/auth/v1/user',
        headers={
            'apikey': SUPABASE_ANON or '',
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
        json={'password': data['password']}
    )
    body = r.json()
    if r.status_code not in (200, 201, 204):
        return jsonify({'error': body.get('msg') or body.get('error_description') or 'Error al actualizar'}), r.status_code

    if 'user' in session:
        session.pop('user', None)
    return jsonify({'message': 'Contraseña actualizada. Inicia sesión con tu nueva contraseña.'})


# ── Protected Pages ──

@app.route('/')
def index():
    _ensure_demo_session()
    return render_template('index.html', user=session['user'])


@app.route('/ingredients')
@login_required
def ingredients_page():
    return render_template('ingredients.html', user=session['user'])


@app.route('/recipes')
@login_required
def recipes_page():
    return render_template('recipes.html', user=session['user'])


@app.route('/shopping-list')
@login_required
def shopping_list_page():
    return render_template('shopping_list.html', user=session['user'])


@app.route('/analytics')
@login_required
def analytics_page():
    return render_template('analytics.html', user=session['user'])


# ── Protected API ──

@app.route('/api/ingredients', methods=['GET'])
@api_auth_required
def get_ingredients():
    r = api_req('GET', T_INGS)
    if r.status_code != 200:
        return jsonify({'error': r.text}), r.status_code
    return jsonify(r.json())


@app.route('/api/ingredients', methods=['POST'])
@api_auth_required
def add_ingredient():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': 'El nombre es obligatorio'}), 400
    r = api_req('POST', T_INGS, data=data,
                extra_headers={'Prefer': 'resolution=merge-duplicates'})
    if r.status_code not in (200, 201, 204):
        return jsonify({'error': r.text}), r.status_code
    # Refresh suppliers file
    try:
        sr = api_req('GET', T_INGS, params={'select': 'supplier', 'supplier': 'not.is.null', 'order': 'supplier.asc'})
        if sr.status_code == 200:
            seen = set()
            suppliers = []
            for ing in sr.json():
                s = ing.get('supplier', '').strip()
                if s and s.lower() not in seen:
                    seen.add(s.lower())
                    suppliers.append(s)
            filepath = os.path.join(BASE_DIR, 'suppliers.json')
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(suppliers, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return jsonify({'message': data['name'] + ' agregado/actualizado'})


@app.route('/api/ingredients/delete', methods=['POST'])
@api_auth_required
def delete_ingredient_post():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': 'Nombre requerido'}), 400
    name = data['name']
    r = api_req('DELETE', T_INGS, params={'name': 'eq.' + name},
                extra_headers={'Prefer': 'return=representation'})
    if r.status_code == 200 and r.json():
        return jsonify({'message': name + ' eliminado'})
    return jsonify({'error': 'Ingrediente no encontrado'}), 404


@app.route('/api/ingredients/<name>', methods=['DELETE'])
@api_auth_required
def delete_ingredient(name):
    from urllib.parse import unquote
    name = unquote(name)
    r = api_req('DELETE', T_INGS, params={'name': 'eq.' + name},
                extra_headers={'Prefer': 'return=representation'})
    if r.status_code == 200 and r.json():
        return jsonify({'message': name + ' eliminado'})
    return jsonify({'error': 'Ingrediente no encontrado'}), 404


@app.route('/api/recipes', methods=['GET'])
@api_auth_required
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
@api_auth_required
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
@api_auth_required
def delete_recipe(name):
    r = api_req('DELETE', T_RECIPES, params={'recipe_name': 'eq.' + name},
                extra_headers={'Prefer': 'return=representation'})
    if r.status_code == 200 and r.json():
        return jsonify({'message': name + ' eliminada'})
    return jsonify({'error': 'Receta no encontrada'}), 404


@app.route('/api/recipes/<int:recipe_id>/check', methods=['GET'])
@api_auth_required
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
@api_auth_required
def global_shopping_list():
    # Get all inventory
    r = api_req('GET', T_INGS)
    ingredients = r.json() if r.status_code == 200 else []
    stock_map = {i['name']: i for i in ingredients}

    # Get all menu recipe items (ingredients across all dishes)
    rr = api_req('GET', T_MENU_RECIPE)
    all_items = rr.json() if rr.status_code == 200 else []

    needed = {}
    for item in all_items:
        name = item['ingredient_name']
        qty = float(item.get('quantity_grams', 0))
        if name not in needed:
            needed[name] = 0
        needed[name] += qty

    shoppingList = []
    totalCost = 0
    # Convert grams to appropriate measure for shopping
    for name, qty_needed in needed.items():
        ing = stock_map.get(name)
        if not ing:
            continue
        stock = float(ing.get('count', 0))
        missing = max(0, qty_needed - stock)
        if missing <= 0:
            continue

        measure = ing.get('measure', 'g')
        cost = float(ing.get('cost', 0))

        # Convert missing grams to display unit
        if measure == 'g':
            display_qty = round(missing, 0)
            display_measure = 'g'
        elif measure == 'kg':
            display_qty = round(missing / 1000, 2)
            display_measure = 'kg'
        elif measure == 'ml':
            display_qty = round(missing, 0)
            display_measure = 'ml'
        elif measure == 'l':
            display_qty = round(missing / 1000, 2)
            display_measure = 'l'
        elif measure == 'lb':
            display_qty = round(missing / 453.592, 2)
            display_measure = 'lb'
        else:
            display_qty = round(missing, 0)
            display_measure = measure

        item_cost = display_qty * cost
        totalCost += item_cost
        shoppingList.append({
            'name': name,
            'qty': display_qty,
            'measure': display_measure,
            'cost': cost,
            'supplier': ing.get('supplier', 'Sin proveedor'),
            'brand': ing.get('brand', ''),
            'presentation': ing.get('presentation', ''),
            'classification': ing.get('classification', ''),
        })

    shoppingList.sort(key=lambda x: x['name'])
    return jsonify({'shopping_list': shoppingList, 'total_cost': round(totalCost, 2)})


@app.route('/api/recipes/<int:recipe_id>', methods=['PUT'])
@api_auth_required
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
@api_auth_required
def export_ingredients():
    r = api_req('GET', T_INGS)
    if r.status_code != 200:
        return jsonify({'error': r.text}), r.status_code
    data = r.json()
    csv = 'Clasificacion,Producto,Marca,Proveedor,Presentacion,Unidad,Cantidad,Costo/Unidad,Valor Total,Observacion\n'
    for ing in data:
        total = parseFloat(ing['count']) * parseFloat(ing['cost'])
        csv += f"{ing.get('classification','')},{ing['name']},{ing.get('brand','')},{ing.get('supplier','')},{ing.get('presentation','')},{ing['measure']},{ing['count']},{ing['cost']},{total},{ing.get('notes','')}\n"
    return csv, 200, {'Content-Type': 'text/csv', 'Content-Disposition': 'attachment; filename=inventario.csv'}


@app.route('/api/analytics', methods=['GET'])
@api_auth_required
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

    dishes = api_req('GET', T_MENU)
    dish_list = dishes.json() if dishes.status_code == 200 else []

    recipeCosts = []
    if dish_list:
        dish_ids = [d['id'] for d in dish_list]
        id_filter = 'in.(' + ','.join(str(i) for i in dish_ids) + ')'
        rr = api_req('GET', T_MENU_RECIPE, params={'dish_id': id_filter})
        all_items = rr.json() if rr.status_code == 200 else []
        items_by_dish = {}
        for item in all_items:
            items_by_dish.setdefault(item['dish_id'], []).append(item)

        ing_names = set()
        for items in items_by_dish.values():
            for item in items:
                if not item.get('unit_cost'):
                    ing_names.add(item['ingredient_name'])
        ing_cost_map = {}
        if ing_names:
            name_filter = 'in.(' + ','.join(n.replace("'", "''") for n in ing_names) + ')'
            ri = api_req('GET', T_INGS, params={'name': name_filter, 'select': 'name,cost,measure'})
            if ri.status_code == 200:
                for ing in ri.json():
                    mult = _cost_multiplier(ing.get('measure', 'g'))
                    ing_cost_map[ing['name']] = float(ing['cost']) * mult

        for dish in dish_list:
            did = dish['id']
            items = items_by_dish.get(did, [])
            raw_total = 0.0
            for item in items:
                qty = float(item.get('quantity_grams', 0))
                if item.get('unit_cost') is not None and float(item.get('unit_cost', 0)) > 0:
                    unit_cost = float(item['unit_cost'])
                else:
                    unit_cost = ing_cost_map.get(item['ingredient_name'], 0)
                raw_total += qty * unit_cost
            raw_total = round(raw_total, 2)
            recipeCosts.append({
                'recipe_id': did,
                'recipe_name': dish.get('dish_name', 'Sin nombre'),
                'cost': raw_total,
                'ingredient_count': len(items),
            })

    recipeCosts.sort(key=lambda x: x['cost'], reverse=True)

    return jsonify({
        'ingredient_count': len(ingredients),
        'recipe_count': len(dish_list),
        'total_inventory_value': round(value, 2),
        'health': {
            'ok': okCount,
            'low': lowCount,
            'out': outCount,
        },
        'top_ingredients_by_value': ingValues[:10],
        'recipe_costs': recipeCosts,
    })


def _cost_multiplier(measure):
    m = (measure or '').lower().strip()
    if m in ('g', 'ml', 'u', 'unidad'):
        return 1.0
    if m in ('kg', 'l'):
        return 0.001
    if m == 'lb':
        return 0.00220462
    return 1.0

def _compute_dish_cost(dish_id):
    r = api_req('GET', T_MENU_RECIPE, params={'dish_id': 'eq.' + str(dish_id)})
    if r.status_code != 200:
        return 0, 0, [], {}
    items = r.json()
    raw_total = 0.0
    enriched = []

    # Collect ingredient names for batch nutrition fetch
    ing_names = list(set(it['ingredient_name'] for it in items))
    nutrition_map = {}
    if ing_names:
        nf = 'in.(' + ','.join(n.replace("'", "''") for n in ing_names) + ')'
        rn = api_req('GET', T_NUTRITION, params={'ingredient_name': nf})
        if rn.status_code == 200:
            for n in rn.json():
                nutrition_map[n['ingredient_name']] = n

    nut = {
        'protein_g': 0.0, 'fat_g': 0.0, 'carbs_g': 0.0,
        'fiber_g': 0.0, 'sodium_mg': 0.0, 'calories': 0.0,
    }

    for item in items:
        qty = float(item.get('quantity_grams', 0))
        if item.get('unit_cost') is not None and float(item.get('unit_cost', 0)) > 0:
            unit_cost = float(item['unit_cost'])
        else:
            r2 = api_req('GET', T_INGS, params={'name': 'eq.' + item['ingredient_name'], 'select': 'cost,measure'})
            ing_data = r2.json()
            if ing_data:
                cost = float(ing_data[0].get('cost', 0))
                measure = ing_data[0].get('measure', 'g')
                mult = _cost_multiplier(measure)
                unit_cost = cost * mult
            else:
                unit_cost = 0
        line_cost = qty * unit_cost
        raw_total += line_cost
        enriched.append({
            'id': item['id'],
            'dish_id': item['dish_id'],
            'ingredient_name': item['ingredient_name'],
            'quantity_grams': qty,
            'unit_cost': round(unit_cost, 4),
            'line_cost': round(line_cost, 2),
        })
        nd = nutrition_map.get(item['ingredient_name'])
        if nd:
            factor = qty / 100.0
            nut['protein_g'] += float(nd.get('protein_g', 0)) * factor
            nut['fat_g'] += float(nd.get('fat_g', 0)) * factor
            nut['carbs_g'] += float(nd.get('carbs_g', 0)) * factor
            nut['fiber_g'] += float(nd.get('fiber_g', 0)) * factor
            nut['sodium_mg'] += float(nd.get('sodium_mg', 0)) * factor
            nut['calories'] += float(nd.get('total_calories', 0)) * factor
    raw_total = round(raw_total, 2)

    # Get overhead from menu_board
    rd = api_req('GET', T_MENU, params={'id': 'eq.' + str(dish_id), 'select': 'overhead_cost'})
    overhead = 0
    if rd.status_code == 200 and rd.json():
        overhead = float(rd.json()[0].get('overhead_cost', 0))

    final_total = round(raw_total + overhead, 2)
    api_req('PATCH', T_MENU, data={'cost_total': final_total}, params={'id': 'eq.' + str(dish_id)})
    return raw_total, final_total, enriched, nut



@app.route('/api/suppliers', methods=['GET'])
@api_auth_required
def get_suppliers():
    r = api_req('GET', T_INGS, params={'select': 'supplier', 'supplier': 'not.is.null', 'order': 'supplier.asc'})
    if r.status_code != 200:
        return jsonify({'error': r.text}), r.status_code
    seen = set()
    suppliers = []
    for ing in r.json():
        s = ing.get('supplier', '').strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            suppliers.append(s)
    # Also save to file
    try:
        filepath = os.path.join(BASE_DIR, 'suppliers.json')
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(suppliers, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return jsonify(suppliers)


@app.route('/api/nutrition', methods=['GET'])
@api_auth_required
def get_nutrition():
    r = api_req('GET', T_NUTRITION, params={'order': 'ingredient_name.asc'})
    if r.status_code != 200:
        return jsonify({'error': r.text}), r.status_code
    return jsonify(r.json())


@app.route('/api/nutrition', methods=['POST'])
@api_auth_required
def upsert_nutrition():
    data = request.get_json()
    if not data or not isinstance(data, list):
        return jsonify({'error': 'Envia un array de registros'}), 400
    h = {'Prefer': 'resolution=merge-duplicates'}
    r = api_req('POST', T_NUTRITION, data=data, extra_headers=h)
    if r.status_code not in (200, 201):
        return jsonify({'error': r.text}), r.status_code
    return jsonify({'message': f'{len(data)} registros guardados'})


@app.route('/api/ingredients/names', methods=['GET'])
@api_auth_required
def get_ingredient_names():
    r = api_req('GET', T_INGS, params={'select': 'name'})
    if r.status_code != 200:
        return jsonify({'error': r.text}), r.status_code
    names = [i['name'] for i in r.json()]
    return jsonify(sorted(names))


# ── Menu Planner Routes ──

@app.route('/menu-planner')
@login_required
def menu_planner_page():
    return render_template('menu_planner.html', user=session['user'])


@app.route('/pos')
@login_required
def pos_page():
    return render_template('pos.html', user=session['user'])


@app.route('/api/menu', methods=['GET'])
@api_auth_required
def get_menu():
    r = api_req('GET', T_MENU, params={'order': 'sort_order.asc'})
    if r.status_code != 200:
        return jsonify({'error': r.text}), r.status_code
    dishes = r.json()
    if not dishes:
        return jsonify([])

    dish_ids = [d['id'] for d in dishes]

    # Batch-fetch all recipe items
    id_filter = 'in.(' + ','.join(str(i) for i in dish_ids) + ')'
    rr = api_req('GET', T_MENU_RECIPE, params={'dish_id': id_filter})
    all_items = rr.json() if rr.status_code == 200 else []

    # Group items by dish_id
    items_by_dish = {}
    for item in all_items:
        items_by_dish.setdefault(item['dish_id'], []).append(item)

    # Batch-fetch all ingredient costs (for items without unit_cost)
    ing_names = set()
    for items in items_by_dish.values():
        for item in items:
            if not item.get('unit_cost'):
                ing_names.add(item['ingredient_name'])
    ing_cost_map = {}
    if ing_names:
        name_filter = 'in.(' + ','.join(n.replace("'", "''") for n in ing_names) + ')'
        ri = api_req('GET', T_INGS, params={'name': name_filter, 'select': 'name,cost,measure'})
        if ri.status_code == 200:
            for ing in ri.json():
                mult = _cost_multiplier(ing.get('measure', 'g'))
                ing_cost_map[ing['name']] = float(ing['cost']) * mult

    # Batch-fetch nutrition data for all ingredients in recipes
    all_ing_names = set()
    for items in items_by_dish.values():
        for item in items:
            all_ing_names.add(item['ingredient_name'])
    nutrition_map = {}
    if all_ing_names:
        nf = 'in.(' + ','.join(n.replace("'", "''") for n in all_ing_names) + ')'
        rn = api_req('GET', T_NUTRITION, params={'ingredient_name': nf})
        if rn.status_code == 200:
            for n in rn.json():
                nutrition_map[n['ingredient_name']] = n

    for dish in dishes:
        did = dish['id']
        items = items_by_dish.get(did, [])
        raw_total = 0.0
        enriched = []
        # Nutrition accumulators
        nut = {
            'protein_g': 0.0, 'fat_g': 0.0, 'carbs_g': 0.0,
            'fiber_g': 0.0, 'sodium_mg': 0.0, 'calories': 0.0,
        }
        total_recipe_g = 0.0
        for item in items:
            qty = float(item.get('quantity_grams', 0))
            total_recipe_g += qty
            if item.get('unit_cost') is not None and float(item.get('unit_cost', 0)) > 0:
                unit_cost = float(item['unit_cost'])
            else:
                unit_cost = ing_cost_map.get(item['ingredient_name'], 0)
            line_cost = qty * unit_cost
            raw_total += line_cost
            enriched.append({
                'id': item['id'],
                'dish_id': item['dish_id'],
                'ingredient_name': item['ingredient_name'],
                'quantity_grams': qty,
                'unit_cost': round(unit_cost, 4),
                'line_cost': round(line_cost, 2),
            })
            # Accumulate nutrition (data is per 100g)
            nd = nutrition_map.get(item['ingredient_name'])
            if nd:
                factor = qty / 100.0
                nut['protein_g'] += float(nd.get('protein_g', 0)) * factor
                nut['fat_g'] += float(nd.get('fat_g', 0)) * factor
                nut['carbs_g'] += float(nd.get('carbs_g', 0)) * factor
                nut['fiber_g'] += float(nd.get('fiber_g', 0)) * factor
                nut['sodium_mg'] += float(nd.get('sodium_mg', 0)) * factor
                nut['calories'] += float(nd.get('total_calories', 0)) * factor
        raw_total = round(raw_total, 2)
        overhead = float(dish.get('overhead_cost', 0))
        final_total = round(raw_total + overhead, 2)
        dish['cost_total'] = final_total
        dish['raw_cost'] = raw_total
        dish['recipe_count'] = len(enriched)
        dish['nutrition_computed'] = nut
        dish['total_recipe_g'] = round(total_recipe_g, 1)

    return jsonify(dishes)


# ── POS / Landing Page ──

@app.route('/api/pos/dishes', methods=['GET'])
@api_auth_required
def get_pos_dishes():
    r = api_req('GET', T_MENU, params={'order': 'category.asc,sort_order.asc'})
    if r.status_code != 200:
        return jsonify({'error': r.text}), r.status_code
    dishes = r.json()
    if not dishes:
        return jsonify([])

    dish_ids = [d['id'] for d in dishes]
    id_filter = 'in.(' + ','.join(str(i) for i in dish_ids) + ')'
    rr = api_req('GET', T_MENU_RECIPE, params={'dish_id': id_filter})
    all_items = rr.json() if rr.status_code == 200 else []

    items_by_dish = {}
    for item in all_items:
        items_by_dish.setdefault(item['dish_id'], []).append(item)

    ing_names = set()
    for items in items_by_dish.values():
        for item in items:
            ing_names.add(item['ingredient_name'])
    ing_cost_map = {}
    if ing_names:
        nf = 'in.(' + ','.join(n.replace("'", "''") for n in ing_names) + ')'
        ri = api_req('GET', T_INGS, params={'name': nf, 'select': 'name,cost,measure,count'})
        if ri.status_code == 200:
            for ing in ri.json():
                mult = _cost_multiplier(ing.get('measure', 'g'))
                ing_cost_map[ing['name']] = {
                    'cost': float(ing['cost']) * mult,
                    'count': float(ing.get('count', 0)),
                }

    result = []
    for dish in dishes:
        did = dish['id']
        items = items_by_dish.get(did, [])
        cost_total = 0.0
        recipe_details = []
        for item in items:
            qty = float(item.get('quantity_grams', 0))
            ic = ing_cost_map.get(item['ingredient_name'], {})
            unit_cost = ic.get('cost', 0)
            line_cost = qty * unit_cost
            cost_total += line_cost
            recipe_details.append({
                'ingredient_name': item['ingredient_name'],
                'quantity_grams': qty,
                'unit_cost': round(unit_cost, 4),
                'current_stock': ic.get('count', 0),
            })
        sale_price = float(dish.get('sale_price', 0))
        overhead = float(dish.get('overhead_cost', 0))
        cost_total = round(cost_total + overhead, 2)
        result.append({
            'id': did,
            'category': dish.get('category', ''),
            'dish_name': dish.get('dish_name', ''),
            'sale_price': sale_price,
            'cost_total': cost_total,
            'portion_weight_g': float(dish.get('portion_weight_g', 0) or 0),
            'profit': round(sale_price - cost_total, 2),
            'margin_pct': round(((sale_price - cost_total) / sale_price * 100) if sale_price else 0, 1),
            'recipe_count': len(recipe_details),
            'recipe_details': recipe_details,
        })
    return jsonify(result)


@app.route('/api/pos/sell', methods=['POST'])
@api_auth_required
def record_sale():
    try:
        data = request.get_json()
        if not data or not isinstance(data.get('items'), list) or not data['items']:
            return jsonify({'error': 'Envia lista de items'}), 400

        items_data = data['items']

        # Compute totals
        total_sale = 0.0
        total_cost = 0.0
        total_profit = 0.0
        line_items = []

        for it in items_data:
            dish_id = it.get('dish_id')
            qty = int(it.get('quantity', 1))
            if qty < 1: continue

            rd = api_req('GET', T_MENU, params={'id': 'eq.' + str(dish_id)})
            if rd.status_code != 200 or not rd.json():
                return jsonify({'error': f'Plato ID {dish_id} no encontrado'}), 404
            dish = rd.json()[0]
            dish_name = dish.get('dish_name', '')
            sale_price_unit = float(it.get('sale_price', dish.get('sale_price', 0)))

            # Compute cost per unit from recipe
            rr = api_req('GET', T_MENU_RECIPE, params={'dish_id': 'eq.' + str(dish_id)})
            recipe_items = rr.json() if rr.status_code == 200 else []
            cost_per_unit = 0.0
            for ri in recipe_items:
                q = float(ri.get('quantity_grams', 0))
                if ri.get('unit_cost') is not None and float(ri.get('unit_cost', 0)) > 0:
                    uc = float(ri['unit_cost'])
                else:
                    r2 = api_req('GET', T_INGS, params={'name': 'eq.' + ri['ingredient_name'], 'select': 'cost,measure'})
                    ingd = r2.json()
                    if ingd:
                        c = float(ingd[0].get('cost', 0))
                        m = ingd[0].get('measure', 'g')
                        uc = c * _cost_multiplier(m)
                    else:
                        uc = 0
                cost_per_unit += q * uc
            overhead = float(dish.get('overhead_cost', 0))
            cost_per_unit = round(cost_per_unit + overhead, 2)

            line_sale = round(sale_price_unit * qty, 2)
            line_cost = round(cost_per_unit * qty, 2)
            line_profit = round(line_sale - line_cost, 2)
            total_sale += line_sale
            total_cost += line_cost
            total_profit += line_profit

            line_items.append({
                'dish_id': dish_id,
                'dish_name': dish_name,
                'quantity': qty,
                'sale_price_unit': sale_price_unit,
                'cost_per_unit': cost_per_unit,
                'line_sale': line_sale,
                'line_cost': line_cost,
                'line_profit': line_profit,
            })

            # Deduct inventory: for each recipe ingredient, subtract qty_grams * qty_sold
            for ri in recipe_items:
                ing_name = ri['ingredient_name']
                deduct_g = float(ri.get('quantity_grams', 0)) * qty
                rs = api_req('GET', T_INGS, params={'name': 'eq.' + ing_name, 'select': 'count'})
                if rs.status_code == 200 and rs.json():
                    current = float(rs.json()[0].get('count', 0))
                    new_count = max(0, current - deduct_g)
                    api_req('PATCH', T_INGS, data={'count': new_count}, params={'name': 'eq.' + ing_name})

        if not line_items:
            return jsonify({'error': 'Sin items validos'}), 400

        items_count = sum(it['quantity'] for it in line_items)

        # Create sale record
        sale_record = {
            'total_sale': round(total_sale, 2),
            'total_cost': round(total_cost, 2),
            'total_profit': round(total_profit, 2),
            'items_count': items_count,
        }
        r_create = api_req('POST', T_SALES, data=sale_record, extra_headers={'Prefer': 'return=representation'})
        if r_create.status_code not in (200, 201):
            return jsonify({'error': f'Error al crear venta: {r_create.text[:200]}'}), r_create.status_code
        try:
            sale_id = r_create.json()[0]['id']
        except (IndexError, KeyError, TypeError):
            return jsonify({'error': f'Respuesta inesperada: {r_create.text[:200]}'}), 500

        # Insert line items
        for li in line_items:
            li['sale_id'] = sale_id
        api_req('POST', T_SALE_ITEMS, data=line_items)

        return jsonify({
            'message': f'Venta registrada — {items_count} productos, $ {total_sale:.0f}',
            'sale_id': sale_id,
            'total_sale': round(total_sale, 2),
            'total_cost': round(total_cost, 2),
            'total_profit': round(total_profit, 2),
        })
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor: ' + str(e)}), 500


@app.route('/api/pos/today', methods=['GET'])
@api_auth_required
def get_today_sales():
    today = datetime.utcnow().strftime('%Y-%m-%d')
    r = api_req('GET', T_SALES, params={'created_at': 'gte.' + today, 'order': 'created_at.desc'})
    if r.status_code != 200:
        return jsonify({'error': r.text}), r.status_code
    sales = r.json()
    summary = {
        'total_sale': sum(float(s.get('total_sale', 0)) for s in sales),
        'total_cost': sum(float(s.get('total_cost', 0)) for s in sales),
        'total_profit': sum(float(s.get('total_profit', 0)) for s in sales),
        'orders_count': len(sales),
        'items_count': sum(int(s.get('items_count', 0)) for s in sales),
    }
    return jsonify({'sales': sales, 'summary': summary})


@app.route('/api/pos/sale-price', methods=['PUT'])
@api_auth_required
def update_sale_price():
    data = request.get_json()
    dish_id = data.get('dish_id')
    price = data.get('sale_price')
    if not dish_id or price is None:
        return jsonify({'error': 'dish_id y sale_price requeridos'}), 400
    r = api_req('PATCH', T_MENU, data={'sale_price': float(price)}, params={'id': 'eq.' + str(dish_id)})
    if r.status_code not in (200, 204):
        return jsonify({'error': r.text}), r.status_code
    return jsonify({'message': 'Precio actualizado'})


@app.route('/api/menu', methods=['POST'])
@api_auth_required
def add_menu_item():
    data = request.get_json()
    if not data or not data.get('category') or not data.get('dish_name'):
        return jsonify({'error': 'Categoria y nombre requeridos'}), 400

    items = api_req('GET', T_MENU, params={'category': 'eq.' + data['category'], 'order': 'sort_order.desc', 'limit': 1})
    next_order = items.json()[0]['sort_order'] + 1 if items.status_code == 200 and items.json() else 0

    r = api_req('POST', T_MENU, data={
        'category': data['category'],
        'dish_name': data['dish_name'],
        'sort_order': next_order,
        'status': data.get('status', 'activo'),
    }, extra_headers={'Prefer': 'return=representation'})
    if r.status_code not in (200, 201):
        return jsonify({'error': r.text}), r.status_code
    return jsonify(r.json()[0] if isinstance(r.json(), list) else r.json())


@app.route('/api/menu/<int:item_id>', methods=['PUT'])
@api_auth_required
def update_menu_item(item_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Datos requeridos'}), 400

    update = {}
    for field in ('category', 'dish_name', 'sort_order', 'status', 'sale_price'):
        if field in data:
            update[field] = data[field]

    r = api_req('PATCH', T_MENU, data=update, params={'id': 'eq.' + str(item_id)})
    if r.status_code not in (200, 204):
        return jsonify({'error': r.text}), r.status_code
    return jsonify({'message': 'Actualizado'})


@app.route('/api/menu/<int:item_id>', methods=['DELETE'])
@api_auth_required
def delete_menu_item(item_id):
    r = api_req('DELETE', T_MENU, params={'id': 'eq.' + str(item_id)},
                extra_headers={'Prefer': 'return=representation'})
    if r.status_code == 200 and r.json():
        return jsonify({'message': 'Eliminado'})
    return jsonify({'error': 'No encontrado'}), 404


# ── Menu Recipe (Ingredient-Level Costing) Routes ──

@app.route('/api/menu/<int:dish_id>/recipe', methods=['GET'])
@api_auth_required
def get_menu_recipe(dish_id):
    _, _, enriched, nut = _compute_dish_cost(dish_id)
    return jsonify({'items': enriched, 'nutrition_computed': nut})


@app.route('/api/menu/<int:dish_id>/recipe', methods=['POST'])
@api_auth_required
def add_menu_recipe_item(dish_id):
    data = request.get_json()
    if not data or not data.get('ingredient_name') or not data.get('quantity_grams'):
        return jsonify({'error': 'ingredient_name y quantity_grams requeridos'}), 400
    qty = float(data['quantity_grams'])
    if qty <= 0:
        return jsonify({'error': 'quantity_grams debe ser > 0'}), 400

    payload = {
        'dish_id': dish_id,
        'ingredient_name': data['ingredient_name'],
        'quantity_grams': qty,
    }
    if data.get('unit_cost') is not None:
        payload['unit_cost'] = float(data['unit_cost'])

    r = api_req('POST', T_MENU_RECIPE, data=payload,
                extra_headers={'Prefer': 'return=representation'})
    if r.status_code not in (200, 201):
        return jsonify({'error': r.text}), r.status_code
    # Recompute dish cost
    _compute_dish_cost(dish_id)
    items = r.json()
    return jsonify(items[0] if isinstance(items, list) else items)


@app.route('/api/menu/<int:dish_id>/recipe/<int:item_id>', methods=['PUT'])
@api_auth_required
def update_menu_recipe_item(dish_id, item_id):
    data = request.get_json()
    update = {}
    if 'ingredient_name' in data:
        update['ingredient_name'] = data['ingredient_name']
    if 'quantity_grams' in data:
        qty = float(data['quantity_grams'])
        if qty <= 0:
            return jsonify({'error': 'quantity_grams debe ser > 0'}), 400
        update['quantity_grams'] = qty
    if data.get('unit_cost') is not None:
        update['unit_cost'] = float(data['unit_cost'])
    if not update:
        return jsonify({'error': 'Sin datos para actualizar'}), 400

    r = api_req('PATCH', T_MENU_RECIPE, data=update,
                params={'id': 'eq.' + str(item_id), 'dish_id': 'eq.' + str(dish_id)})
    if r.status_code not in (200, 204):
        return jsonify({'error': r.text}), r.status_code
    _compute_dish_cost(dish_id)
    return jsonify({'message': 'Actualizado'})


@app.route('/api/menu/<int:dish_id>/recipe/<int:item_id>', methods=['DELETE'])
@api_auth_required
def delete_menu_recipe_item(dish_id, item_id):
    r = api_req('DELETE', T_MENU_RECIPE, params={'id': 'eq.' + str(item_id), 'dish_id': 'eq.' + str(dish_id)},
                extra_headers={'Prefer': 'return=representation'})
    if r.status_code == 200 and r.json():
        _compute_dish_cost(dish_id)
        return jsonify({'message': 'Ingrediente eliminado de la receta'})
    return jsonify({'error': 'No encontrado'}), 404


@app.route('/api/menu/<int:dish_id>/nutrition', methods=['PUT'])
@api_auth_required
def update_dish_nutrition(dish_id):
    data = request.get_json()
    fields = ['cost_total', 'portion_weight_g', 'protein_g', 'calories', 'carbs_g', 'fat_g', 'fiber_g', 'sodium_mg', 'overhead_cost']
    update = {}
    for f in fields:
        if f in data:
            update[f] = data[f]
    if not update:
        return jsonify({'error': 'Sin datos'}), 400
    r = api_req('PATCH', T_MENU, data=update, params={'id': 'eq.' + str(dish_id)})
    if r.status_code not in (200, 204):
        return jsonify({'error': r.text}), r.status_code
    return jsonify({'message': 'Actualizado'})


# ── Admin Routes ──

@app.route('/admin')
@login_required
def admin_page():
    user = session.get('user', {})
    if not is_admin(user.get('email', '')):
        return redirect('/')
    return render_template('admin.html', user=user)


@app.route('/api/admin/users', methods=['GET'])
@api_auth_required
def admin_get_users():
    user = session.get('user', {})
    if not is_admin(user.get('email', '')):
        return jsonify({'error': 'No autorizado'}), 403
    r = api_req('GET', T_USERS, params={'order': 'created_at.desc'})
    if r.status_code != 200:
        return jsonify({'error': r.text}), r.status_code
    return jsonify(r.json())


@app.route('/api/admin/users', methods=['POST'])
@api_auth_required
def admin_create_user():
    user = session.get('user', {})
    if not is_admin(user.get('email', '')):
        return jsonify({'error': 'No autorizado'}), 403
    data = request.get_json()
    if not data or not data.get('email'):
        return jsonify({'error': 'Email requerido'}), 400
    api_req('POST', T_USERS,
            data={'id': data.get('id', str(uuid.uuid4())),
                  'email': data['email'],
                  'role': data.get('role', 'user')},
            extra_headers={'Prefer': 'resolution=merge-duplicates'})
    return jsonify({'message': 'Usuario agregado'})


@app.route('/api/admin/users/<email>/role', methods=['POST'])
@api_auth_required
def admin_update_role(email):
    user = session.get('user', {})
    if not is_admin(user.get('email', '')):
        return jsonify({'error': 'No autorizado'}), 403
    data = request.get_json()
    if not data or not data.get('role'):
        return jsonify({'error': 'Rol requerido'}), 400
    if data['role'] not in ('user', 'admin'):
        return jsonify({'error': 'Rol inválido'}), 400
    r = api_req('PATCH', T_USERS, data={'role': data['role']},
                params={'email': 'eq.' + email})
    if r.status_code not in (200, 204):
        return jsonify({'error': r.text}), r.status_code
    return jsonify({'message': 'Rol actualizado a ' + data['role']})


@app.route('/api/admin/users/<email>', methods=['DELETE'])
@api_auth_required
def admin_delete_user(email):
    user = session.get('user', {})
    if not is_admin(user.get('email', '')):
        return jsonify({'error': 'No autorizado'}), 403
    if email.lower() == user.get('email', '').lower():
        return jsonify({'error': 'No puedes eliminarte a ti mismo'}), 400
    api_req('DELETE', T_USERS, params={'email': 'eq.' + email})
    return jsonify({'message': 'Usuario eliminado'})


@app.route('/api/admin/migrate', methods=['POST'])
@api_auth_required
def run_migration():
    user = session.get('user', {})
    if not user.get('email'):
        return jsonify({'error': 'No autenticado'}), 401

    ref = SUPABASE_URL.rstrip('/').split('.')[0].split('//')[1] if SUPABASE_URL else ''
    if not ref:
        return jsonify({'error': 'URL de Supabase no configurada'}), 500

    sql = '''
    ALTER TABLE ingredient_table ADD COLUMN IF NOT EXISTS user_id UUID DEFAULT auth.uid();
    ALTER TABLE ingredient_table ADD COLUMN IF NOT EXISTS classification TEXT DEFAULT '';
    ALTER TABLE ingredient_table ADD COLUMN IF NOT EXISTS brand TEXT DEFAULT '';
    ALTER TABLE ingredient_table ADD COLUMN IF NOT EXISTS supplier TEXT DEFAULT '';
    ALTER TABLE ingredient_table ADD COLUMN IF NOT EXISTS presentation TEXT DEFAULT '';
    ALTER TABLE ingredient_table ADD COLUMN IF NOT EXISTS notes TEXT DEFAULT '';
    ALTER TABLE recipe_table ADD COLUMN IF NOT EXISTS user_id UUID DEFAULT auth.uid();
    ALTER TABLE recipe_ingredients_table ADD COLUMN IF NOT EXISTS user_id UUID DEFAULT auth.uid();
    CREATE TABLE IF NOT EXISTS user_profiles (
        id UUID PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS menu_board (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        category TEXT NOT NULL,
        dish_name TEXT NOT NULL,
        sort_order INT DEFAULT 0,
        status TEXT DEFAULT 'activo',
        cost_total DECIMAL(10,2) DEFAULT 0,
        portion_weight_g INT DEFAULT 150,
        protein_g DECIMAL(8,2) DEFAULT 0,
        calories DECIMAL(8,2) DEFAULT 0,
        carbs_g DECIMAL(8,2) DEFAULT 0,
        fat_g DECIMAL(8,2) DEFAULT 0,
        fiber_g DECIMAL(8,2) DEFAULT 0,
        sodium_mg DECIMAL(8,2) DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS menu_recipe_items (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        dish_id BIGINT NOT NULL REFERENCES menu_board(id) ON DELETE CASCADE,
        ingredient_name TEXT NOT NULL,
        quantity_grams DECIMAL(10,2) NOT NULL DEFAULT 0,
        unit_cost DECIMAL(10,4) DEFAULT 0
    );
    ALTER TABLE menu_recipe_items ADD COLUMN IF NOT EXISTS unit_cost DECIMAL(10,4) DEFAULT 0;
    ALTER TABLE menu_board ADD COLUMN IF NOT EXISTS cost_total DECIMAL(10,2) DEFAULT 0;
    ALTER TABLE menu_board ADD COLUMN IF NOT EXISTS overhead_cost DECIMAL(10,2) DEFAULT 0;
    ALTER TABLE menu_board ADD COLUMN IF NOT EXISTS portion_weight_g INT DEFAULT 150;
    ALTER TABLE menu_board ADD COLUMN IF NOT EXISTS protein_g DECIMAL(8,2) DEFAULT 0;
    ALTER TABLE menu_board ADD COLUMN IF NOT EXISTS calories DECIMAL(8,2) DEFAULT 0;
    ALTER TABLE menu_board ADD COLUMN IF NOT EXISTS carbs_g DECIMAL(8,2) DEFAULT 0;
    ALTER TABLE menu_board ADD COLUMN IF NOT EXISTS fat_g DECIMAL(8,2) DEFAULT 0;
    ALTER TABLE menu_board ADD COLUMN IF NOT EXISTS fiber_g DECIMAL(8,2) DEFAULT 0;
    ALTER TABLE menu_board ADD COLUMN IF NOT EXISTS sodium_mg DECIMAL(8,2) DEFAULT 0;
    '''

    # Try management API
    try:
        r = requests.post(
            f'https://api.supabase.com/v1/projects/{ref}/database/query',
            headers={
                'Authorization': f'Bearer {SUPABASE_KEY}',
                'Content-Type': 'application/json',
            },
            json={'query': sql}
        )
        if r.status_code < 400:
            return jsonify({'message': 'Migración ejecutada. Columnas user_id agregadas.', 'success': True})
        error_detail = r.json().get('error', r.text[:200])
    except Exception as e:
        error_detail = str(e)

    return jsonify({
        'error': f'Migración automática falló: {error_detail}',
        'manual_sql': sql,
        'instructions': 'Ve al panel de Supabase > SQL Editor, pega y ejecuta el SQL de arriba.',
    }), 400


def parseFloat(v):
    try:
        return float(v)
    except:
        return 0.0
