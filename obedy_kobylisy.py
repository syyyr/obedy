#!/usr/bin/env python3
import base64
import locale
import os
import re
import sys
import time
from collections import OrderedDict
from datetime import date, timedelta
from io import BytesIO
from json import dumps as jsonDump
from PIL import Image, ImageOps

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC

import requests_cache
import requests
from bs4 import BeautifulSoup

NORMAL = '\u001b[0m'
BOLD = '\u001b[1m'
URL_START = '\u001b]8;;'
URL_SEP = '\u001b\\'
URL_END = '\u001b]8;;\u001b\\'
ITALIC = '\u001b[3m'
GREY = '\u001b[38;5;7m'
BLUE = '\u001b[34m'
DOUBLE_UNDERLINE = '\u001b[21m'

CACHE_TIMEOUT = 60 * 30
CACHE_DIR = os.getenv('XDG_CACHE_HOME') if os.getenv('XDG_CACHE_HOME') else os.path.expanduser('~/.cache')

requests_cache.install_cache(os.path.join(CACHE_DIR, 'obedy_kobylisy/requests'), 'filesystem', serializer='json', expire_after=CACHE_TIMEOUT) # expire after 30 minutes
SCREENSHOT_CACHE_FILE_CIHELNA = os.path.join(CACHE_DIR, 'obedy_kobylisy/screenshot_cihelna')
SCREENSHOT_CACHE_FILE_VYHLIDKA = os.path.join(CACHE_DIR, 'obedy_kobylisy/screenshot_vyhlidka')
locale.setlocale(locale.LC_TIME, 'cs_CZ.UTF-8') # You better have this locale installed lmao
ALL_RESTAURANTS = ['blekoti', 'kozlovna', 'cihelna', 'soucku', 'vyhlidka']
CIHELNA_URL = 'https://ucihelny.cz'
VYHLIDKA_URL = 'https://steakyzlatavyhlidka.cz/'

def wait_for_elem(browser, locator):
    try:
        return WebDriverWait(browser, 10).until(EC.presence_of_element_located(locator))
    except TimeoutException:
        return None

def resToJson(input_arg):
    res = {}
    res['restaurant'] = input_arg[0]
    # Menu has to be a list - JSON can't preserve order otherwise
    res['menu'] = []
    for [day, meals] in input_arg[1].items():
        res['menu'].append({'day': str(day), 'meals': meals})

    res['source_url'] = input_arg[2]
    return jsonDump(res)

def impl_menicka(restaurant_id, correction_func):
    page_url = f'https://www.menicka.cz/tisk.php?restaurace={restaurant_id}'
    page_content = requests.get(page_url, timeout=5000).text
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
            if meal_name in (
                'Polévka',
                'Hlavní Jídla',
                'Hlavní Jidla',
                'Hlavní jídla',
                'Hlavní jídla:',
                'Hlavní jídla :',
                'Speciality:',
                'Specialita:',
                'Specialita',
                'Dezerty',
                'Saláty',
                'Specialita zahradnického centra',
                'Šéfkuchař doporučuje',
                'Bezmasá jídla',
                'Gril',
                'Minutka'
            ):
                continue
            # Get rid of unnecessary information about the meal.
            meal_name = re.sub(r'(\d+-)?\d+ ?g', '', meal_name) # g
            meal_name = re.sub(r'\(?\d+ ?ks\)?(, )?', '', meal_name) # ks
            meal_name = re.sub(r'\d, ?\d+l?', '', meal_name) # liters of soup
            meal_name = re.sub(r'^\s+', '', meal_name) # leading space
            meal_name = re.sub(r'\s+$', '', meal_name) # Trailing space
            meal_name = re.sub(' +', ' ', meal_name) # repeating spaces

            meal_price_tag = meal_tag.find('td', attrs={'class': 'prize'})
            corrected = correction_func(meal_name, meal_price_tag.text)
            if corrected is None or corrected[0][0] == '':
                continue

            for (meal_name_corrected, meal_price_corrected) in corrected:
                meals.append({'name': meal_name_corrected, 'price': meal_price_corrected})

        res[day] = []
        # Remove duplicates
        for meal in meals:
            if meal not in res[day]:
                res[day].append(meal)

    return (res, page_url)

