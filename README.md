# Продаём пиццу в телеграме
Данный проект позволяет с помощью `бота` покупать пиццу в `телеграме`.
Ознакомиться с работой `бота` можете по [ссылке](https://t.me/norgius_speech_bot).

## Что необходимо для запуска
Для данного проекта необходим `Python3.6` (или выше).
Создадим виртуальное окружение в корневой директории проекта:
```
python3 -m venv env
```
После активации виртуального окружения установим необходимые зависимости:
```
pip install -r requirements.txt
```
Также заранее создадим файл `.env` в директории проекта.

## Создаем магазин на сайте [Elasticpath](https://www.elasticpath.com/)
Зарегистрируйтесь как разработчик на сайте [Elasticpath](https://www.elasticpath.com/) и создайте магазин.

Для телеграм бота потребуются `Client ID` и `Client Secret`, запишите их в `.env`:
```
ELASTICPATH_CLIENT_SECRET=
ELASTICPATH_CLIENT_ID=
```
Вам также необходимо задать время жизни токена доступа к магазину, который автоматически будет получать бот в процессе своей работы, на текущий момент в [документации](https://documentation.elasticpath.com/commerce-cloud/docs/api/basics/authentication/index.html#:~:text=Authentication%20tokens%20are%20generated%20via%20the%20authentication%20endpoint%20and%20expire%20within%201%20hour.%20They%20need%20to%20be%20then%20regenerated.) указано, что время жизни `токена` равно `1 часу`. Поэтому укажите время `в секундах равное 1 часу` или менее:
```
TOKEN_LIFETIME=
```
## Загружаем товары в магазин
Для загрузки товаров предусмотрен специальный файл `add_data_to_store.py`. Загружать товары и создавать модели (в магазине они называются `flow`) будем поэтапно. Для каждого действия необходимо указывать свой аргумент:
* Создание `flow` и его `fields`. Для первого передаём название, для второго название `json-файла` в папке `Fields for flow`:
```
python add_data_to_store.py --flow='pizzeria --fields='pizzeria_fields.json'
```
```
python add_data_to_store.py --flow='customer address' --fields='cusmomer_address_fields.json'
```
* Создадим `Price book` и валюту `RUB` для нашей пиццерии (**Важно!!!** запишите полученный `ID` в `.env` файл `PRICE_BOOK_ID=`):
```
python add_data_to_store.py --price_book
```
* Добавим данные о товарах в магазин (**Важно!!!** после добавления не забудьте связать их с каталогом в личном кабинете магазина):
```
python add_data_to_store.py --menu
```
* Добавим адреса магазинов в нашу созданную модель `Pizzeria`:
```
python add_data_to_store.py --address
```

## Создаём бота
Напишите [отцу ботов](https://telegram.me/BotFather) для создания телеграм бота.

Запишите его токен в `.env`:
```
PIZZERIA_BOT_TG_TOKEN=
```
Также для работы бота необходимо получить токен оплаты. У `BotFather` командой `/mybots` выбрать вашего бота, а затем выбрать `Payments` и получить токен у отдельного банка. Запишите его в `.env`:
```
PAYMENT_TOKEN=
```

## Подключаем Redis
Регистрируемся на [Redis](https://redis.com/) и заводим себе удаленную `базу данных`. Для подключения к ней вам понадобятся `host`, `port` и `password`. Запишите их в файле `.env`:
```
REDIS_HOST=
REDIS_PORT=
REDIS_PASSWORD=
```

## Другие ключи и дополнительные настройки
Для функционирования проекта вам потребуется получить `ключ API Яндекс-геокодера`, перейдите по [ссылке](https://developer.tech.yandex.ru/) и получите API-ключ, выбрав `JavaScript API и HTTP Геокодер`. После получения ключа, запишите его в `.env`:
```
YANDEX_GEOCODER_APIKEY=
```
Вы можете ограничить или же увеличить количество отображаемых товаров в меню:
```
PRODUCTS_PER_PAGE=
```

## Запуск бота
Бот запускается командой
```
python bot.py
```
