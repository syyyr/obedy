#!/usr/bin/env python3
import locale
import re
import sys
from collections import OrderedDict
from datetime import date
from json import dumps as jsonDump

import requests_cache
import requests
from bs4 import BeautifulSoup

NORMAL = '\u001b[0m'
BOLD = '\u001b[1m'
ITALIC = '\u001b[3m'
GREY = '\u001b[38;5;7m'
BLUE = '\u001b[34m'
DOUBLE_UNDERLINE = '\u001b[21m'

requests_cache.install_cache('~/.cache/obedy_kobylisy', 'filesystem', serializer='json', expire_after=60 * 30) # expire after 30 minutes
locale.setlocale(locale.LC_TIME, 'cs_CZ.UTF-8') # You better have this locale installed lmao
ALL_RESTAURANTS = ['blekoti', 'cihelna', 'kozlovna', 'soucku']

def resToJson(input_arg):
    res = {}
    res['restaurant'] = input_arg[0]
    # Menu has to be a list - JSON can't preserve order otherwise
    res['menu'] = []
    for [day, meals] in input_arg[1].items():
        res['menu'].append({'day': str(day), 'meals': meals})

    return jsonDump(res)

def impl_menicka(restaurant_id, correction_func):
    page_content = requests.get(f'https://www.menicka.cz/tisk.php?restaurace={restaurant_id}', timeout=5000).text
    soup = BeautifulSoup(page_content, 'html.parser')
    all_menus = soup.find_all('div', attrs={'class': 'content'})
    res = OrderedDict()

    for menu_tag in all_menus:
        date_tag = menu_tag.find('h2')
        match_date = re.match(r'[^ ]* (\d+)\.(\d+)\.(\d+)', date_tag.text)
        day = date(int(match_date.group(3)), int(match_date.group(2)), int(match_date.group(1)))
        meals = []
        for meal_tag in menu_tag.find_all('tr'):
            meal_name_tag = meal_tag.find('td', attrs={'class': 'food'})
            meal_name = meal_name_tag.text
            # Sometimes, there are bogus rows.
            if meal_name in ('Polévka', 'Hlavní jídla', 'Hlavní jídla:', 'Hlavní jídla :', 'Speciality:', 'Specialita:', 'Specialita', 'Dezerty'):
                continue
            # Get rid of unnecessary information about the meal.
            meal_name = re.sub(r'\d+g', '', meal_name) # g
            meal_name = re.sub(r'\d+ks', '', meal_name) # ks
            meal_name = re.sub(r'\d, \d+l', '', meal_name) # liters of soup
            meal_name = re.sub(r'^\s+', '', meal_name) # leading space
            meal_name = re.sub(r'\s+$', '', meal_name) # Trailing space
            meal_name = re.sub(' +', ' ', meal_name) # repeating spaces

            meal_price_tag = meal_tag.find('td', attrs={'class': 'prize'})
            corrected = correction_func(meal_name, meal_price_tag.text)
            if corrected is None:
                continue

            for (meal_name_corrected, meal_price_corrected) in corrected:
                meals.append({'name': meal_name_corrected, 'price': meal_price_corrected})

        res[day] = []
        # Remove duplicates
        for meal in meals:
            if meal not in res[day]:
                res[day].append(meal)

    return res

def default_correction_func(name, price):
    return [(name, price)]

def blekoti():
    def func(name, price):
        if name == 'Steaky přímo z venkovního grilu':
            return None

        name = re.sub(r'" +(\S*) +"', lambda m: f'"{m.group(1)}"', name)
        name = re.sub(r'(")(\S)(\S*)', lambda m: m.group(1) + m.group(2) + m.group(3).lower(), name)
        name = re.sub(r', -', ',', name)
        # Do not shout.
        name = re.sub(r'(\w)(\w*)', lambda m: m.group(1) + m.group(2).lower(), name)
        return [(name, price)]

    return ('U Blekotů', impl_menicka(2421, func))

def cihelna():
    def func(name, price):
        if price != "":
            name = re.sub(f' {re.sub(" Kč", "", price)}', '', name)
        name = re.sub(r', -', ',', name)
        name = re.sub(r'Malinovka', 'malinovka', name)
        name = re.sub(r'(Polední menu)', r'\1:', name)
        name = re.sub(r'([^ ])"(.+)"', r'\1 "\2"', name)
        name = re.sub(r'"(.+)"([^ ])', r'"\1" \2', name)
        # Do not shout.
        name = re.sub(r'(\S)(\S*)', lambda m: m.group(1) + m.group(2).lower(), name)
        return [(name, price)]

    return ('U Cihelny', impl_menicka(5879, func))

