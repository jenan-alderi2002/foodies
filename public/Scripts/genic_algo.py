from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict, Optional, List
import pandas as pd
import re

app = FastAPI()

# Read data from the file
file_path = 'DataFood2.csv'
data = pd.read_csv(file_path, encoding='utf-8')

# Convert each meal to a gene representation
def meal_to_gene(row):
    meal_name = row['اسم الوجبة']
    components = [component.strip().lower().strip('"') for component in re.split(r',|،', row['المكونات'])]

    primary_components = [comp.strip().replace(' ', '').lower().strip('"') for comp in row['مكونات اساسية'].split(',')]
    secondary_components = [comp.strip().lower().strip('"') for comp in row['مكونات فرعية'].split(',')]

    def extract_quantity(quantity_str):
        if isinstance(quantity_str, str):
            match = re.search(r'[\d.]+', quantity_str)
            return float(match.group()) if match else None
        else:
            return None

    def extract_duration(duration_str):
        if isinstance(duration_str, str):
            match = re.search(r'\d+', duration_str)
            return int(match.group()) if match else None
        elif isinstance(duration_str, (int, float)):
            return int(duration_str)
        else:
            return None

    def extract_num_people(num_people_str):
        if isinstance(num_people_str, str):
            matches = re.findall(r'\d+', num_people_str)
            if len(matches) == 1:
                return int(matches[0])
            elif len(matches) > 1:
                return int(sum(map(int, matches)) / len(matches))
        return None

    quantities = [extract_quantity(q) for q in row['الكمية'].split(',')]
    duration = extract_duration(row['الوقت المستهلك'])
    num_people = extract_num_people(row['عدد الاشخاص'])
    dish_type = row['نوع الطبق']

    gene = {
        'meal_name': meal_name,
        'components': components,
        'primary_components': primary_components,
        'secondary_components': secondary_components,
        'quantities': quantities,
        'duration': duration,
        'num_people': num_people,
        'dish_type': dish_type,
    }
    return gene

# Convert all rows to genes using apply
genes = data.apply(meal_to_gene, axis=1).tolist()

class UserInput(BaseModel):
    components: Dict[str, float]
    num_people: int
    similar_meals: Optional[bool] = False
    limit_time: Optional[bool] = False
    max_time: Optional[int] = None

def fitness(meal_gene, user_components):
    meal_components = [component.strip().lower() for component in meal_gene['components']]
    matching_components = set(meal_components) & set(user_components.keys())
    return len(matching_components) / len(meal_components) if len(meal_components) > 0 else 0


def get_best_meals(genes, user_components, num_people, similar_meals, limit_time=False, max_time=None, top_n=5):
    best_meals = []

    for gene in genes:
        if limit_time:
            adjusted_gene = adjust_quantities(gene, user_components, num_people, max_time)
        else:
            adjusted_gene = adjust_quantities(gene, user_components, num_people)

        if adjusted_gene is None:
            continue

        if similar_meals:
            if all(comp in user_components.keys() for comp in adjusted_gene['primary_components']):
                fitness_score = fitness(adjusted_gene, user_components)
                if fitness_score > 0:
                    missing_components = set(adjusted_gene['components']) - set(user_components.keys())
                    best_meals.append((adjusted_gene['meal_name'], adjusted_gene, missing_components))
        else:
            fitness_score = fitness(adjusted_gene, user_components)
            if fitness_score > 0:
                missing_components = set(adjusted_gene['components']) - set(user_components.keys())
                best_meals.append((adjusted_gene['meal_name'], adjusted_gene, missing_components))

    sorted_meals = sorted(best_meals, key=lambda x: fitness(x[1], user_components), reverse=True)
    return sorted_meals[:top_n]



def adjust_quantities(meal_gene, user_components, num_people, max_time=None, used_components=None):
    if not all(comp in user_components for comp in meal_gene['primary_components']):
        return None

    if max_time is not None and meal_gene['duration'] is not None:
        if meal_gene['duration'] > max_time:
            return None

    adjusted_quantities = []
    original_quantities = meal_gene['quantities']
    original_num_people = meal_gene['num_people']
    note = None

    if original_num_people is None:
        original_num_people = 1

    scaling_factors = []
    excess_components = {}  # To track excess components

    for component, original_quantity in zip(meal_gene['components'], original_quantities):
        if component in user_components and original_quantity is not None:
            available_quantity = user_components[component]
            if used_components and component in used_components:
                available_quantity -= used_components[component]
            if available_quantity > 0:
                scaling_factors.append(available_quantity / original_quantity)
            else:
                scaling_factors.append(0)

    if scaling_factors:
        scaling_factor = min(scaling_factors)
    else:
        scaling_factor = 0

    adjusted_num_people = int(original_num_people * scaling_factor)

    if adjusted_num_people < num_people:
        return None

    for component, quantity in zip(meal_gene['components'], original_quantities):
        if quantity is not None:
            adjusted_quantity = quantity * scaling_factor
            adjusted_quantities.append(adjusted_quantity)
            if adjusted_quantity < user_components.get(component, 0):
                excess_components[component] = user_components[component] - adjusted_quantity
        else:
            adjusted_quantities.append(None)

    adjusted_gene = meal_gene.copy()
    adjusted_gene['quantities'] = adjusted_quantities
    adjusted_gene['num_people'] = adjusted_num_people
    adjusted_gene['excess_components'] = excess_components  # Add excess components info

    return adjusted_gene