def default_correction_func(name, price):
    return [(name, price)]

def blekoti():
    def func(name, price):
        if name in ('Steaky přímo z grilu', 'Steaky přímo z venkovního grilu'):
            return None

        if func.menu_save is not None:
            name = f'{func.menu_save} {name}'
            func.menu_save = None

        # Meal is sometimes on two rows
        if 'Pro tento den nebylo zadáno menu' not in name and price == '':
            func.menu_save = name
            return None

        name = re.sub(r'HK', 'houskový knedlík', name)
        name = re.sub(r'" +(\S*) +"', lambda m: f'"{m.group(1)}"', name)
        name = re.sub(r'(")(\S)(\S*)', lambda m: m.group(1) + m.group(2) + m.group(3).lower(), name)
        name = re.sub(r', -', ',', name)
        name = re.sub(r',\)', ')', name)
        # Do not shout.
        name = re.sub(r'(\w)(\w*)', lambda m: m.group(1) + m.group(2).lower(), name)
        return [(name, price)]

    func.menu_save = None

    return ('U Blekotů',) + impl_menicka(2421, func)

def cihelna():
    def func(name, price):
        if name == 'dcl Malinovka':
            name = '2 dcl malinovka'

        if func.menu_save is not None:
            name = f'{func.menu_save} {name}'
            func.menu_save = None
        if price != "":
            name = re.sub(f' {re.sub(" Kč", "", price)}', '', name)

        # Sometimes, the price is in the meal name.
        match = re.search(r' (\d+) Kč$', name)
        if match is not None:
            name = re.sub(match.re, '', name)
            price = match.group(1) + ' Kč'

        # Daily menu is sometimes on two rows
        if 'Polední menu' in name and price == '':
            func.menu_save = name
            return None

        name = re.sub(r', -', ',', name)
        name = re.sub(r'Malinovka', 'malinovka', name)
        name = re.sub(r'Předkrm ', '', name)
        name = re.sub(r'([Pp])(olední menu)-? ?([^:])', r'P\2: \3', name)
        name = re.sub(r'([^ ])"(.+)"', r'\1 "\2"', name)
        name = re.sub(r'"(.+)"([^ ,])', r'"\1" \2', name)
        name = re.sub(r'housk\.', r'houskový', name)
        name = re.sub(r'kn\.', r'knedlík', name)
        name = re.sub(r'b\. k\.', r'bez kosti', name)
        name = re.sub(r'om\.', r'omáčka', name)
        name = re.sub(r'tat\.', r'tatarská', name)
        name = re.sub(r'opeč\.', r'opečený', name)
        name = re.sub(r'br\.', r'bramborová', name)
        name = re.sub(r'uz\.', r'uzeným', name)
        name = re.sub(r'smet-', r'smetanovo-', name)
        name = re.sub(r'červ\. zelí', r'červené zelí', name)
        name = re.sub(r'tatar\. omáčka', r'tatarská omáčka', name)
        name = re.sub(r'cibul\. kroužky', r'cibulové kroužky', name)
        name = re.sub(r'angl\. slaninou', r'anglickou slaninou', name)
        name = re.sub(r'bram\. kaše', r'bramborová kaše', name)

        # Do not shout.
        name = re.sub(r'(\S)(\S*)', lambda m: m.group(1) + m.group(2).lower(), name)
        return [(name, price)]

    func.menu_save = None

    menicka = impl_menicka(5879, func)
    return ('U Cihelny',) + menicka

def kozlovna():
    def func(name, price):
        # Sometimes, the salad is on the same row.
        dual_entry_match = re.match(r'(.+) (\d+),? ?-? ?(.+)', name)
        if dual_entry_match is not None:
            return [
                (dual_entry_match.group(1), dual_entry_match.group(2) + " Kč"),
                (dual_entry_match.group(3), price)
            ]

        name = re.sub(r'Dezert - ', '', name)
        name = re.sub(r'kus-kus', 'kuskus', name)
        name = re.sub(r'Bez lepku', '(bez lepku)', name)
        name = re.sub(r'MENU:?', 'Polední menu:', name)
        return [(name, price)]
    return ('Kozlovna Almara',) + impl_menicka(4165, func)

