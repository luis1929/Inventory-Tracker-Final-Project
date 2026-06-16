import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env file")

API_URL = SUPABASE_URL.rstrip('/') + '/rest/v1'
HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
    'Content-Type': 'application/json',
}

T_INGS = 'ingredient_table'
T_RECIPES = 'recipe_table'
T_RECIPE_INGS = 'recipe_ingredients_table'

print('Supabase API connected\n')

r = requests.get(f'{API_URL}/{T_INGS}?select=name&limit=1', headers=HEADERS)
if r.status_code != 200:
    print('Warning: Could not access ingredient_table. Tables may not exist.')
    print('Run CREATE TABLE statements in Supabase SQL Editor first.')
else:
    print('-Database tables accessible-')

allIngredients = requests.get(f'{API_URL}/{T_INGS}', headers=HEADERS)
allIngredientList = allIngredients.json()
if allIngredientList:
    for row in allIngredientList:
        print(row)


def api_req(method, table, data=None, params=None, extra_headers=None):
    h = HEADERS.copy()
    if extra_headers:
        h.update(extra_headers)
    url = f'{API_URL}/{table}'
    r = requests.request(method, url, headers=h, json=data, params=params)
    return r


def entryFunction():
    print("\n-Add/Update Ingredient Inventory-")

    while True:
        try:
            name = input('Ingredient Name: ').strip()
            measure = input('What unit measure? (lb, oz, qt, etc.): ').strip()
            count = float(input('Currently in stock (Count): '))
            cost = float(input('Dollar cost per unit: '))
        except ValueError:
            print("Invalid input for Count or Cost. Please enter a number.")
            continue

        r = api_req('POST', T_INGS,
                     data={'name': name, 'measure': measure, 'count': count, 'cost': cost},
                     extra_headers={'Prefer': 'resolution=merge-duplicates'})
        if r.status_code in (200, 201, 204):
            print(name + " added/updated!")
        else:
            print("Error: " + r.text)

        while True:
            repeat = input('Add another item? (Y/N): ').strip().upper()
            if repeat in ('Y', 'YES'):
                break
            elif repeat in ('N', 'NO'):
                print('\n-Current Inventory-')
                r = api_req('GET', T_INGS)
                for funcrow in r.json():
                    print(funcrow)
                return
            else:
                print("Invalid choice. Enter Y or N.")


def removeFunction():
    print("\n-Remove Ingredient from Inventory-")
    whatDelete = input('Ingredient name to remove: ').strip()

    # Check if exists first
    r = api_req('GET', T_INGS, params={'name': 'eq.' + whatDelete, 'select': 'name'})
    exists = len(r.json()) > 0

    if not exists:
        print("No ingredient named '" + whatDelete + "' found.")
    else:
        api_req('DELETE', T_INGS, params={'name': 'eq.' + whatDelete},
                extra_headers={'Prefer': 'return=representation'})
        print(whatDelete + " has been removed.")

    print('\n-Current Inventory-')
    r = api_req('GET', T_INGS)
    for funcrow in r.json():
        print(funcrow)


def addRecipeFunction():
    print("\n-Add New Recipe-")
    recipeName = input('Recipe name: ').strip()
    instructions = input('Cooking instructions: ').strip()

    r = api_req('POST', T_RECIPES,
                data={'recipe_name': recipeName, 'instructions': instructions},
                extra_headers={'Prefer': 'return=representation'})
    if r.status_code == 409:
        print("A recipe named '" + recipeName + "' already exists.")
        return
    if r.status_code != 201:
        print("Error creating recipe: " + r.text)
        return

    recipeId = r.json()[0]['recipe_id']
    print("Recipe '" + recipeName + "' added (ID: " + str(recipeId) + ").")

    while True:
        ingName = input('\nIngredient for recipe: ').strip()

        r = api_req('GET', T_INGS, params={'name': 'eq.' + ingName, 'select': 'name,measure,count'})
        ingData = r.json()
        if not ingData:
            print("Ingredient '" + ingName + "' not found in inventory.")
            continue

        ingredientMeasure = ingData[0]['measure']
        currentStock = ingData[0]['count']

        if currentStock <= 0:
            print("WARNING: You currently have " + str(currentStock) + " " +
                  ingredientMeasure + " of " + ingName)

        try:
            quantity = float(input("Quantity needed (" + ingredientMeasure + "): "))
        except ValueError:
            print("Invalid number.")
            continue

        r = api_req('POST', T_RECIPE_INGS,
                    data={'recipe_id': recipeId, 'ingredient_name': ingName,
                          'quantity_needed': quantity, 'measure': ingredientMeasure})
        if r.status_code in (200, 201, 204):
            print(ingName + " (" + str(quantity) + " " + ingredientMeasure +
                  ") added to " + recipeName)
        else:
            print("Error: " + r.text)
            continue

        while True:
            repeat = input('Add another ingredient? (Y/N): ').strip().upper()
            if repeat in ('Y', 'YES'):
                break
            elif repeat in ('N', 'NO'):
                print("\nRecipe '" + recipeName + "' created successfully!")
                return
            else:
                print("Invalid choice. Enter Y or N.")


def showRecipes():
    print("\n-Current Recipes-")
    r = api_req('GET', T_RECIPES)
    recipes = r.json()

    if not recipes:
        print("No recipes found.")
        return

    for recipe in recipes:
        print("\nID: " + str(recipe['recipe_id']) + " | Name: " + recipe['recipe_name'])
        print("Instructions: " + recipe['instructions'])

        print("-Ingredients-")
        r2 = api_req('GET', T_RECIPE_INGS,
                     params={'recipe_id': 'eq.' + str(recipe['recipe_id']),
                             'select': 'ingredient_name,quantity_needed,measure'})
        for item in r2.json():
            print("  - " + str(item['quantity_needed']) + " " + item['measure'] +
                  " of " + item['ingredient_name'])