def kozlovna():
    def func(name, price):
        # Sometimes, the salad is on the same row.
        dual_entry_match = re.match(r'(.+) (\d+), - (.+)', name)
        if dual_entry_match is not None:
            return [
                (dual_entry_match.group(1), dual_entry_match.group(2) + " Kč"),
                (dual_entry_match.group(3), price)
            ]

        name = re.sub(r'Dezert - ', '', name)
        name = re.sub(r'Bez lepku', '(bez lepku)', name)
        return [(name, price)]
    return ('Kozlovna Almara', impl_menicka(4165, func))

def soucku():
    def func(name, price):
        # Do not shout.
        name = re.sub(r'(\S)(\S*)', lambda m: m.group(1) + m.group(2).lower(), name)

        # Add spaces around plus signs.
        name = re.sub(r'(\+)(\S)', r'\1 \2', name)
        name = re.sub(r'(\S)(\+)', r'\1 \2', name)

        # Sometimes, the price is in the meal name.
        match = re.search(r' /(\d+)$', name)
        if match is not None:
            name = re.sub(match.re, '', name)
            price = match.group(1) + ' Kč'

        # Add spaces around plus signs.
        name = re.sub(r' /$', '', name)

        # Fix typo
        name = re.sub(r'^Meu', 'Menu', name)

        name = re.sub(r'^Menu (\d)([^:])', r'Menu \1:\2', name)

        name = re.sub(r'^(\S)', lambda m: m.group(1).upper(), name)

        # Sometimes, two meals are on the same row.
        dual_entry_match = re.match(r'(.+) (\d{2,}) (.+)', name)
        if dual_entry_match is not None:
            return [
                (dual_entry_match.group(1), dual_entry_match.group(2) + " Kč"),
                (dual_entry_match.group(3), price)
            ]

        return [(name, price)]

    return ('U Součků', impl_menicka(2457, func))

def main(requested_restaurants, weekday):
    for restaurant in requested_restaurants:
        if restaurant not in globals():
            if weekday_to_number(restaurant) is None:
                print(f'Neznámá restaurace "{restaurant}".')
                return 1

            requested_restaurants = ALL_RESTAURANTS
            weekday = weekday_to_number(restaurant)

    weekly_menus = [globals()[restaurant]() for restaurant in requested_restaurants if restaurant in globals()]
    daily_menus = [(name, list(weekly_menus.items())[weekday]) for (name, weekly_menus) in weekly_menus]

    name_width = 0
    price_width = 0

    for (restaurant, (menu_date, menu)) in daily_menus:
        longest_meal_name = max(menu, key=lambda it: len(it['name']))['name']
        longest_price_name = max(menu, key=lambda it: len(it['price']))['price']
        name_width = max(len(longest_meal_name), len('Název'), name_width)
        price_width = max(len(longest_price_name), len('Cena'), price_width)

    format_string = '{:3}' + f'{{:{name_width + 1}}} {{:>{price_width + 1}}}'

    for (restaurant, (menu_date, menu)) in daily_menus:
        date_str = menu_date.strftime("%A %e. %B")
        print(f'{BOLD}{restaurant}{NORMAL} {ITALIC}{GREY}{date_str}{NORMAL}')
        header_str = format_string.format("#", "Název", "Cena")
        print(f'{DOUBLE_UNDERLINE}{BLUE}{header_str}{NORMAL}')

        for count, meal in enumerate(menu):
            print(format_string.format(str(count + 1), meal['name'], meal['price']))

    return 0

def weekday_to_number(weekdayStr):
    return {'po': 0, 'út': 1, 'st': 2, 'čt': 3, 'pá': 4, 'ut': 1, 'ct': 3, 'pa': 4}[weekdayStr]

if __name__ == '__main__':
    if len(sys.argv) >= 2:
        requested_restaurants = [sys.argv[1]]
    else:
        requested_restaurants = ALL_RESTAURANTS

    if len(sys.argv) >= 3:
        weekdayStr = str(sys.argv[2])
        weekday = weekday_to_number(weekdayStr)
    else:
        weekday = date.today().weekday()
        if weekday > 4:
            weekday = 0
            print('O víkendu nejsou obědy. Ukazuji pondělí.')

    if weekday is None:
        print('Neznámý den: "' + weekdayStr + '". Podporované formáty: Pátek|pá|pa')
        sys.exit(1)

    code = main(requested_restaurants, weekday)
    sys.exit(code)