def soucku():
    def func(name, price):
        if re.search('vlastních krabiček', name) is not None:
            return None

        # Do not shout.
        name = re.sub(r'(\S)(\S*)', lambda m: m.group(1) + m.group(2).lower(), name)

        # Add spaces around plus signs.
        name = re.sub(r'(\+)(\S)', r'\1 \2', name)
        name = re.sub(r'(\S)(\+)', r'\1 \2', name)
        name = re.sub(r'br\. knedlík', r'bramborový knedlík', name)
        name = re.sub(r'br\. kaše', r'bramborová kaše', name)
        name = re.sub(r'led\. salát', r'ledový salát', name)
        name = re.sub(r'Slaát', r'salát', name)
        name = re.sub(r'dom\.', r'domácí', name)
        name = re.sub(r'vař\.', r'vařený', name)
        name = re.sub(r'olom\.', r'olomoucký', name)
        name = re.sub(r'vepř\.', r'vepřový', name)
        name = re.sub(r'rest\.', r'restované', name)
        name = re.sub(r'gril\. (.* prso)', r'grilované \1', name)
        name = re.sub(r'červ\. cibule', r'červená cibule', name)
        name = re.sub(r'trh\. kachním', r'trhaným kachním', name)
        name = re.sub(r'uz\. krkovička', r'uzená krkovička', name)
        name = re.sub(r'kuř\. maso', r'kuřecí maso', name)
        name = re.sub(r'gril\. hermelín', r'grilovaný hermelín', name)
        name = re.sub(r'uz\. sýr', r'uzený sýr', name)
        name = re.sub(r'/$', r'', name)

        # Sometimes, the price is in the meal name.
        match = re.search(r' /(\d+)$|(\d+), -kč$', name)
        if match is not None:
            name = re.sub(match.re, '', name)
            price = match.group(1) or match.group(2) + ' Kč'

        # Add spaces around plus signs.
        name = re.sub(r' /$', '', name)

        # Fix typo
        name = re.sub(r'^Meu', 'Menu', name)

        name = re.sub(r'^Menu (\d)([^:])', r'Menu \1:\2', name)

        name = re.sub(r'polévka', 'Polévka', name)
        name = re.sub(r'^Specialita(\S)', lambda m: m.group(1).upper(), name)

        # Sometimes, two meals are on the same row.
        dual_entry_match = re.match(r'(.+) (\d{2,}) (.+)', name)
        if dual_entry_match is not None:
            return [
                (dual_entry_match.group(1), dual_entry_match.group(2) + " Kč"),
                (dual_entry_match.group(3), price)
            ]

        # Sometimes, two daily menus are on the same line
        two_daily_menus_match = re.match(r'menu (\d).*menu (\d)', name, flags=re.IGNORECASE)
        if two_daily_menus_match is not None:
            menu_one = two_daily_menus_match.group(1)
            menu_two = two_daily_menus_match.group(2)

            # Try separating the meals via polévka.
            two_daily_menus_match = re.match(r'.*(polévka.*).*(polévka.*)', name, flags=re.IGNORECASE)
            if two_daily_menus_match is not None:
                return [
                    (f'Menu {menu_one}: {two_daily_menus_match.group(1).capitalize()}', price),
                    (f'Menu {menu_two}: {two_daily_menus_match.group(2).capitalize()}', price),
                ]

            # If that doesn't work, separate by searching for a capital letter. That should be start of the meal name.
            two_daily_menus_match = re.match(r'.*(Polévka.*).*([A-Z].*)', name)
            if two_daily_menus_match is not None:
                return [
                    (f'Menu {menu_one}: {two_daily_menus_match.group(1)}', price),
                    (f'Menu {menu_two}: Polévka + {two_daily_menus_match.group(2)}', price),
                ]

        return [(name, price)]

    return ('U Součků',) + impl_menicka(2457, func)

