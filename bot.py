import logging
from math import ceil
from textwrap import dedent

import redis
import requests
from geopy import distance
from environs import Env
from telegram import (ParseMode, LabeledPrice, Update,
                      InlineKeyboardButton, InlineKeyboardMarkup)
from telegram.ext import (Filters, Updater, CallbackContext, CommandHandler,
                          CallbackQueryHandler, MessageHandler,
                          PreCheckoutQueryHandler)

from moltin_api import (get_access_token, get_products, get_product_image,
                        put_product_in_cart, get_user_cart,
                        delete_cart_product, get_entry_from_flow,
                        get_pizzeria_list, create_entries_for_flow,
                        delete_all_cart_products)

logger = logging.getLogger(__name__)


def fetch_coordinates(apikey, address):
    base_url = "https://geocode-maps.yandex.ru/1.x"
    response = requests.get(base_url, params={
        "geocode": address,
        "apikey": apikey,
        "format": "json",
    })
    response.raise_for_status()
    found_places = response.json()['response']['GeoObjectCollection']['featureMember']

    if not found_places:
        return None

    most_relevant = found_places[0]
    lon, lat = most_relevant['GeoObject']['Point']['pos'].split(" ")
    return float(lat), float(lon)


def parse_products(raw_products: list) -> dict:
    products = {}
    for raw_product in raw_products:
        attributes = raw_product.get('attributes')
        product = {
            'name': attributes.get('name'),
            'description': attributes.get('description'),
            'price': attributes.get('price').get('RUB').get('amount') / 100,
            'image_id': raw_product.get('relationships')
            .get('main_image').get('data').get('id')
            }
        products[raw_product.get('id')] = product
    return products


def get_menu_buttons(products: dict, products_per_page: int,
                     pages_number: int, page: int = 0) -> list:
    keyboard = []
    pages_range = (range(page * products_per_page, page *
                         products_per_page + products_per_page))
    product_number = 0
    for product_id, product in products.items():
        if product_number in pages_range:
            button = [
                InlineKeyboardButton(product.get('name'),
                                     callback_data=product_id)
                    ]
            keyboard.append(button)
        product_number += 1
    if pages_number > 1:

        keyboard.append([InlineKeyboardButton('<', callback_data='back'),
                         InlineKeyboardButton('>', callback_data='forward')]
                        )
    keyboard.append([InlineKeyboardButton('Корзина', callback_data='Корзина')])
    return keyboard


def get_product_quantity_in_cart(product_id, user_cart) -> int:
    products = user_cart.get('data')
    if products:
        for product in products:
            if product_id == product.get('product_id'):
                return int(product.get('quantity'))
    return 0