def deleteRecipeFunction():
    print("\n-Delete Recipe-")
    r = api_req('GET', T_RECIPES, params={'select': 'recipe_id,recipe_name'})
    recipes = r.json()

    if not recipes:
        print("No recipes to delete.")
        return

    for recipe in recipes:
        print("ID: " + str(recipe['recipe_id']) + ", Name: " + recipe['recipe_name'])

    whatDelete = input('Recipe name to delete: ').strip()

    r = api_req('DELETE', T_RECIPES,
                params={'recipe_name': 'eq.' + whatDelete},
                extra_headers={'Prefer': 'return=representation'})
    deleted = r.json() if r.status_code == 200 else []
    if deleted:
        print("Recipe '" + whatDelete + "' has been removed.")
    else:
        print("No recipe named '" + whatDelete + "' found.")

    print("\n-Remaining Recipes-")
    r = api_req('GET', T_RECIPES, params={'select': 'recipe_id,recipe_name'})
    for row in r.json():
        print("ID: " + str(row['recipe_id']) + ", Name: " + row['recipe_name'])


def checkRecipeFunction():
    print("\n-Check Recipe vs Inventory-")
    r = api_req('GET', T_RECIPES, params={'select': 'recipe_id,recipe_name'})
    recipes = r.json()

    if not recipes:
        print("No recipes found.")
        return

    for recipe in recipes:
        print("ID: " + str(recipe['recipe_id']) + ", Name: " + recipe['recipe_name'])

    recipeName = input("\nRecipe name to check: ").strip()

    r = api_req('GET', T_RECIPES, params={'recipe_name': 'eq.' + recipeName})
    recipeData = r.json()
    if not recipeData:
        print("No recipe named '" + recipeName + "' found.")
        return

    recipe = recipeData[0]
    recipeId = recipe['recipe_id']
    print("\n=== Recipe: " + recipe['recipe_name'] + " ===")
    print("Instructions: " + recipe['instructions'])

    r = api_req('GET', T_RECIPE_INGS,
                params={'recipe_id': 'eq.' + str(recipeId),
                        'select': 'ingredient_name,quantity_needed,measure,ingredient_table(count,cost)'})
    ingredients = r.json()

    if not ingredients:
        print("No ingredients found for this recipe.")
        return

    totalCost = 0.0
    missingCost = 0.0
    shoppingList = []
    allAvailable = True

    print("\n--- Inventory Comparison ---")
    print(f"{'Ingredient':<20} {'Need':<12} {'Have':<12} {'Missing':<12} {'Cost':<10}")
    print("-" * 66)

    for item in ingredients:
        ingName = item['ingredient_name']
        qtyNeeded = item['quantity_needed']
        measure = item['measure']
        stock = item['ingredient_table']['count']
        cost = item['ingredient_table']['cost']

        missing = max(0.0, qtyNeeded - stock)
        ingCost = qtyNeeded * cost
        ingMissingCost = missing * cost
        totalCost += ingCost
        missingCost += ingMissingCost

        needStr = str(qtyNeeded) + " " + measure
        haveStr = str(stock) + " " + measure
        missingStr = str(round(missing, 2)) + " " + measure if missing > 0 else "None"
        costStr = "${:.2f}".format(ingCost)

        print(f"{ingName:<20} {needStr:<12} {haveStr:<12} {missingStr:<12} {costStr:<10}")

        if missing > 0:
            allAvailable = False
            shoppingList.append((ingName, missing, measure, ingMissingCost))

    print("-" * 66)
    print("\n--- Recipe Cost Estimation ---")
    print("  Total recipe cost (all ingredients): ${:.2f}".format(totalCost))

    if allAvailable:
        print("\n--- Shopping List ---")
        print("  You have all ingredients needed! Nothing to buy.")
    else:
        print("\n--- Shopping List ---")
        print(f"{'Ingredient':<20} {'Qty to Buy':<12} {'Cost':<10}")
        print("-" * 42)
        for ingName, qty, measure, cost in shoppingList:
            print(f"{ingName:<20} {qty:.2f} {measure:<6} ${cost:.2f}")
        print("-" * 42)
        print(f"{'Total to spend:':<33} ${missingCost:.2f}")


while True:
    print("\n=== MAIN MENU ===")
    print("I - Ingredient Menu")
    print("R - Recipe Menu")
    print("X - Exit Program")

    choice = input("Choice: ").strip().upper()

    if choice == "I":
        while True:
            sub = input("\nIngredient Menu: Change (C) or Delete (D)? ").strip().upper()

            if sub == "C":
                entryFunction()
                break
            elif sub == "D":
                removeFunction()
                break
            else:
                print("Invalid choice. Enter C or D.")

    elif choice == "R":
        while True:
            sub = input("\nRecipe Menu: Add (A), View (V), Delete (D), Check (C)? ").strip().upper()

            if sub == "A":
                addRecipeFunction()
                break
            elif sub == "V":
                showRecipes()
                break
            elif sub == "D":
                deleteRecipeFunction()
                break
            elif sub == "C":
                checkRecipeFunction()
                break
            else:
                print("Invalid choice. Enter A, V, D, or C.")

    elif choice == "X":
        print("\n-Exiting Program-")
        break

    else:
        print("Invalid choice. Enter I, R, or X.")

print("\n-Closing Program-")
try:
    input("Press Enter to exit...")
except EOFError:
    pass
print("Supabase API session closed")
