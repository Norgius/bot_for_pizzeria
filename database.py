import redis


def get_database_connection(database_password: str, database_host: str,
                            database_port: int) -> redis.Redis:
    _database = redis.Redis(host=database_host, port=database_port,
                            password=database_password)
    return _database
