import os
import sys
import json
import uuid
import requests
from urllib.parse import quote
from datetime import datetime, timedelta
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
T_PROJECTIONS = 'sales_projections'
T_PRECIOS = 'precios_competencia'

# Fudness.co integration
FUDNESS_API = 'https://fudness.co/wp-json'
FUDNESS_STORE_API = f'{FUDNESS_API}/wc/store/v1'
FUDNESS_WC_API = f'{FUDNESS_API}/wc/v3'
T_FUD_PRODS = 'fudness_products'
T_FUD_ORDERS = 'fudness_orders'
T_FUD_SYNC = 'fudness_sync_log'


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


@app.route('/ai-compras-kitchen')
def ai_compras_kitchen():
    return render_template('ai_compras_kitchen.html')


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


def _convert_val(val, measure):
    if measure == 'lb':
        return round(val / 453.592, 2)
    return round(val / 1000, 3)

def _calc_needed_from_sales(days):
    pr = api_req('GET', T_PROJ, params={'is_active': 'eq.true'})
    has_projections = pr.status_code == 200 and len(pr.json()) > 0

    if has_projections:
        projections = pr.json()
        rr = api_req('GET', T_MENU_RECIPE)
        recipe_items = rr.json() if rr.status_code == 200 else []

        needed = {}
        for proj in projections:
            did = proj['dish_id']
            units = int(proj.get('projected_units', 30))
            dish_recipe_ings = [ri for ri in recipe_items if (ri.get('menu_item_id') or ri['dish_id']) == did]
            for ri in dish_recipe_ings:
                name = ri['ingredient_name']
                qty_grams = float(ri.get('quantity_grams', 0))
                total_needed = qty_grams * units
                needed[name] = needed.get(name, 0) + total_needed
        return needed

    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    rs = api_req('GET', T_SALES, params={'created_at': 'gte.' + since, 'select': 'id'})
    sale_ids = [s['id'] for s in (rs.json() if rs.status_code == 200 else [])]
    if not sale_ids:
        return {}

    items_resp = api_req('GET', T_SALE_ITEMS, params={
        'sale_id': 'in.(' + ','.join(str(s) for s in sale_ids) + ')'
    })
    sale_items = items_resp.json() if items_resp.status_code == 200 else []

    dish_units = {}
    for si in sale_items:
        did = si['dish_id']
        qty = int(si.get('quantity', 0))
        dish_units[did] = dish_units.get(did, 0) + qty

    rr = api_req('GET', T_MENU_RECIPE)
    recipe_items = rr.json() if rr.status_code == 200 else []

    needed = {}
    for did, units_sold in dish_units.items():
        dish_recipe_ings = [ri for ri in recipe_items if (ri.get('menu_item_id') or ri['dish_id']) == did]
        for ri in dish_recipe_ings:
            name = ri['ingredient_name']
            qty_grams = float(ri.get('quantity_grams', 0))
            total_needed = qty_grams * units_sold
            needed[name] = needed.get(name, 0) + total_needed
    return needed


