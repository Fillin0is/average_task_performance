# Average task performance

Исследовательский проект для прогнозирования времени выполнения программных
задач на открытом датасете TAWOS 1.1.

TAWOS содержит задачи из 39 open-source проектов, их тексты, метаданные,
историю изменений и несколько оценок длительности, включая
`Resolution_Time_Minutes`, `In_Progress_Minutes` и `Total_Effort_Minutes`.

Сам датасет и содержимое MySQL не хранятся в Git: вместе они занимают около
17 ГБ. Репозиторий содержит воспроизводимые скрипты загрузки и развёртывания.

## Требования

- Git;
- Docker с поддержкой `docker compose`;
- `curl`, `unzip` и около 17 ГБ свободного места.

## Запуск на другом компьютере

Подробная пошаговая памятка для Windows: [docs/SETUP.md](docs/SETUP.md).

```bash
git clone https://github.com/Fillin0is/average_task_performance.git
cd average_task_performance
cp docker/.env.example docker/.env
./scripts/download_tawos.sh
docker compose -f docker/docker-compose.tawos.yaml up -d
./scripts/check_tawos.sh
```

## 1. Загрузка датасета

Потребуется около 5 ГБ свободного места: официальный архив занимает 608 МБ,
распакованный MySQL dump — около 4,1 ГБ.

```bash
./scripts/download_tawos.sh
```

Скрипт загружает TAWOS с UCL Figshare, умеет продолжать прерванную загрузку и
проверяет официальный MD5 checksum. Результат сохраняется в игнорируемом Git
каталоге `data/raw/tawos/`.

Используя датасет, необходимо соблюдать его условия: данные предназначены для
исследовательских целей, нельзя пытаться деанонимизировать участников или
применять результаты во вред авторам и владельцам проектов.

## 2. Импорт в MySQL

Датасет опубликован как dump MySQL 8. Первый запуск контейнера автоматически
создаёт базу `tawos` и импортирует dump:

```bash
docker compose -f docker/docker-compose.tawos.yaml up -d
docker compose -f docker/docker-compose.tawos.yaml logs -f mysql
```

Импорт 4,1 ГБ может занять несколько минут. До его окончания контейнер будет
иметь статус `health: starting`. Проверить успешную установку:

```bash
./scripts/check_tawos.sh
```

MySQL доступен только локально на `127.0.0.1:3307`. Настройки для разработки
можно изменить, скопировав `docker/.env.example` в `docker/.env` до первого
запуска.

## Просмотр данных

Подключитесь к базе из DBeaver, DataGrip или другого MySQL-клиента:

| Параметр | Значение по умолчанию |
|---|---|
| Host | `127.0.0.1` |
| Port | `3307` |
| Database | `tawos` |
| User | `tawos` |
| Password | `tawos_dev_password` |

Быстро открыть MySQL CLI без установки клиента на компьютер:

```bash
docker compose -f docker/docker-compose.tawos.yaml exec mysql \
  mysql -utawos -ptawos_dev_password tawos
```

Остановить MySQL с сохранением данных:

```bash
docker compose -f docker/docker-compose.tawos.yaml down
```

Именованный volume позволяет повторно запускать контейнер без нового импорта.
Команда ниже полностью удаляет импортированную базу; исходный SQL dump останется
на месте:

```bash
docker compose -f docker/docker-compose.tawos.yaml down --volumes
```

## Источник

- [TAWOS dataset, UCL Figshare](https://doi.org/10.5522/04/21308124)
- [Описание и схема](https://github.com/SOLAR-group/TAWOS)
- V. Tawosi et al., *A Versatile Dataset of Agile Open Source Software
  Projects*, MSR 2022, DOI: 10.1145/3524842.3528029.
