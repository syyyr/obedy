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

requests_cache.install_cache('~/.cache/obedy_kobylisy', 'filesystem', serializer='json', expire_after=60 * 60 * 1) # expire after one hour

def resToJson(input):
    res = {}
    res['restaurant'] = input[0]
    # Menu has to be a list - JSON can't preserve order otherwise
    res['menu'] = []
    for [day, meals] in input[1].items():
        res['menu'].append({'day': str(day), 'meals': meals})

    return jsonDump(res)

def impl_menicka(restaurant_id):
    page_content = requests.get(f'https://www.menicka.cz/tisk.php?restaurace={restaurant_id}', timeout=5000).content
    soup = BeautifulSoup(page_content, 'html.parser')
    all_menus = soup.find_all('div', attrs={'class': 'content'})
    res = OrderedDict()

    for menu_tag in all_menus:
        date_tag = menu_tag.find('h2')
        match_date = re.match(r'[^ ]* (\d+)\.(\d+)\.(\d+)', date_tag.text)
        day = date(int(match_date.group(3)), int(match_date.group(2)), int(match_date.group(1)))
        res[day] = []
        for meal_tag in menu_tag.find_all('tr'):
            meal_name_tag = meal_tag.find('td', attrs={'class': 'food'})
            meal_name = meal_name_tag.text
            # Sometimes, there is a bogus row with "Polévka" in it.
            if meal_name == 'Polévka':
                continue
            # Get rid of unnecessary information about the meal.
            meal_name = re.sub(r'\d+g', '', meal_name) # g
            meal_name = re.sub(r'\d+ks', '', meal_name) # ks
            meal_name = re.sub(r'\d, \d+l', '', meal_name) # liters of soup
            meal_name = re.sub(r'^ +', '', meal_name) # leading space

            meal_price_tag = meal_tag.find('td', attrs={'class': 'prize'})
            res[day].append({'name': meal_name, 'price': meal_price_tag.text})

    return res

def blekoti():
    return ('U Blekotů', impl_menicka(2421))

def cihelna():
    return ('U Cihelny', impl_menicka(5879))

def kozlovna():
    return ('Kozlovna Almara', impl_menicka(4165))

def main():
    if 'blekoti' in sys.argv[1]:
        (restaurant, menu) = blekoti()
    elif 'cihelna' in sys.argv[1]:
        (restaurant, menu) = cihelna()
    elif 'kozlovna' in sys.argv[1]:
        (restaurant, menu) = kozlovna()
    else:
        print('První argument skriptu musí obsahovat jedno z těchto slov: "blekoti", "cihelna", "kozlovna"')
        return 1

    locale.setlocale(locale.LC_TIME, 'cs_CZ.UTF-8') # You better have this locale installed lmao
    if len(sys.argv) >= 3:
        weekdayStr = str(sys.argv[2])
        weekday = {'po': 0, 'út': 1, 'st': 2, 'čt': 3, 'pá': 4, 'ut': 1, 'ct': 3, 'pa': 4}[weekdayStr]
    else:
        weekday = date.today().weekday()

    if weekday is None:
        print('Neznámý den: "' + weekdayStr + '". Podporované formáty: Pátek|pá|pa')
        return 1

    (menu_date, menu) = list(menu.items())[weekday]

    name_width = max(len(max(menu, key=lambda index: len(index['name']))['name']), len('Název'))
    price_width = max(len(max(menu, key=lambda index: len(index['price']))['price']), len('Cena'))
    format_string = '{:3}' + f'{{:{name_width + 1}}} {{:>{price_width + 1}}}'

    print(BOLD + restaurant + NORMAL + ' ' + ITALIC + GREY + menu_date.strftime('%A') + ' ' + str(menu_date.day) + menu_date.strftime('. %B') + NORMAL)
    print(DOUBLE_UNDERLINE + BLUE + format_string.format('#', 'Název', 'Cena') + NORMAL)

    for count, meal in enumerate(menu):
        print(format_string.format(str(count + 1), meal['name'], meal['price']))

    return 0

if __name__ == '__main__':
    code = main()
    sys.exit(code)