@app.route('/api/shopping-list', methods=['GET'])
@api_auth_required
def global_shopping_list():
    mode = request.args.get('mode', 'stock')
    if mode not in ('stock', 'sales'):
        mode = 'stock'

    r = api_req('GET', T_INGS)
    ingredients = r.json() if r.status_code == 200 else []
    stock_map = {i['name']: i for i in ingredients}

    if mode == 'sales':
        days = int(request.args.get('days', 30))
        needed = _calc_needed_from_sales(days)
    else:
        rr = api_req('GET', T_MENU_RECIPE)
        all_items = rr.json() if rr.status_code == 200 else []
        needed = {}
        for item in all_items:
            name = item['ingredient_name']
            qty = float(item.get('quantity_grams', 0))
            if name not in needed:
                needed[name] = 0
            needed[name] += qty

    def convert_qty(val, measure):
        if measure == 'g': return round(val, 0), 'g'
        if measure == 'kg': return round(val / 1000, 2), 'kg'
        if measure == 'ml': return round(val, 0), 'ml'
        if measure == 'l': return round(val / 1000, 2), 'l'
        if measure == 'lb': return round(val / 453.592, 2), 'lb'
        return round(val, 0), measure

    shoppingList = []
    totalCost = 0
    handled = set()

    for name, qty_needed in needed.items():
        ing = stock_map.get(name)
        if not ing:
            continue
        stock = float(ing.get('count', 0))
        min_stock = float(ing.get('min_stock', 0) or 0)
        missing = max(0, qty_needed - stock)
        if missing <= 0 and stock >= min_stock:
            continue
        if stock < min_stock:
            missing = max(missing, min_stock - stock)
        handled.add(name)

        measure = ing.get('measure', 'g')
        cost = float(ing.get('cost', 0))
        display_qty, display_measure = convert_qty(missing, measure)

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
            'reason': 'menu_needed' if qty_needed > stock else 'min_stock',
            'current_stock': _convert_val(stock, measure),
            'min_stock': _convert_val(min_stock, measure),
            'stock_measure': {'g': 'kg', 'ml': 'l'}.get(measure, measure),
        })

    for ing in ingredients:
        name = ing['name']
        if name in handled:
            continue
        stock = float(ing.get('count', 0))
        min_stock = float(ing.get('min_stock', 0) or 0)
        if stock >= min_stock:
            continue
        missing = min_stock - stock
        if missing <= 0:
            continue

        measure = ing.get('measure', 'g')
        cost = float(ing.get('cost', 0))
        display_qty, display_measure = convert_qty(missing, measure)

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
            'reason': 'min_stock',
            'current_stock': _convert_val(stock, measure),
            'min_stock': _convert_val(min_stock, measure),
            'stock_measure': {'g': 'kg', 'ml': 'l'}.get(measure, measure),
        })

    shoppingList.sort(key=lambda x: x['name'])
    return jsonify({'shopping_list': shoppingList, 'total_cost': round(totalCost, 2), 'mode': mode})


T_PROJ = 'sales_projections'

@app.route('/projections')
@api_auth_required
def projections_page():
    user = session.get('user', {})
    return render_template('projections.html', user=user)

@app.route('/api/projections', methods=['GET'])
@api_auth_required
def get_projections():
    r = api_req('GET', T_PROJ, params={'order': 'dish_name.asc'})
    if r.status_code == 404:
        return jsonify({'projections': [], 'table_exists': False})
    projections = r.json() if r.status_code == 200 else []
    mr = api_req('GET', T_MENU)
    menu_map = {m['id']: m for m in (mr.json() if mr.status_code == 200 else [])}
    rr = api_req('GET', T_MENU_RECIPE)
    recipe_items = rr.json() if rr.status_code == 200 else []
    ing_count = {}
    for ri in recipe_items:
        did = ri.get('menu_item_id') or ri['dish_id']
        ing_count[did] = ing_count.get(did, 0) + 1
    for p in projections:
        dish = menu_map.get(p['dish_id'])
        if dish:
            p['category'] = dish.get('category', '')
        p['ingredient_count'] = ing_count.get(p['dish_id'], 0)
    return jsonify({'projections': projections, 'table_exists': True})

