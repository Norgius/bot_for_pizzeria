from transliterate import slugify

import requests


def get_access_token(client_secret: str, client_id: str) -> str:
    url = 'https://api.moltin.com/oauth/access_token'
    data = {'grant_type': 'client_credentials',
            'client_secret': client_secret, 'client_id': client_id}
    response = requests.post(url, data=data)
    response.raise_for_status()
    access_token = response.json().get('access_token')
    return access_token


def get_products(store_access_token: str) -> tuple[list, list]:
    headers = {'Authorization': f'Bearer {store_access_token}'}
    response = requests.get('https://api.moltin.com/catalog/products',
                            headers=headers)
    response.raise_for_status()
    raw_products = response.json().get('data')
    return raw_products


def get_product_image(store_access_token: str, image_id: str):
    headers = {'Authorization': f'Bearer {store_access_token}'}
    response = requests.get(f'https://api.moltin.com/v2/files/{image_id}',
                            headers=headers)
    response.raise_for_status()
    image_link = response.json().get('data').get('link').get('href')
    response = requests.get(image_link, stream=True)
    response.raise_for_status()
    return response.raw


def put_product_in_cart(store_access_token: str, product_id: str,
                        quantity: str, chat_id: int) -> int:
    url = f'https://api.moltin.com/v2/carts/{chat_id}/items'
    headers = {'Authorization': f'Bearer {store_access_token}'}
    body = {"data": {'quantity': quantity, 'type': 'cart_item',
                     'id': product_id}}
    response = requests.post(url, headers=headers, json=body)
    response.raise_for_status()
    return response.json()


def get_user_cart(store_access_token: str, chat_id: int) -> dict:
    url = f'https://api.moltin.com/v2/carts/{chat_id}/items'
    headers = {'Authorization': f'Bearer {store_access_token}'}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def delete_cart_product(store_access_token: str, chat_id: int,
                        product_id: str) -> None:
    url = f'https://api.moltin.com/v2/carts/{chat_id}/items/{product_id}'
    headers = {'Authorization': f'Bearer {store_access_token}'}
    response = requests.delete(url, headers=headers)
    response.raise_for_status()


def delete_all_cart_products(store_access_token: str, chat_id: int) -> None:
    url = f'https://api.moltin.com/v2/carts/{chat_id}/items'
    headers = {'Authorization': f'Bearer {store_access_token}'}
    response = requests.delete(url, headers=headers)
    response.raise_for_status()


def create_customer(store_access_token: str, customer_name: str,
                    customer_email: str) -> str:
    url = 'https://api.moltin.com/v2/customers'
    headers = {'Authorization': f'Bearer {store_access_token}'}
    body = {"data": {'name': customer_name, 'type': 'customer',
                     'email': customer_email}}
    response = requests.post(url, headers=headers, json=body)
    response.raise_for_status()
    customer_id = response.json().get('data').get('id')
    return customer_id


def create_product(store_access_token: str, product_data: dict):
    url = 'https://api.moltin.com/pcm/products'
    headers = {'Authorization': f'Bearer {store_access_token}'}
    json_data = {
        'type': 'product',
                'attributes': {
                    'name': product_data['name'],
                    'sku': slugify(product_data['name']),
                    'slug': slugify(product_data['name']),
                    'description': product_data['description'],
                    'status': 'live',
                    'commodity_type': 'physical',
                }
    }
    response = requests.post(url, headers=headers, json={'data': json_data})
    response.raise_for_status()
    product = response.json()
    product_sku = product['data']['attributes']['sku']
    product_id = product['data']['id']
    return product_id, product_sku


def create_corrency(store_access_token: str):
    url = 'https://api.moltin.com/v2/currencies'
    headers = {'Authorization': f'Bearer {store_access_token}'}
    json_data = {
        'type': 'currency',
        'code': 'RUB',
        'exchange_rate': 1,
        'format': '{price} РУБ',
        'decimal_point': '.',
        'thousand_separator': ',',
        'decimal_places': 2,
        'default': True,
        'enabled': True
    }
    response = requests.post(url, headers=headers, json={'data': json_data})
    response.raise_for_status()


def create_price_book(store_access_token: str):
    url = 'https://api.moltin.com/pcm/pricebooks'
    headers = {'Authorization': f'Bearer {store_access_token}'}
    json_data = {
        'type': 'pricebook',
        'attributes': {
            'name': 'Pizzeria price book',
        }
    }
    response = requests.post(url, headers=headers, json={'data': json_data})
    response.raise_for_status()
    return response.json()['data']['id']


def set_price_for_product(store_access_token: str, price_book_id: str,
                          product_sku: str, product_price: int):
    url = f'https://api.moltin.com/pcm/pricebooks/{price_book_id}/prices'
    headers = {'Authorization': f'Bearer {store_access_token}'}
    json_data = {
        'type': 'product-price',
        'attributes': {
            'currencies': {
                'RUB': {
                    'amount': product_price * 100,
                    'includes_tax': False
                },
            },
            'sku': product_sku
        }
    }
    response = requests.post(url, headers=headers, json={'data': json_data})
    response.raise_for_status()


def upload_image(store_access_token: str, image_url: str):
    url = 'https://api.moltin.com/v2/files'
    headers = {'Authorization': f'Bearer {store_access_token}'}
    files = {
        'file_location': (None, image_url),
    }
    response = requests.post(url, headers=headers, files=files)
    response.raise_for_status()
    return response.json()['data']['id']


def create_image_relationship(store_access_token: str, image_id: str,
                              product_id: str):
    url = f'https://api.moltin.com/pcm/products/{product_id}/relationships/main_image'
    headers = {'Authorization': f'Bearer {store_access_token}'}
    json_data = {
        'type': 'file',
        'id': f'{image_id}',
    }
    response = requests.post(url, headers=headers, json={'data': json_data})
    response.raise_for_status()


def create_flow(store_access_token: str):
    url = 'https://api.moltin.com/v2/flows'
    headers = {'Authorization': f'Bearer {store_access_token}'}
    json_data = {
        'data': {
            'type': 'flow',
            'name': 'Pizzeria',
            'slug': 'pizzeria',
            'description': 'pizzeria',
            'enabled': True,
        },
    }
    response = requests.post(url, headers=headers, json=json_data)
    response.raise_for_status()
    return response.json()['data']['id']


def create_field(store_access_token: str, json_data: dict, flow_id: str):
    url = 'https://api.moltin.com/v2/fields'
    headers = {'Authorization': f'Bearer {store_access_token}'}
    json_data['data']['relationships']['flow']['data']['id'] = flow_id
    response = requests.post(url, headers=headers, json=json_data)
    response.raise_for_status()


def create_entries_for_flow(store_access_token: str, address: dict):
    url = 'https://api.moltin.com/v2/flows/pizzeria/entries'
    headers = {'Authorization': f'Bearer {store_access_token}'}
    json_data = {
        'data': {
            'type': 'entry',
            'address': address['address']['full'],
            'alias': address['alias'],
            'latitude': float(address['coordinates']['lat']),
            'longitude': float(address['coordinates']['lon']),
        },
    }
    response = requests.post(url, headers=headers, json=json_data)
    response.raise_for_status()