def vyhlidka_screenshot():
    page_content = requests.get(VYHLIDKA_URL, timeout=5000).text
    soup = BeautifulSoup(page_content, 'html.parser')
    source = soup.find('source', {'srcset': re.compile(r'/ws/media-library/[a-z0-9]+/(jidelni-listek-)?.+.webp')})
    img_url = f'{VYHLIDKA_URL}{source["srcset"]}'
    response = requests.get(img_url, timeout=5000)

    match_date = re.search(r'[^0-9]+(\d+)\.(\d+)\.(\d+)\.webp', source["srcset"])
    if match_date is not None:
        day = date(int(match_date.group(3)) + 2000, int(match_date.group(2)), int(match_date.group(1)))
    else:
        day = None
    if os.path.exists(SCREENSHOT_CACHE_FILE_VYHLIDKA) and os.path.getmtime(SCREENSHOT_CACHE_FILE_VYHLIDKA) + CACHE_TIMEOUT > time.time():
        with open(SCREENSHOT_CACHE_FILE_VYHLIDKA, mode='r') as f:
            return (f.read(), VYHLIDKA_URL, day)

    # Crop white border
    webp = Image.open(BytesIO(response.content))
    invert_im = webp.convert("RGB")
    invert_im = ImageOps.invert(webp)
    x0, y0, x1, y1 = invert_im.getbbox()
    webp = webp.crop((x0 + 30, y0 + 275, x1 - 15, y1))

    width, height = webp.size
    webp = webp.resize((int(width * 0.75), int(height * 0.75)))

    png = BytesIO()
    webp.save(png, "png")
    screenshot = base64.b64encode(png.getvalue()).decode('utf-8')
    with open(SCREENSHOT_CACHE_FILE_VYHLIDKA, mode='w') as f:
        f.write(screenshot)
    return (screenshot, VYHLIDKA_URL, day)

def vyhlidka():
    screenshot, source, day = vyhlidka_screenshot()
    menicka = OrderedDict()
    monday = date.today() - timedelta(days=date.today().weekday())
    for k in [monday + timedelta(days=i) for i in range(5)]:
        if day == k or day is None:
            menicka[k] = [{'screenshot': screenshot}]
        else:
            menicka[k] = [{'name': 'Pro tento den nebylo zadáno menu.', 'price': ''}]

    menicka = (menicka, source)

    return ('Steaky na Zlaté vyhlídce',) + menicka

def main(requested_restaurants, weekday):
    for restaurant in requested_restaurants:
        if restaurant not in globals():
            if weekday_to_number(restaurant) is None:
                print(f'Neznámá restaurace "{restaurant}".')
                return 1

            requested_restaurants = ALL_RESTAURANTS
            weekday = weekday_to_number(restaurant)

    weekly_menus = [globals()[restaurant]() for restaurant in requested_restaurants if restaurant in globals()]
    daily_menus = [(name, list(weekly_menus.items())[weekday], _) for (name, weekly_menus, _) in weekly_menus]

    name_width = 0
    price_width = 0

    for (restaurant, (menu_date, menu), _) in daily_menus:
        if len(menu) == 0 or 'screenshot' in menu[0]:
            continue
        longest_meal_name = max(menu, key=lambda it: len(it['name']))['name']
        longest_price_name = max(menu, key=lambda it: len(it['price']))['price']
        name_width = max(len(longest_meal_name), len('Název'), name_width)
        price_width = max(len(longest_price_name), len('Cena'), price_width)

    format_string = '{:3}' + f'{{:{name_width + 1}}} {{:>{price_width + 1}}}'

    for (restaurant, (menu_date, menu), url) in daily_menus:
        date_str = menu_date.strftime("%A %e. %B")
        print(f'{BOLD}{URL_START}{url}{URL_SEP}{restaurant}{URL_END}{NORMAL} {ITALIC}{GREY}{date_str}{NORMAL}')

        if len(menu) != 0 and 'screenshot' in menu[0]:
            header_str = format_string.format("", "", "")
            print(f'{DOUBLE_UNDERLINE}{BLUE}{header_str}{NORMAL}')
            if os.getenv('TERM') == 'xterm-kitty':
                i = 0
                data = menu[0]['screenshot']
                while data:
                    chunk, data = data[:4096], data[4096:]
                    if len(chunk) < 4096:
                        sys.stdout.write('\u001b_Gm=0;')
                    elif i == 0:
                        sys.stdout.write('\u001b_Gm=1,a=T,f=100;')
                    else:
                        sys.stdout.write('\u001b_Gm=1;')
                    sys.stdout.write(chunk)
                    sys.stdout.write('\u001b\\')
                    i = i + 1
                sys.stdout.write('\n')
            continue

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