def get_meals(genes, user_components, total_people, max_time=None, similar_meals=False, limit_time=False):
    def find_meals(genes, used_components, used_primary_components, total_people, start_index, total_duration=0):
        results = []

        for i in range(start_index, len(genes)):
            if not similar_meals and any(comp in used_primary_components for comp in genes[i]['primary_components']):
                continue

            adjusted_gene = adjust_quantities(genes[i], user_components, 1, max_time, used_components.copy())

            if adjusted_gene is None:
                continue

            if limit_time and (total_duration + adjusted_gene['duration']) > max_time:
                continue

            new_used_components = used_components.copy()
            new_used_primary_components = used_primary_components.copy()
            for component, quantity in zip(adjusted_gene['components'], adjusted_gene['quantities']):
                if component in user_components:
                    new_used_components[component] = new_used_components.get(component, 0) + quantity

            new_used_primary_components.update(adjusted_gene['primary_components'])

            if adjusted_gene['num_people'] >= total_people:
                results.append([(adjusted_gene['meal_name'], adjusted_gene)])
            else:
                sub_results = find_meals(
                    genes,
                    new_used_components,
                    new_used_primary_components,
                    total_people - adjusted_gene['num_people'],
                    i + 1,
                    total_duration + adjusted_gene['duration']
                )
                for sub_result in sub_results:
                    results.append([(adjusted_gene['meal_name'], adjusted_gene)] + sub_result)

        return results

    chosen_meals = find_meals(genes, {}, set(), total_people, 0)

    best_combinations = []
    for meal_combination in chosen_meals:
        total_people_adjusted = sum(meal['num_people'] for _, meal in meal_combination)
        total_duration = sum(meal['duration'] for _, meal in meal_combination)
        meal_combination_notes = []
        
        # Check for excess components
        total_used_components = {}
        for _, meal in meal_combination:
            for component, quantity in zip(meal['components'], meal['quantities']):
                if component in user_components:
                    total_used_components[component] = total_used_components.get(component, 0) + quantity

        for component, total_used_quantity in total_used_components.items():
            if total_used_quantity > user_components.get(component, 0):
                excess_quantity = total_used_quantity - user_components[component]
                meal_combination_notes.append(f"{component}: reduce by {excess_quantity}")

        best_combinations.append((meal_combination, total_people_adjusted, total_duration, meal_combination_notes))

    return best_combinations


@app.post("/get_best_meals/")
def get_best_meals_endpoint(user_input: UserInput):
    best_meals = get_best_meals(
        genes,
        user_input.components,
        user_input.num_people,
        user_input.similar_meals,
        user_input.limit_time,
        user_input.max_time if user_input.limit_time else None
    )
    chosen_meals = get_meals(
        genes,
        user_input.components,
        user_input.num_people,
        user_input.max_time if user_input.limit_time else None,
        user_input.similar_meals,
        user_input.limit_time
    )

    response = {
        "best_meals": [],
        "chosen_meals": []
    }

    for meal_name, meal, missing_components in best_meals:
        meal_info = {
            "meal_name": meal_name,
            "adjusted_for": meal['num_people'],
            "cooking_time": meal['duration'],
            "missing_components": list(missing_components) if missing_components else "All components are available"
        }
        response["best_meals"].append(meal_info)

    for meal_combination, total_people_adjusted, total_duration, notes in chosen_meals:
        meal_combination_info = {
            "total_people_adjusted": total_people_adjusted,
            "total_duration": total_duration,
            "meals": [],
            "notes": notes
        }
        for meal_name, meal in meal_combination:
            meal_info = {
                "meal_name": meal_name,
                "adjusted_for": meal['num_people'],
                "cooking_time": meal['duration']
            }
            meal_combination_info["meals"].append(meal_info)

        # Collect all components that should be reduced
        excess_components = set()
        for meal_name, meal in meal_combination:
            if meal.get('excess_components'):
                excess_components.update(meal['excess_components'].keys())

        if excess_components:
            meal_combination_info["notes"].append(f"Consider reducing the amount of the following components to avoid excess: {', '.join(excess_components)}")

        response["chosen_meals"].append(meal_combination_info)

    return response
