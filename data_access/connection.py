from sqlalchemy import URL, create_engine, text


database_url = URL.create(
    drivername="mysql+pymysql",
    username="tawos",
    password="tawos_dev_password",
    host="127.0.0.1",
    port=3307,
    database="tawos",
    query={"charset": "utf8mb4"}
)

engine = create_engine(
    database_url,
    pool_pre_ping=True
)

if __name__ == "__main__":
    with engine.connect() as connection:
        version = connection.execute(
            text("SELECT VERSION()")
        ).scalar_one()

        print(f"Подключение успешно. MySQL: {version}")