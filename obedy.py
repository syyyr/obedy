#!/bin/env python
from bs4 import BeautifulSoup
from collections import OrderedDict
from json import dumps as jsonDump
from datetime import date, datetime, timedelta
from os import environ
import locale
import re
import requests
import sys
import pprint

NORMAL = '\u001b[0m'
BOLD = '\u001b[1m'
ITALIC = '\u001b[3m'
GREY = '\u001b[38;5;7m'
BLUE = '\u001b[34m'
DOUBLE_UNDERLINE = '\u001b[21m'

ZOMATO_COOKIE = environ.get('ZOMATO_COOKIE')

def resToJson(input):
    res = {}
    res['restaurant'] = input[0]
    # Menu has to be a list - JSON can't preserve order otherwise
    res['menu'] = []
    for [day, meals] in input[1].items():
        res['menu'].append({'day': str(day), 'meals': meals})

    return jsonDump(res)

def blox():
    page = requests.get('http://www.blox-restaurant.cz/#!/page_obedy')
    soup = BeautifulSoup(page.content, 'html.parser')
    allTr = iter(soup.find(id='page_obedy').findAll('tr'))

    res = OrderedDict()
    match_date = re.match('Menu na týden (\d+)\.(\d+)\. - (\d+).(\d+)\.(\d+)', next(allTr).find('strong').text)
    current_date = date(int(match_date.group(5)), int(match_date.group(2)), int(match_date.group(1)))
    res[current_date] = []
    next(allTr) # Skip first - it's the day tag - to prevent advancing the date too soon

    for item in allTr:
        day_tag = item.find('strong')
        if day_tag is not None:
            current_date = current_date + timedelta(days=1)
            res[current_date] = []
            continue

        meals = item.find_all('td')
        if '\xa0' in meals[3].text: # Nonsense price -> we're already at the end
            break
        price = re.sub('[^0-9]', '', meals[3].text) # Blox formats price weirdly sometimes
        res[current_date].append({ 'name': meals[1].text, 'price': price + " Kč" })

    return ('Blox', res)

def country_life():
    monthToInt = {
        'ledna': 1,
        'února': 2,
        'března': 3,
        'dubna': 4,
        'května': 5,
        'června': 6,
        'července': 7,
        'srpna': 8,
        'září': 9,
        'října': 10,
        'listopadu': 11,
        'prosince': 12,
    }
    page = requests.get('https://www.countrylife.cz/mo-dejvice-restaurace')
    soup = BeautifulSoup(page.content, 'html.parser')
    menu = soup.find(text='Jídelní lístek na tento týden:').findNext('div').findAll('p')
    res = OrderedDict()
    for item in menu:
        if item.text == '' or item.text == '\xa0': # There are some bogus <p> elements
            continue

        day_tag = item.find('strong')
        if day_tag.text == 'Alergeny:': # This is the end
            break
        day_tag_sanitized = re.sub('\xa0', '', day_tag.text)
        match_date = re.match('.* (\d+)\. ([a-zěščřžýáíéúů]+)', day_tag_sanitized, flags=re.U)

        # Yeah, the year won't work at the end of the year, but I don't really care
        current_date = date(date.today().year, monthToInt[match_date.group(2)], int(match_date.group(1)))
        res[current_date] = []
        meals = item.text.split('\n')[1:] # Discard the first element - it's the day
        for count, meal in enumerate(meals):
            meal = re.sub('doporučujeme|NOVINKA', '', meal) # I don't care about this stuff
            match = re.match(r'([^\(]+)(\(.*\))*', meal)

            name = match.group(1)
            name = re.sub('\xa0', '', name)
            name = re.sub(' $', '', name)
            if name == '': # sometimes there is one more empty element, lmao
                break

            price = '39 Kč/porce' if count == 0 else '22 Kč/100 g' if datetime.now().hour > 16 else '27 Kč/100 g'
            res[current_date].append({ 'name': name, 'price': price })


    return ('Country life', res)

def husa():
    page = requests.get('http://www.potrefene-husy.cz/cz/dejvice-poledni-menu')
    soup = BeautifulSoup(page.content, 'html.parser')

    res = OrderedDict()
    header_with_date = soup.find('h2')
    match_date = re.match('od (\d+)\.(\d+)\.(\d+)', header_with_date.text)
    current_date = date(int(match_date.group(3)), int(match_date.group(2)), int(match_date.group(1)))

    monday_tag = soup.find('tr', text='Pondělí')
    res[current_date] = []

    menu = monday_tag.findAllNext('tr')
    for item in menu:
        day_tag = item.find('h3')
        if day_tag is not None:
            if current_date.weekday() == 4: # Friday - end
                break
            current_date = current_date + timedelta(days=1)
            res[current_date] = []
            continue
        tds = item.findAll('td')
        if len(tds) == 0: # bogus element between days
            continue
        name = tds[1].text
        name = name.replace(' *', '') # gluten-free - don't care
        name = name.replace('Tip šéfkuchaře: ', '') # don't care
        name = name.replace('\t', '') # bogus tab in name
        name = re.sub(' +', ' ', name)
        price = tds[2].text
        res[current_date].append({ 'name': name, 'price': price })

    return ('Potrefená husa', res)

