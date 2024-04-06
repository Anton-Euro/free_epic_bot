from aiogram import Bot, Dispatcher, F, types
import asyncio
import logging
import sys
import requests
import json
from datetime import datetime
import pytz
import psycopg2
import os
from keep_alive import keep_alive


TOKEN = os.environ['TOKEN']
base_url = 'https://store.epicgames.com/ru/p/'
date_format = "%Y-%m-%dT%H:%M:%S.%fZ"
target_timezone = pytz.timezone('Europe/Minsk')
db_url = os.environ['DB_URL']

dp = Dispatcher()


async def parse_games() -> list:
    params = {
        'locale': 'ru-RU',
        'country': 'BY',
    }
    response = requests.get('https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions', params=params)
    response = json.loads(response.text)['data']['Catalog']['searchStore']['elements']

    games = []
    for game in response:
        try:
            title = game['title']
            description = game['description']
            for img in game['keyImages']:
                if 'Wide' in img['type']:
                    logo = img['url']
                    break
            else:
                logo = game['keyImages'][0]['url']
            url = base_url + game['catalogNs']['mappings'][0]['pageSlug']
            prev_price = game['price']['totalPrice']['fmtPrice']['originalPrice']
            if game['promotions']['promotionalOffers'] != []:
                status = 'Сейчас бесплатно'
                item = game['promotions']['promotionalOffers'][0]['promotionalOffers'][0]
                if item['discountSetting']['discountPercentage'] == 0:
                    start_time = item['startDate']
                    end_time = item['endDate']
                    start_time = datetime.strptime(start_time, date_format)
                    start_time = start_time.replace(tzinfo=pytz.utc).astimezone(target_timezone)
                    end_time = datetime.strptime(end_time, date_format)
                    end_time = end_time.replace(tzinfo=pytz.utc).astimezone(target_timezone)
                else:
                    continue
            else:
                status = 'Скоро'
                item = game['promotions']['upcomingPromotionalOffers'][0]['promotionalOffers'][0]
                if item['discountSetting']['discountPercentage'] == 0:
                    start_time = item['startDate']
                    end_time = item['endDate']
                    start_time = datetime.strptime(start_time, date_format)
                    start_time = start_time.replace(tzinfo=pytz.utc).astimezone(target_timezone)
                    end_time = datetime.strptime(end_time, date_format)
                    end_time = end_time.replace(tzinfo=pytz.utc).astimezone(target_timezone)
                else:
                    continue
        except:
            continue
        games.append({
            'title': title,
            'description': description,
            'logo': logo,
            'url': url,
            'prev_price': prev_price,
            'status': status,
            'start_date': start_time,
            'end_date': end_time,
        })

    games.sort(key=lambda x: x['start_date'])
    return games


async def send_response(bot: Bot, users: list, games: list) -> None:
    for game in games:
        for user in users:
            if user[1] == True:
                try:
                    await bot.send_photo(chat_id=user[0],
                                        photo=game['logo'],
                                        caption=f'''
<strong>Название:</strong> {game['title']}
<strong>Описание:</strong> {game['description']}
<strong>Ссылка:</strong> {game['url']}
<strong>Цена:</strong> <s>{game['prev_price']}</s> 0 ₽
<strong>Статус:</strong> {game['status']}
<strong>Доступно:</strong> {game['start_date'].strftime('%Y-%m-%d %H:%M')} - {game['end_date'].strftime('%Y-%m-%d %H:%M')}
                        ''',
                                        parse_mode='HTML')
                except:
                    pass
            await asyncio.sleep(1)


@dp.message(F.text == "/start")
async def start(message: types.Message):
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute('SELECT id FROM free_epic_user')
    users = list(map(lambda x: x[0], cur.fetchall()))
    if message.from_user.id not in users:
        cur.execute('INSERT INTO free_epic_user (id, status) VALUES (%s, %s)', (message.from_user.id,True,))
        conn.commit()
        await message.answer('Вы включили рассылку!\nЧтобы выключить рассылку введите /stop')
        games = await parse_games()
        await send_response(message.bot, [(message.from_user.id, True)], games)
    else:
        cur.execute(f'SELECT status FROM free_epic_user WHERE id = {message.from_user.id}')
        if cur.fetchone()[0] == False:
            cur.execute('UPDATE free_epic_user SET status = %s WHERE id = %s', (True,message.from_user.id,))
            conn.commit()
            await message.answer('Вы включили рассылку!\nЧтобы выключить рассылку введите /stop')
        else:
            await message.answer('У вас уже включена рассылка!\nЧтобы выключить рассылку введите /stop')
    cur.close()
    conn.close()


@dp.message(F.text == "/stop")
async def stop(message: types.Message):
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute(
        f'SELECT status FROM free_epic_user WHERE id = {message.from_user.id}')
    if cur.fetchone()[0] == True:
        cur.execute('UPDATE free_epic_user SET status = %s WHERE id = %s', (
            False,
            message.from_user.id,
        ))
        conn.commit()
        await message.answer(
            'Вы выключили рассылку!\nЧтобы включить рассылку введите /start')
    else:
        await message.answer(
            'У вас уже выключена рассылка!\nЧтобы выключить рассылку введите /stop'
        )
    cur.close()
    conn.close()


async def check_post(bot):
    with open('last.txt', 'r') as f:
        last_games = eval(f.read())
    while True:
        games = await parse_games()

        curr_games = []
        for game in games:
            curr_games.append(game['title'])
        if last_games != curr_games:
            last_games = list(curr_games)
            with open('last.txt', 'w') as f:
                f.write(str(last_games))
            conn = psycopg2.connect(db_url)
            cur = conn.cursor()
            cur.execute('SELECT * FROM free_epic_user')
            users = cur.fetchall()
            cur.close()
            conn.close()
            await send_response(bot, users, games)
            
        await asyncio.sleep(3600)


async def main():
    bot = Bot(TOKEN)
    loop = asyncio.get_event_loop()
    loop.create_task(check_post(bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    keep_alive()
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