def prepare_cart_buttons_and_message(
        user_cart: dict, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    products = user_cart.get('data')
    message = ''
    keyboard = []
    if products:
        for product in products:
            product_price = product.get('meta').get('display_price')\
                .get('without_tax').get('unit').get('formatted')
            product_quantity = product.get('quantity')
            product_total_cost = product_quantity * float(product_price[:-4])

            message += dedent(f'''
            <b>{product.get("name")}</b>

            {product.get("description")}
            Стоимость: <u>{product_price}</u>
            <u>{product_quantity} пицц</u> в корзине на сумму <u>{product_total_cost:.2f} РУБ</u>
            ''')
            button = [InlineKeyboardButton(
                f'Убрать из корзины {product.get("name")}',
                callback_data=f'del_{product.get("id")}'
                                           )
                      ]
            keyboard.append(button)
        cart_total_cost = user_cart.get('meta').get('display_price')\
            .get('without_tax').get('amount')
        message += dedent(f'''
        <b>Общая стоимость:</b> <u>{cart_total_cost/100:.2f} РУБ</u>''')
        _database.json().set(f'{chat_id}_menu', '$',
                             {'menu': message, 'price': cart_total_cost/100})
    else:
        message = 'Ваша корзина пуста'

    keyboard.append([InlineKeyboardButton('В меню', callback_data='В меню')])
    if len(keyboard) > 1:
        keyboard.append(
            [InlineKeyboardButton('Оплата', callback_data='Оплата')]
        )
    reply_markup = InlineKeyboardMarkup(keyboard)
    return message, reply_markup


def prepare_description_buttons_and_message(
        product_data: dict, product_quantity: int) -> tuple[str, InlineKeyboardMarkup]:
    payment = product_quantity * product_data.get('price')
    message = dedent(f'''
    <b>{product_data.get('name')}</b>

    Стоимость: <u>{product_data.get('price'):.2f} РУБ</u>

    {product_data.get('description')}
    ''')
    if product_quantity:
        message += dedent(f'''
        Количество данной пиццы в <b>корзине</b>: <u>{product_quantity}</u>
        К оплате: {payment:.2f} РУБ
        ''')
    keyboard = [
        [InlineKeyboardButton('Положить в корзину',
                              callback_data='Положить в корзину')],
        [InlineKeyboardButton('Корзина', callback_data='Корзина')],
        [InlineKeyboardButton('Назад', callback_data='Назад')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    return message, reply_markup


def start(update: Update, context: CallbackContext) -> str:
    store_access_token = context.bot_data['store_access_token']
    products_per_page = context.bot_data['products_per_page']
    raw_products = get_products(store_access_token)
    products = parse_products(raw_products)
    pages_number = ceil(len(products) / products_per_page)
    context.bot_data['page_number'] = 0
    keyboard = get_menu_buttons(products, products_per_page, pages_number)
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(text='Пожалуйста, выберите товар!',
                              reply_markup=reply_markup)
    return 'HANDLE_MENU'


def handle_menu(update: Update, context: CallbackContext) -> str:
    bot = context.bot
    query = update.callback_query
    if not query:
        return 'HANDLE_MENU'
    chat_id = query.message.chat_id
    user_reply = query.data
    store_access_token = context.bot_data['store_access_token']
    if user_reply == 'forward' or user_reply == 'back':
        page_number = context.bot_data['page_number']
        page_number = page_number + 1 if user_reply == 'forward' \
            else page_number - 1
        products_per_page = context.bot_data['products_per_page']
        raw_products = get_products(store_access_token)
        products = parse_products(raw_products)

        pages_number = ceil(len(products) / products_per_page)
        page_number = 0 if page_number >= pages_number else page_number
        page_number = pages_number - 1 if page_number < 0 else page_number
        context.bot_data['page_number'] = page_number

        keyboard = get_menu_buttons(products, products_per_page,
                                    pages_number, page_number)
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot.send_message(text='Пожалуйста, выберите товар!', chat_id=chat_id,
                         reply_markup=reply_markup)
        bot.delete_message(chat_id=chat_id,
                           message_id=query.message.message_id)
        return 'HANDLE_MENU'
    user_cart = get_user_cart(store_access_token, chat_id)
    if user_reply == 'Корзина':
        message, reply_markup = prepare_cart_buttons_and_message(user_cart,
                                                                 chat_id)
        bot.send_message(chat_id=chat_id, text=message,
                         reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        bot.delete_message(chat_id=chat_id,
                           message_id=query.message.message_id)
        return 'HANDLE_CART'
    raw_products = get_products(store_access_token)
    products = parse_products(raw_products)
    context.bot_data['product_id'] = user_reply
    product_data = products.get(user_reply)
    context.bot_data[f'{user_reply}_data'] = product_data

    image_id = product_data.get('image_id')
    image = get_product_image(store_access_token, image_id)
    quantity_in_cart = get_product_quantity_in_cart(user_reply, user_cart)
    message, reply_markup = prepare_description_buttons_and_message(
        product_data, quantity_in_cart)

    bot.send_photo(chat_id=chat_id, photo=image, caption=message,
                   reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    bot.delete_message(chat_id=chat_id,
                       message_id=query.message.message_id)
    return 'HANDLE_DESCRIPTION'


def handle_description(update: Update, context: CallbackContext) -> str:
    bot = context.bot
    query = update.callback_query
    if not query:
        return 'HANDLE_DESCRIPTION'
    user_reply = query.data
    chat_id = query.message.chat_id
    store_access_token = context.bot_data['store_access_token']
    if user_reply == 'Положить в корзину':
        product_id = context.bot_data['product_id']
        product_data = context.bot_data[f'{product_id}_data']
        quantity = 1
        user_cart = put_product_in_cart(store_access_token, product_id,
                                        quantity, chat_id)
        bot.answer_callback_query(text='Товар добавлен к корзину',
                                  callback_query_id=query.id,)

        quantity_in_cart = get_product_quantity_in_cart(product_id, user_cart)
        message, reply_markup = prepare_description_buttons_and_message(
            product_data, quantity_in_cart)
        image_id = product_data.get('image_id')
        image = get_product_image(store_access_token, image_id)
        bot.send_photo(chat_id=chat_id, photo=image, caption=message,
                       reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        bot.delete_message(chat_id=chat_id,
                           message_id=query.message.message_id)
        return 'HANDLE_DESCRIPTION'
    elif user_reply == 'Корзина':
        user_cart = get_user_cart(store_access_token, chat_id)
        message, reply_markup = prepare_cart_buttons_and_message(user_cart,
                                                                 chat_id)
        bot.send_message(chat_id=chat_id, text=message,
                         reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        bot.delete_message(chat_id=chat_id,
                           message_id=query.message.message_id)
        return 'HANDLE_CART'
    else:
        raw_products = get_products(store_access_token)
        products = parse_products(raw_products)
        products_per_page = context.bot_data['products_per_page']
        pages_number = ceil(len(products) / products_per_page)
        context.bot_data['page_number'] = 0
        keyboard = get_menu_buttons(products, products_per_page, pages_number)
        reply_markup = InlineKeyboardMarkup(keyboard)

        bot.send_message(text='Пожалуйста, выберите товар!', chat_id=chat_id,
                         reply_markup=reply_markup)
        bot.delete_message(chat_id=chat_id,
                           message_id=query.message.message_id)
        return 'HANDLE_MENU'


def handle_cart(update: Update, context: CallbackContext) -> str:
    bot = context.bot
    query = update.callback_query
    if not query:
        return 'HANDLE_CART'
    chat_id = query.message.chat_id
    user_reply = query.data
    store_access_token = context.bot_data['store_access_token']
    if user_reply.startswith('del_'):
        product_id = user_reply[4::]
        delete_cart_product(store_access_token, chat_id, product_id)
        user_cart = get_user_cart(store_access_token, chat_id)
        message, reply_markup = prepare_cart_buttons_and_message(user_cart,
                                                                 chat_id)
        bot.send_message(chat_id=chat_id, text=message,
                         reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        bot.delete_message(chat_id=chat_id,
                           message_id=query.message.message_id)
        return 'HANDLE_CART'
    elif user_reply == 'В меню':
        raw_products = get_products(store_access_token)
        products = parse_products(raw_products)
        products_per_page = context.bot_data['products_per_page']
        pages_number = ceil(len(products) / products_per_page)
        context.bot_data['page_number'] = 0
        keyboard = get_menu_buttons(products, products_per_page, pages_number)
        reply_markup = InlineKeyboardMarkup(keyboard)

        bot.send_message(text='Пожалуйста, выберите товар!', chat_id=chat_id,
                         reply_markup=reply_markup)
        bot.delete_message(chat_id=chat_id,
                           message_id=query.message.message_id)
        return 'HANDLE_MENU'
    else:
        message = 'Пришлите, пожалуйста, ваш адрес текстом или геолокацию'
        bot.send_message(text=message, chat_id=query.message.chat_id)
        return 'HANDLE_WAITING'


def handle_waiting(update: Update, context: CallbackContext) -> str:
    store_access_token = context.bot_data['store_access_token']
    chat_id = update.effective_chat.id
    try:
        current_pos = (update.message.location.latitude,
                       update.message.location.longitude)
    except AttributeError:
        address = update.message.text
        geocoder_api = context.bot_data['geocoder_api']
        current_pos = fetch_coordinates(geocoder_api, address)
    if not current_pos:
        message = 'Не могу распознать этот адрес'
        update.message.reply_text(text=message)
        return 'HANDLE_WAITING'

    customer_address_id = create_entries_for_flow(store_access_token,
                                                  current_pos,
                                                  flow='customer_address')
    raw_addresses = get_pizzeria_list(store_access_token)
    path_to_pizzerias = {}
    for raw_address in raw_addresses['data']:
        pizzeria_coord = (raw_address['latitude'], raw_address['longitude'])
        path_to_pizzeria = distance.distance(pizzeria_coord, current_pos).km

        path_to_pizzerias[path_to_pizzeria] = (raw_address['address'],
                                               raw_address['id'])
    nearest_pizzeria = min(path_to_pizzerias.items(), key=lambda x: x[0])
    _database.set(f'{chat_id}_order',
                  f'{customer_address_id}${nearest_pizzeria[1][1]}')

    keyboard = [[InlineKeyboardButton('Доставка', callback_data='Доставка')],
                [InlineKeyboardButton('Самовывоз', callback_data='Самовывоз')]]
    if nearest_pizzeria[0] <= 0.500:
        message = dedent(f'''
        Пиццерия неподалеку, всего в <b>{(nearest_pizzeria[0] * 1000):.0f} метрах</b> от вас.
        Её адрес: <b>{nearest_pizzeria[1][0]}.</b>

        Также можем доставить её бесплатно)
        ''')
    elif 0.500 < nearest_pizzeria[0] <= 5:
        message = dedent(f'''
        Похоже придется ехать до вас на самокате.
        Доставка будет стоить <b>100 рублей.</b>
        Доставляем или самовывоз?

        Адрес пиццерии: <b>{nearest_pizzeria[1][0]}.</b>
        ''')
    elif 5 < nearest_pizzeria[0] <= 20:
        message = 'Доставка пиццы обойдется вам в <b>300 рублей.</b>'
    else:
        message = dedent(f'''
        К сожалению так далеко мы пиццу не доставляем.
        Ближайшая пиццерия аж в <b>{nearest_pizzeria[0]:.1f} км</b> от вас.
        ''')
        _ = keyboard.pop(0)
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(text=message, parse_mode=ParseMode.HTML,
                              reply_markup=reply_markup)
    return 'HANDLE_DELIVERY'


def remind_about_order(context: CallbackContext) -> str:
    chat_id = context.job.context
    message = dedent('''
    Приятного аппетита! *место для рекламы*

    *сообщение что делать если пицца не пришла*
    ''')
    context.bot.send_message(chat_id=chat_id, text=message)


def handle_delivery(update: Update, context: CallbackContext) -> str:
    store_access_token = context.bot_data['store_access_token']
    bot = context.bot
    query = update.callback_query
    chat_id = query.message.chat_id
    entry_ids = _database.get(f'{chat_id}_order').decode('utf-8')
    customer_address_id, pizzeria_id = entry_ids.split('$')
    raw_entry = get_entry_from_flow(store_access_token, 'pizzeria',
                                    pizzeria_id)
    pizzeria_coords = (raw_entry['data']['latitude'],
                       raw_entry['data']['longitude'])
    
    pizzeria_address = raw_entry['data']['address']
    keyboard = [[InlineKeyboardButton('Наличными', callback_data='cash')],
                [InlineKeyboardButton('Картой', callback_data='card')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if query.data == 'Доставка':
        deliveryman_id = raw_entry['data']['deliveryman_id']
        context.bot_data[f'{chat_id}_delivery'] = \
            f'{customer_address_id}${deliveryman_id}'
        message = 'Оплатите пиццу и ожидайте доставщика пиццы'
        bot.send_message(chat_id, text=message, reply_markup=reply_markup)

    elif query.data == 'Самовывоз':
        context.bot_data[f'{chat_id}_delivery'] = False
        bot.send_location(chat_id, latitude=pizzeria_coords[0],
                          longitude=pizzeria_coords[1])
        message = f'После оплаты будем ждать вас по адресу: {pizzeria_address}'
        bot.send_message(chat_id, text=message, reply_markup=reply_markup)
    return 'HANDLE_PAYMENT_CHOICE'


def handle_payment_choice(update: Update, context: CallbackContext) -> None:
    store_access_token = context.bot_data['store_access_token']
    bot = context.bot
    query = update.callback_query
    chat_id = query.message.chat_id
    if query.data:
        if query.data == 'card':
            pay_for_pizza(update, context)
        else:
            message = 'Благодарим за заказ!'
            bot.send_message(text=message, chat_id=query.message.chat_id)

        delivery = context.bot_data[f'{chat_id}_delivery']
        if delivery:
            customer_address_id, deliveryman_id = delivery.split('$')
            raw_entry = get_entry_from_flow(store_access_token,
                                            'customer_address',
                                            customer_address_id)
            coords = (raw_entry['data']['latitude'],
                      raw_entry['data']['longitude'])

            message = _database.json().get(f'{chat_id}_menu')['menu']
            bot.send_message(deliveryman_id, text=message,
                             parse_mode=ParseMode.HTML)
            bot.send_location(deliveryman_id, latitude=coords[0],
                              longitude=coords[1], protect_content=True)
            context.bot_data[f'{chat_id}_delivery'] = None

        delete_all_cart_products(store_access_token, chat_id)
        context.job_queue.run_once(remind_about_order, 3600, context=chat_id)
        return 'START'
    return 'HANDLE_PAYMENT_CHOICE'


def pay_for_pizza(update: Update, context: CallbackContext) -> None:
    '''Sends an invoice without shipping-payment.'''
    query = update.callback_query
    chat_id = query.message.chat_id
    title = 'Payment Example'
    description = 'Payment Example using python-telegram-bot'
    payload = 'pizza_payment'
    provider_token = context.bot_data['payment_token']
    currency = 'RUB'
    price = _database.json().get(f'{chat_id}_menu')['price']
    prices = [LabeledPrice('Test', int(price) * 100)]
    context.bot.send_invoice(
        chat_id, title, description, payload, provider_token, currency, prices
    )


def pre_checkout_callback(update: Update, context: CallbackContext) -> None:
    query = update.pre_checkout_query
    if query.invoice_payload != 'pizza_payment':
        query.answer(ok=False, error_message="Something went wrong...")
    else:
        query.answer(ok=True)


def successful_payment_callback(update: Update, context: CallbackContext) -> None:
    update.message.reply_text('Благодарим за заказ! Оплата прошла успешно!')


def handle_users_reply(update: Update, context: CallbackContext) -> None:
    client_secret = context.bot_data['client_secret']
    client_id = context.bot_data['client_id']
    token_lifetime = context.bot_data['token_lifetime']
    client_id = context.bot_data['client_id']
    try:
        store_access_token = _database.get('store_access_token')
        if not store_access_token:
            store_access_token = get_access_token(client_secret, client_id)
            _database.setex('store_access_token', token_lifetime,
                            store_access_token)
        else:
            store_access_token = store_access_token.decode('utf-8')
        context.bot_data['store_access_token'] = store_access_token
    except requests.exceptions.HTTPError as err:
        logger.warning(f'Ошибка в работе api.moltin.com\n{err}\n')

    if update.message:
        user_reply = update.message.text
        chat_id = update.message.chat_id
    elif update.callback_query:
        user_reply = update.callback_query.data
        chat_id = update.callback_query.message.chat_id
    else:
        return
    if user_reply == '/start':
        user_state = 'START'
    else:
        user_state = _database.get(chat_id).decode('utf-8')

    states_functions = {
        'START': start,
        'HANDLE_MENU': handle_menu,
        'HANDLE_DESCRIPTION': handle_description,
        'HANDLE_CART': handle_cart,
        'HANDLE_WAITING': handle_waiting,
        'HANDLE_DELIVERY': handle_delivery,
        'HANDLE_PAYMENT_CHOICE': handle_payment_choice
    }
    state_handler = states_functions[user_state]
    try:
        next_state = state_handler(update, context)
        _database.set(chat_id, next_state)
    except requests.exceptions.HTTPError as err:
        logger.warning(f'Ошибка в работе api.moltin.com\n{err}\n')
    except Exception as err:
        logger.warning(f'Ошибка в работе телеграм бота\n{err}\n')


def main():
    env = Env()
    env.read_env()
    client_secret = env.str('ELASTICPATH_CLIENT_SECRET')
    client_id = env.str('ELASTICPATH_CLIENT_ID')
    token_lifetime = env.int('TOKEN_LIFETIME')
    products_per_page = env.int('PRODUCTS_PER_PAGE', 6)
    database_password = env.str("REDIS_PASSWORD")
    database_host = env.str("REDIS_HOST")
    database_port = env.int("REDIS_PORT")
    geocoder_api = env.str('YANDEX_GEOCODER_APIKEY')
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logger.setLevel(logging.INFO)
    global _database
    _database = redis.Redis(host=database_host, port=database_port,
                            password=database_password)
    tg_token = env.str('PIZZERIA_BOT_TG_TOKEN')
    payment_token = env.str('PAYMENT_TOKEN')
    updater = Updater(tg_token)
    dispatcher = updater.dispatcher
    dispatcher.bot_data['client_id'] = client_id
    dispatcher.bot_data['token_lifetime'] = token_lifetime
    dispatcher.bot_data['client_secret'] = client_secret
    dispatcher.bot_data['products_per_page'] = products_per_page
    dispatcher.bot_data['geocoder_api'] = geocoder_api
    dispatcher.bot_data['payment_token'] = payment_token
    dispatcher.add_handler(CallbackQueryHandler(handle_users_reply))
    dispatcher.add_handler(MessageHandler(
        Filters.text | Filters.location,
        handle_users_reply)
    )
    dispatcher.add_handler(CommandHandler('start', handle_users_reply))
    dispatcher.add_handler(MessageHandler(
        Filters.successful_payment, successful_payment_callback)
    )
    dispatcher.add_handler(PreCheckoutQueryHandler(pre_checkout_callback))
    logger.info('Телеграм бот запущен')
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