def komousi():
    if ZOMATO_COOKIE is None:
        raise Exception('ZOMATO_COOKIE is not set')

    headers = {
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.117 Safari/537.36',
        'accept-language': 'en-US,en;q=0.9,cs-CZ;q=0.8,cs;q=0.7',
        'cookie': ZOMATO_COOKIE
    }
    page = requests.get('https://www.zomato.com/widgets/daily_menu.php?entity_id=16507625', headers=headers)
    soup = BeautifulSoup(page.content, 'html.parser')
    days = soup.findAll('div', attrs={'class': 'date'})

    res = OrderedDict()
    for day in days:
        date_tag = day.findNext('div', attrs={'class': 'left-div'})
        match_date = re.match('[^0-9]*(\d+)\.(\d+)\.(\d+)', date_tag.text)
        current_date = date(int(match_date.group(3)), int(match_date.group(2)), int(match_date.group(1)))
        res[current_date] = []

        meals = date_tag.findAllNext('div', attrs={'class': 'item'})
        meals_iter = iter(meals)
        for meal in meals_iter:
            name_tag = meal.find('div', attrs={'class': 'item-name'})
            match_name = re.match('[\t\n ]*(\d+ ?(g|ks)?)? *(.+)', name_tag.text)
            name = re.sub(' *$', '', match_name.group(3))

            price_tag = meal.find('div', attrs={'class': 'item-price'})
            match_price = re.match('[\t\n ]*(\d+)\xa0Kč', price_tag.text)
            if match_price is None: # The name can be split into two lines
                name_tag_next = name_tag.findNext('div', attrs={'class': 'item-name'})
                match_name_next = re.match('[\t\n ]*(\d+ ?(g|ks)?)? *(.+)', name_tag_next.text)
                name_next = re.sub(' *$', '', match_name_next.group(3))
                name = name + name_next
                next(meals_iter) # We have to advance the iterator once, to skip this
                continue
            price = match_price.group(1)

            name = name.replace('  ', ' ')

            res[current_date].append({ 'name': name, 'price': price + ' Kč' })

    # This restaurant doesn't give the menu for the whole week, so we have put some placeholders for the missing days
    res_all_days = {}
    (day, _menu) = list(res.items())[0]
    for i in range(day.weekday()):
        res_all_days[i] = []

    for (key, value) in res.items():
        res_all_days[key] = value

    while len(res_all_days) < 5:
        res_all_days[len(res_all_days)] = []

    return ('Radniční sklípek', res_all_days)

def main():
    if 'blox' in sys.argv[0]:
        (restaurant, menu) = blox()
    elif 'country' in sys.argv[0]:
        (restaurant, menu) = country_life()
    elif 'husa' in sys.argv[0]:
        (restaurant, menu) = husa()
    elif 'komousi' in sys.argv[0]:
        (restaurant, menu) = komousi()
    else:
        print('Název skriptu musí obsahovat jedno z těchto slov: "blox", "country"\nPoužijte symbolický odkaz k pojmenování skriptu.')
        exit(1)

    locale.setlocale(locale.LC_TIME, 'cs_CZ.UTF-8') # You better have this locale installed lmao
    if len(sys.argv) >= 2:
        weekdayStr = str(sys.argv[1])
        weekday = {'po': 0, 'út': 1, 'st': 2, 'čt': 3, 'pá': 4, 'ut': 1, 'ct': 3, 'pa': 4}[weekdayStr]
    else:
        weekday = date.today().weekday()

    if weekday is None:
        print('Neznámý den: "' + weekdayStr + '". Podporované formáty: Pátek|pá|pa')
        exit(1)

    (menu_date, menu) = list(menu.items())[weekday]

    name_width = max(len(max(menu, key=lambda index: len(index['name']))['name']), len('Název'))
    price_width = max(len(max(menu, key=lambda index: len(index['price']))['price']), len('Cena'))
    format_string = '{:3}' + '{{:{}}} {{:>{}}}'.format(name_width + 1, price_width + 1)

    print(BOLD + restaurant + NORMAL + ' ' + ITALIC + GREY + menu_date.strftime('%A') + ' ' + str(menu_date.day) + menu_date.strftime('. %B') + NORMAL)
    print(DOUBLE_UNDERLINE + BLUE + format_string.format('#', 'Název', 'Cena') + NORMAL)

    for count, meal in enumerate(menu):
        print(format_string.format(str(count + 1), meal['name'], meal['price']))

if __name__ == '__main__':
    main()
