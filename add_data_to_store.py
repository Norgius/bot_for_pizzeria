import json
import argparse
import logging

from environs import Env
import requests

from database import get_database_connection
from moltin_api import (get_access_token, set_price_for_product,
                        create_corrency, create_price_book, create_product,
                        upload_image, create_image_relationship, create_flow,
                        create_field, create_entries_for_flow)

logger = logging.getLogger(__name__)


def main():
    env = Env()
    env.read_env()
    database_password = env.str("REDIS_PASSWORD")
    database_host = env.str("REDIS_HOST")
    database_port = env.int("REDIS_PORT")
    client_secret = env.str('ELASTICPATH_CLIENT_SECRET')
    client_id = env.str('ELASTICPATH_CLIENT_ID')
    token_lifetime = env.int('TOKEN_LIFETIME')
    price_book_id = env.str('PRICE_BOOK_ID', '')
    flow_id = env.str('FLOW_ID', '')
    parser = argparse.ArgumentParser(
        description=''
    )
    parser.add_argument('--price_book', action=argparse.BooleanOptionalAction,
                        help='Аргумент для создания price_book')
    parser.add_argument('--flow', action=argparse.BooleanOptionalAction,
                        help='Аргумент для создания flow')
    parser.add_argument('--field_for_flow', default='', type=str,
                        help='''Аргумент для создания field_for_flow
                                и путь до файла с данными о полях''')
    parser.add_argument('--menu', action=argparse.BooleanOptionalAction,
                        help='Аргумент для добавления товаров в магазин')
    parser.add_argument('--address', action=argparse.BooleanOptionalAction,
                        help='Аргумент для добавления адресов пиццерий')
    args = parser.parse_args()
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logger.setLevel(logging.INFO)
    _database = get_database_connection(database_password, database_host,
                                        database_port)
    store_access_token = _database.get('store_access_token')
    if not store_access_token:
        store_access_token = get_access_token(client_secret, client_id)
        _database.setex('store_access_token', token_lifetime,
                        store_access_token)
    else:
        store_access_token = store_access_token.decode('utf-8')
    try:
        if args.price_book:
            create_corrency(store_access_token)
            price_book_id = create_price_book(store_access_token)
            print('price_book_id:', price_book_id)
        elif args.flow:
            flow_id = create_flow(store_access_token)
            print('flow_id:', flow_id)
        elif args.field_for_flow:
            with open(args.field_for_flow, 'r') as file:
                field_for_flow = json.load(file)
            for field in field_for_flow:
                create_field(store_access_token, field, flow_id)
            print('Поля для Flow созданы')
        elif args.address:
            url = 'https://dvmn.org/media/filer_public/90/90/9090ecbf-249f-42c7-8635-a96985268b88/addresses.json'
            response = requests.get(url)
            response.raise_for_status()
            for address in response.json():
                create_entries_for_flow(store_access_token, address)
            print('Все адреса были добавлены, проверьте Flow')
        elif args.menu:
            url = 'https://dvmn.org/media/filer_public/a2/5a/a25a7cbd-541c-4caf-9bf9-70dcdf4a592e/menu.json'
            response = requests.get(url)
            response.raise_for_status()
            for product in response.json():
                product_id, product_sku = create_product(store_access_token,
                                                         product)
                set_price_for_product(store_access_token, price_book_id,
                                      product_sku, product['price'])
                image_id = upload_image(store_access_token,
                                        product['product_image']['url'],)
                create_image_relationship(store_access_token, image_id,
                                          product_id)
                print(product['name'], 'загружен')
        else:
            print('Вы не указали аргумент')
    except FileNotFoundError as error:
        logger.warning(error)
    except requests.exceptions.HTTPError as error:
        logger.warning(error)
    finally:
        exit(0)


if __name__ == '__main__':
    main()