@app.route('/api/projections/<int:proj_id>', methods=['PATCH'])
@api_auth_required
def update_projection(proj_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Datos requeridos'}), 400
    data['updated_at'] = datetime.utcnow().isoformat()
    r = api_req('PATCH', T_PROJ, data=data, params={'id': 'eq.' + str(proj_id)})
    if r.status_code in (200, 204):
        return jsonify({'ok': True})
    return jsonify({'error': r.text}), r.status_code

@app.route('/api/projections/init', methods=['POST'])
@api_auth_required
def init_projections():
    mr = api_req('GET', T_MENU, params={'order': 'category.asc,dish_name.asc', 'select': 'id,dish_name,category'})
    menu_items = mr.json() if mr.status_code == 200 else []
    rr = api_req('GET', T_MENU_RECIPE)
    recipe_items = rr.json() if rr.status_code == 200 else []

    dish_costs = {}
    ing_map = {}
    for ri in recipe_items:
        did = ri.get('menu_item_id') or ri['dish_id']
        qty = float(ri.get('quantity_grams', 0))
        cost = float(ri.get('unit_cost', 0))
        if cost <= 0:
            if ri['ingredient_name'] not in ing_map:
                r2 = api_req('GET', T_INGS, params={'name': 'eq.' + ri['ingredient_name'], 'select': 'cost,measure'})
                ingd = r2.json()
                if ingd:
                    c = float(ingd[0].get('cost', 0))
                    m = ingd[0].get('measure', 'g')
                    ing_map[ri['ingredient_name']] = c * _cost_multiplier(m)
                else:
                    ing_map[ri['ingredient_name']] = 0
            cost = ing_map[ri['ingredient_name']]
        if did not in dish_costs:
            dish_costs[did] = {'qty': 0, 'cost': 0}
        dish_costs[did]['qty'] += qty
        dish_costs[did]['cost'] += qty * cost

    created = 0
    today = datetime.utcnow().date()
    for dish in menu_items:
        did = dish['id']
        cost_info = dish_costs.get(did, {'qty': 0, 'cost': 0})
        unit_cost = round(cost_info['cost'], 2)
        data = {
            'dish_id': did,
            'dish_name': dish['dish_name'],
            'projected_units': 30,
            'unit_cost': unit_cost,
            'start_date': today.isoformat(),
            'end_date': (today.replace(day=1) + timedelta(days=32)).replace(day=1).isoformat(),
            'estimated_qty': round(cost_info['qty'] * 30, 2),
            'estimated_cost': round(unit_cost * 30, 2),
        }
        r = api_req('POST', T_PROJ, data=data)
        if r.status_code in (200, 201):
            created += 1
    return jsonify({'created': created, 'total': len(menu_items)})


@app.route('/api/projections/bulk', methods=['PUT'])
@api_auth_required
def bulk_update_projections():
    data = request.get_json()
    if not data or 'projections' not in data:
        return jsonify({'error': 'projections required'}), 400

    rr = api_req('GET', T_MENU_RECIPE)
    recipe_items = rr.json() if rr.status_code == 200 else []
    dish_costs = {}
    ing_map = {}
    for ri in recipe_items:
        did = ri.get('menu_item_id') or ri['dish_id']
        qty = float(ri.get('quantity_grams', 0))
        cost = float(ri.get('unit_cost', 0))
        if cost <= 0:
            if ri['ingredient_name'] not in ing_map:
                r2 = api_req('GET', T_INGS, params={'name': 'eq.' + ri['ingredient_name'], 'select': 'cost,measure'})
                ingd = r2.json()
                if ingd:
                    c = float(ingd[0].get('cost', 0))
                    m = ingd[0].get('measure', 'g')
                    ing_map[ri['ingredient_name']] = c * _cost_multiplier(m)
                else:
                    ing_map[ri['ingredient_name']] = 0
            cost = ing_map[ri['ingredient_name']]
        if did not in dish_costs:
            dish_costs[did] = {'qty': 0, 'cost': 0}
        dish_costs[did]['qty'] += qty
        dish_costs[did]['cost'] += qty * cost

    updated = 0
    for proj in data['projections']:
        pid = proj.get('id')
        if not pid:
            continue
        did = proj.get('dish_id')
        units = int(proj.get('projected_units', 30))
        cost_info = dish_costs.get(did, {'qty': 0, 'cost': 0})
        unit_cost = round(cost_info['cost'], 2)
        update_data = {
            'projected_units': units,
            'unit_cost': unit_cost,
            'estimated_qty': round(cost_info['qty'] * units, 2),
            'estimated_cost': round(unit_cost * units, 2),
            'updated_at': datetime.utcnow().isoformat(),
        }
        r = api_req('PATCH', T_PROJ, data=update_data, params={'id': 'eq.' + str(pid)})
        if r.status_code in (200, 204):
            updated += 1
    return jsonify({'updated': updated})


@app.route('/precios')
@api_auth_required
def precios_page():
    return render_template('precios.html', user=session['user'], is_admin=session.get('email', '').lower() in ADMIN_EMAILS)


@app.route('/api/precios', methods=['GET'])
@api_auth_required
def get_precios():
    r = api_req('GET', T_PRECIOS, params={'order': 'ingrediente.asc,supermercado.asc'})
    precios = r.json() if r.status_code == 200 else []
    return jsonify({'precios': precios})


@app.route('/api/precios', methods=['PUT'])
@api_auth_required
def upsert_precio():
    data = request.get_json()
    if not data or 'ingrediente' not in data or 'supermercado' not in data or 'precio' not in data:
        return jsonify({'error': 'ingrediente, supermercado, precio requeridos'}), 400
    exists = api_req('GET', T_PRECIOS, params={
        'ingrediente': 'eq.' + data['ingrediente'],
        'supermercado': 'eq.' + data['supermercado'],
        'limit': 1
    })
    payload = {
        'ingrediente': data['ingrediente'],
        'supermercado': data['supermercado'],
        'precio': float(data['precio']),
        'producto': data.get('producto', data['ingrediente']),
        'url': data.get('url', ''),
        'fecha_scrape': datetime.utcnow().date().isoformat(),
    }
    if exists.status_code == 200 and len(exists.json()) > 0:
        r = api_req('PATCH', T_PRECIOS, data=payload, params={
            'ingrediente': 'eq.' + data['ingrediente'],
            'supermercado': 'eq.' + data['supermercado'],
        })
    else:
        r = api_req('POST', T_PRECIOS, data=payload)
    return jsonify({'ok': r.status_code in (200, 201, 204)})


@app.route('/api/precios/seed', methods=['POST'])
@api_auth_required
def seed_precios():
    r = api_req('GET', 'ingredient_table', params={'select': 'name,cost,measure,supplier'})
    ings = r.json() if r.status_code == 200 else []
    supermercados = ['Olímpica', 'Carulla', 'Éxito', 'Makro']
    import random
    random.seed(42)
    seeded = 0
    for ing in ings:
        if not ing.get('cost') or float(ing['cost']) <= 0:
            continue
        cost = float(ing['cost'])
        for sm in supermercados:
            mult = 0.7 + random.random() * 0.8
            payload = {
                'ingrediente': ing['name'],
                'supermercado': sm,
                'precio': round(cost * mult, 0),
                'producto': ing['name'],
                'url': '',
                'fecha_scrape': datetime.utcnow().date().isoformat(),
            }
            api_req('POST', T_PRECIOS, data=payload)
            seeded += 1
    return jsonify({'seeded': seeded})


@app.route('/fudness')
@login_required
def fudness_page():
    products = []
    r = api_req('GET', T_FUD_PRODS, params={'select': '*', 'order': 'name.asc'})
    if r.status_code == 200:
        products = r.json()
    return render_template('fudness.html', user=session['user'], is_admin=is_admin(session.get('email', '')),
                           products=products)


@app.route('/menu-board')
@login_required
def menu_board_page():
    items = []
    r = api_req('GET', T_MENU, params={'select': '*', 'order': 'category.asc,sort_order.asc'})
    if r.status_code == 200:
        items = r.json()
    return render_template('menu_board.html', user=session['user'], is_admin=is_admin(session.get('email', '')),
                           items=items)


@app.route('/api/fudness/products', methods=['GET'])
@api_auth_required
def get_fudness_products():
    r = api_req('GET', T_FUD_PRODS, params={'select': '*', 'order': 'name.asc'})
    if r.status_code != 200:
        return jsonify({'error': r.text}), r.status_code
    return jsonify(r.json())


@app.route('/api/fudness/sync/products', methods=['POST'])
@api_auth_required
def sync_fudness_products():
    synced = 0
    page = 1
    while True:
        r = requests.get(f'{FUDNESS_STORE_API}/products', params={'per_page': 100, 'page': page},
                         headers={'User-Agent': 'KitchenMaster/1.0'})
        if r.status_code != 200 or not r.json():
            break
        products = r.json()
        for p in products:
            slug = p['slug']
            price = float(p['prices']['price']) if p['prices']['price'] else 0
            regular_price = float(p['prices']['regular_price']) if p['prices']['regular_price'] else 0
            tags = [t['name'] for t in p.get('tags', [])]
            cats = [c['name'] for c in p.get('categories', [])]
            api_req('POST', T_FUD_PRODS, data={
                'slug': slug,
                'name': p['name'],
                'price': price,
                'regular_price': regular_price,
                'in_stock': p.get('is_in_stock', False),
                'categories': '{' + ','.join(cats) + '}',
                'tags': '{' + ','.join(tags) + '}',
            }, extra_headers={'Prefer': 'resolution=merge-duplicates'})
            synced += 1
        page += 1
    api_req('POST', T_FUD_SYNC, data={
        'sync_type': 'products', 'status': 'success', 'items_count': synced
    })
    return jsonify({'message': f'Sincronizados {synced} productos'})


@app.route('/api/fudness/sync/details', methods=['POST'])
@api_auth_required
def sync_fudness_details():
    r = api_req('GET', T_FUD_PRODS, params={'select': 'slug'})
    if r.status_code != 200:
        return jsonify({'error': 'Error obteniendo productos'}), 500
    slugs = [p['slug'] for p in r.json()]
    updated = 0
    for slug in slugs:
        r2 = requests.get(f'{FUDNESS_API}/wp/v2/product',
                          params={'slug': slug, '_fields': 'slug,content,excerpt'},
                          headers={'User-Agent': 'KitchenMaster/1.0'})
        if r2.status_code != 200 or not r2.json():
            continue
        wp = r2.json()[0]
        content = wp.get('content', {}).get('rendered', '')
        excerpt = wp.get('excerpt', {}).get('rendered', '')
        api_req('PATCH', T_FUD_PRODS, data={
            'description': content,
            'variations': excerpt,
        }, params={'slug': f'eq.{slug}'})
        updated += 1
    return jsonify({'message': f'Detalles actualizados de {updated} productos'})


@app.route('/api/fudness/sync/orders', methods=['POST'])
@api_auth_required
def sync_fudness_orders():
    data = request.get_json() or {}
    consumer_key = data.get('consumer_key', '')
    consumer_secret = data.get('consumer_secret', '')
    if not consumer_key or not consumer_secret:
        return jsonify({'error': 'Consumer Key y Consumer Secret requeridos'}), 400
    auth = requests.auth.HTTPBasicAuth(consumer_key, consumer_secret)
    synced = 0
    page = 1
    while True:
        r = requests.get(f'{FUDNESS_WC_API}/orders', params={
            'per_page': 100, 'page': page, 'order': 'desc', 'orderby': 'date_created'
        }, auth=auth, headers={'User-Agent': 'KitchenMaster/1.0'})
        if r.status_code != 200 or not r.json():
            break
        orders = r.json()
        for o in orders:
            items = [{
                'product_id': i['product_id'],
                'name': i['name'],
                'quantity': i['quantity'],
                'price': float(i['price']),
                'total': float(i['total']),
            } for i in o.get('line_items', [])]
            shipping = o.get('shipping', {})
            api_req('POST', T_FUD_ORDERS, data={
                'id': o['id'],
                'status': o.get('status', ''),
                'currency': o.get('currency', 'COP'),
                'date_created': o.get('date_created'),
                'total': float(o.get('total', 0)),
                'customer_name': f"{o.get('billing', {}).get('first_name', '')} {o.get('billing', {}).get('last_name', '')}",
                'customer_email': o.get('billing', {}).get('email', ''),
                'customer_phone': o.get('billing', {}).get('phone', ''),
                'items': json.dumps(items),
                'shipping_address': json.dumps(shipping),
                'payment_method': o.get('payment_method_title', ''),
                'payment_status': o.get('payment_status', ''),
            }, extra_headers={'Prefer': 'resolution=merge-duplicates'})
            synced += 1
        page += 1
    api_req('POST', T_FUD_SYNC, data={
        'sync_type': 'orders', 'status': 'success' if synced > 0 else 'error',
        'items_count': synced, 'message': f'{synced} pedidos sincronizados'
    })
    return jsonify({'message': f'Sincronizados {synced} pedidos'})


@app.route('/api/fudness/orders', methods=['GET'])
@api_auth_required
def get_fudness_orders():
    r = api_req('GET', T_FUD_ORDERS, params={'select': '*', 'order': 'date_created.desc'})
    if r.status_code != 200:
        return jsonify({'error': r.text}), r.status_code
    return jsonify(r.json())


@app.route('/api/fudness/orders/<int:order_id>', methods=['GET'])
@api_auth_required
def get_fudness_order(order_id):
    r = api_req('GET', T_FUD_ORDERS, params={'id': f'eq.{order_id}', 'select': '*'})
    if r.status_code != 200 or not r.json():
        return jsonify({'error': 'Pedido no encontrado'}), 404
    return jsonify(r.json()[0])


@app.route('/api/fudness/sync/log', methods=['GET'])
@api_auth_required
def get_fudness_sync_log():
    r = api_req('GET', T_FUD_SYNC, params={'select': '*', 'order': 'created_at.desc', 'limit': 20})
    if r.status_code != 200:
        return jsonify({'error': r.text}), r.status_code
    return jsonify(r.json())


@app.route('/dashboard')
@login_required
def dashboard_page():
    return render_template('dashboard.html', user=session['user'], is_admin=is_admin(session.get('email', '')))


@app.route('/api/dashboard', methods=['GET'])
@api_auth_required
def get_dashboard_data():
    ings = api_req('GET', T_INGS, params={'select': 'name,classification,cost,count,min_stock,measure,supplier'})
    ings = ings.json() if ings.status_code == 200 else []

    menus = api_req('GET', T_MENU, params={'select': 'dish_name,cost_total,sale_price,category'})
    menus = menus.json() if menus.status_code == 200 else []

    sales = api_req('GET', T_SALES, params={'select': 'created_at,total_sale,total_cost,total_profit', 'order': 'created_at.asc'})
    sales = sales.json() if sales.status_code == 200 else []

    projs = api_req('GET', T_PROJECTIONS, params={'select': 'dish_name,projected_units,unit_cost', 'is_active': 'eq.true'})
    projs = projs.json() if projs.status_code == 200 else []

    precios = api_req('GET', T_PRECIOS, params={'select': 'ingrediente,supermercado,precio'})
    precios = precios.json() if precios.status_code == 200 else []

    from collections import defaultdict

    # Clasificación
    cls_counts = defaultdict(lambda: {'count': 0, 'cost': 0})
    for i in ings:
        c = i.get('classification') or 'Sin clasificar'
        cls_counts[c]['count'] += 1
        cls_counts[c]['cost'] += (i.get('cost') or 0) * (i.get('count') or 0)
    clasificacion = [{'name': k, 'count': v['count'], 'cost': round(v['cost'], 0)} for k, v in cls_counts.items()]

    # Top costosos
    costosos = sorted([i for i in ings if (i.get('cost') or 0) > 0], key=lambda x: x['cost'], reverse=True)[:20]
    top_costosos = [{'name': i['name'], 'cost': round(i['cost'], 0), 'total': round((i.get('cost') or 0) * (i.get('count') or 0), 0)} for i in costosos]

    # Stock bajo
    stock_bajo = [{'name': i['name'], 'measure': i.get('measure',''), 'stock': i.get('count',0), 'min': i.get('min_stock',0)} for i in ings if (i.get('count') or 0) <= (i.get('min_stock') or 0)]

    # Márgenes
    margenes = sorted([m for m in menus if (m.get('cost_total') or 0) > 0 and (m.get('sale_price') or 0) > 0],
                      key=lambda x: (x['sale_price'] - x['cost_total']) / x['sale_price'] * 100, reverse=True)[:20]
    margen_data = [{'name': m['dish_name'], 'costo': round(m['cost_total'],0), 'precio': round(m['sale_price'],0), 'margen': round((m['sale_price'] - m['cost_total']) / m['sale_price'] * 100, 1)} for m in margenes]

    # Ventas diarias
    from datetime import datetime as dt
    ventas_diarias = defaultdict(lambda: {'ventas': 0, 'costos': 0, 'ganancia': 0})
    for s in sales:
        try:
            dia = dt.fromisoformat(s['created_at'].replace('Z','+00:00')).strftime('%Y-%m-%d')
        except:
            dia = str(s['created_at'])[:10]
        ventas_diarias[dia]['ventas'] += (s.get('total_sale') or 0)
        ventas_diarias[dia]['costos'] += (s.get('total_cost') or 0)
        ventas_diarias[dia]['ganancia'] += (s.get('total_profit') or 0)
    ventas = sorted([{'fecha': k, 'ventas': round(v['ventas'],0), 'costos': round(v['costos'],0), 'ganancia': round(v['ganancia'],0)} for k, v in ventas_diarias.items()], key=lambda x: x['fecha'])[-30:]

    # Proyecciones
    proj_data = sorted(projs, key=lambda x: x.get('projected_units') or 0, reverse=True)[:20]

    # Proveedores
    prov_counts = defaultdict(lambda: {'count': 0, 'cost': 0})
    for i in ings:
        s = i.get('supplier') or 'Sin proveedor'
        if s:
            prov_counts[s]['count'] += 1
            prov_counts[s]['cost'] += (i.get('cost') or 0) * (i.get('count') or 0)
    proveedores = sorted([{'name': k, 'count': v['count'], 'cost': round(v['cost'], 0)} for k, v in prov_counts.items()], key=lambda x: x['cost'], reverse=True)[:10]

    # KPIs
    kpi_valor_inv = round(sum((i.get('cost') or 0) * (i.get('count') or 0) for i in ings), 0)
    kpi_total_ings = len(ings)
    kpi_total_platos = len(menus)
    kpi_ventas = round(sum(s.get('total_sale') or 0 for s in sales), 0)
    kpi_ganancia = round(sum(s.get('total_profit') or 0 for s in sales), 0)

    return jsonify({
        'kpis': {
            'valor_inventario': kpi_valor_inv,
            'total_ingredientes': kpi_total_ings,
            'total_platos': kpi_total_platos,
            'ventas_totales': kpi_ventas,
            'ganancia_total': kpi_ganancia,
        },
        'clasificacion': clasificacion,
        'top_costosos': top_costosos,
        'stock_bajo': stock_bajo,
        'margenes': margen_data,
        'ventas_diarias': ventas,
        'proyecciones': proj_data,
        'proveedores': proveedores,
    })


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

        # Add sale_price from menu_board
        sale_prices = {d['id']: float(d.get('sale_price', 0) or 0) for d in dish_list}
        for rc in recipeCosts:
            rc['sale_price'] = sale_prices.get(rc['recipe_id'], 0)

    # Compute units sold in current month per dish
    month_start = datetime.utcnow().strftime('%Y-%m-01')
    rs = api_req('GET', T_SALES, params={'created_at': 'gte.' + month_start, 'select': 'id'})
    sale_ids = []
    if rs.status_code == 200:
        sale_ids = [s['id'] for s in rs.json()]
    units_by_dish = {}
    if sale_ids:
        rsi = api_req('GET', T_SALE_ITEMS, params={'sale_id': 'in.(' + ','.join(str(i) for i in sale_ids) + ')', 'select': 'dish_id,quantity'})
        if rsi.status_code == 200:
            for si in rsi.json():
                did = si['dish_id']
                units_by_dish[did] = units_by_dish.get(did, 0) + int(si.get('quantity', 0))
    for rc in recipeCosts:
        rc['units_sold'] = units_by_dish.get(rc['recipe_id'], 0)

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
        ri = api_req('GET', T_INGS, params={'select': 'name,cost,measure'})
        if ri.status_code == 200:
            for ing in ri.json():
                if ing['name'] in ing_names:
                    mult = _cost_multiplier(ing.get('measure', 'g'))
                    ing_cost_map[ing['name']] = float(ing['cost']) * mult

    # Batch-fetch nutrition data for all ingredients in recipes
    all_ing_names = set()
    for items in items_by_dish.values():
        for item in items:
            all_ing_names.add(item['ingredient_name'])
    nutrition_map = {}
    if all_ing_names:
        rn = api_req('GET', T_NUTRITION, params={'select': '*'})
        if rn.status_code == 200:
            for n in rn.json():
                if n['ingredient_name'] in all_ing_names:
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
        ri = api_req('GET', T_INGS, params={'select': 'name,cost,measure,count'})
        if ri.status_code == 200:
            all_ings = ri.json()
            for ing in all_ings:
                if ing['name'] in ing_names:
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
            if item.get('unit_cost') is not None and float(item.get('unit_cost', 0)) > 0:
                unit_cost = float(item['unit_cost'])
            else:
                ic = ing_cost_map.get(item['ingredient_name'], {})
                unit_cost = ic.get('cost', 0)
            line_cost = qty * unit_cost
            cost_total += line_cost
            ic2 = ing_cost_map.get(item['ingredient_name'], {})
            recipe_details.append({
                'ingredient_name': item['ingredient_name'],
                'quantity_grams': qty,
                'unit_cost': round(unit_cost, 4),
                'current_stock': ic2.get('count', 0),
            })
        sale_price = float(dish.get('sale_price', 0))
        overhead = float(dish.get('overhead_cost', 0))
        recomputed = round(cost_total + overhead, 2)
        stored_cost = float(dish.get('cost_total', 0) or 0)
        # Use stored cost_total from menu_board when ingredient data is inconsistent
        cost_final = stored_cost if stored_cost > 0 else recomputed
        result.append({
            'id': did,
            'category': dish.get('category', ''),
            'dish_name': dish.get('dish_name', ''),
            'sale_price': sale_price,
            'cost_total': cost_final,
            'portion_weight_g': float(dish.get('portion_weight_g', 0) or 0),
            'profit': round(sale_price - cost_final, 2),
            'margin_pct': round(((sale_price - cost_final) / sale_price * 100) if sale_price else 0, 1),
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

ALLOWED_TABLES = {
    'fudness_products': T_FUD_PRODS,
    'ingredient_table': T_INGS,
    'menu_board': T_MENU,
    'menu_recipe_items': T_MENU_RECIPE,
    'nutrition_table': T_NUTRITION,
}


@app.route('/api/table-data/<table_name>', methods=['GET'])
@api_auth_required
def get_table_data(table_name):
    supabase_table = ALLOWED_TABLES.get(table_name)
    if not supabase_table:
        return jsonify({'error': 'Tabla no permitida'}), 403
    r = api_req('GET', supabase_table, params={'select': '*'})
    if r.status_code != 200:
        return jsonify({'error': r.text}), r.status_code
    return jsonify(r.json())


@app.route('/api/recipe-items', methods=['GET'])
@api_auth_required
def get_all_recipe_items():
    r = api_req('GET', T_MENU_RECIPE, params={'order': 'dish_id.asc,ingredient_name.asc'})
    if r.status_code != 200:
        return jsonify({'error': r.text}), r.status_code
    items = r.json()
    return jsonify({'items': items, 'total': len(items)})


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
    CREATE TABLE IF NOT EXISTS fudness_products (
        slug TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        price DECIMAL(12,2),
        regular_price DECIMAL(12,2),
        in_stock BOOLEAN DEFAULT false,
        categories TEXT[] DEFAULT '{}',
        tags TEXT[] DEFAULT '{}',
        description TEXT DEFAULT '',
        variations JSONB DEFAULT '[]',
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS fudness_orders (
        id BIGINT PRIMARY KEY,
        status TEXT DEFAULT '',
        currency TEXT DEFAULT 'COP',
        date_created TIMESTAMPTZ,
        total DECIMAL(12,2) DEFAULT 0,
        customer_name TEXT DEFAULT '',
        customer_email TEXT DEFAULT '',
        customer_phone TEXT DEFAULT '',
        items JSONB DEFAULT '[]',
        shipping_address JSONB DEFAULT '{}',
        payment_method TEXT DEFAULT '',
        payment_status TEXT DEFAULT '',
        synced_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS fudness_sync_log (
        id BIGSERIAL PRIMARY KEY,
        sync_type TEXT NOT NULL,
        status TEXT NOT NULL,
        items_count INT DEFAULT 0,
        message TEXT DEFAULT '',
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
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
