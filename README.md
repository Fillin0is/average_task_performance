# Average task performance

Исследовательский проект для прогнозирования календарной длительности выполнения
задач из открытого датасета TAWOS 1.1.

В проекте находятся SQL-запрос для формирования обучающей выборки, ноутбуки для
анализа и обучения baseline-моделей, а также экспериментальный FastAPI-сервис.
Сам датасет, содержимое MySQL и обученные модели в Git не хранятся.

## Требования

- Git;
- Python 3.12;
- [uv](https://docs.astral.sh/uv/);
- Docker с поддержкой `docker compose`;
- Git Bash с `curl`, `unzip` и `md5sum` для загрузки датасета;
- около 17 ГБ свободного места.

Подробная инструкция для Windows находится в [docs/SETUP.md](docs/SETUP.md),
а описание таблиц TAWOS — в
[docs/DATABASE_DICTIONARY_RU.md](docs/DATABASE_DICTIONARY_RU.md).

## Установка проекта

```powershell
git clone https://github.com/Fillin0is/average_task_performance.git
cd average_task_performance
uv sync
Copy-Item docker\.env.example docker\.env
```

Все дальнейшие команды выполняются из корня проекта.

## Загрузка и запуск TAWOS

Скачайте и распакуйте официальный дамп через Git Bash:

```bash
./scripts/download_tawos.sh
```

Запустите MySQL и CloudBeaver:

```powershell
docker compose -f docker/docker-compose.tawos.yaml up -d
```

При первом запуске MySQL импортирует `data/raw/tawos/TAWOS.sql`. Проверить
состояние контейнеров и импорт можно командами:

```powershell
docker compose -f docker/docker-compose.tawos.yaml ps
docker compose -f docker/docker-compose.tawos.yaml logs -f mysql
```

После окончания импорта выполните в Git Bash:

```bash
./scripts/check_tawos.sh
```

MySQL доступен с компьютера на `127.0.0.1:3307`. Значения по умолчанию:

| Параметр | Значение |
|---|---|
| Database | `tawos` |
| User | `tawos` |
| Password | `tawos_dev_password` |

CloudBeaver открывается по адресу `http://127.0.0.1:8978`. Для подключения из
CloudBeaver используйте хост `mysql`, порт `3306` и драйвер MariaDB. В свойствах
драйвера установите `allowPublicKeyRetrieval=true` и `sslMode=disable`.

Остановить контейнеры с сохранением базы:

```powershell
docker compose -f docker/docker-compose.tawos.yaml down
```

## Анализ и обучение моделей

Проверить Python-подключение к MySQL:

```powershell
uv run python -m data_access.connection
```

Запустить JupyterLab:

```powershell
uv run jupyter lab
```

Ноутбуки расположены в `data_access/notebooks/`:

1. `01_data_audit.ipynb` — первичный анализ таблиц и качества данных;
2. `02_dataset_check.ipynb` — проверка итоговой обучающей выборки;
3. `03_general_baseline.ipynb` — baseline с одной регрессией;
4. `04_duration_buckets_baseline.ipynb` — текущий эксперимент с четырьмя временными
   бакетами: 0–1, 1–7, 7–30 и 30–365 дней.

Обучающая выборка формируется запросом
`data_access/queries/training_dataset.sql`. В текущем эксперименте используются
четыре признака:

- `Description_Issue_Length`;
- `Description_Project_Length`;
- `Initial_Type`;
- `Initial_Priority`.

Приоритет нормализуется в одну из категорий `P1`, `P2`, `P3`, `P4`, `P5` или
`Unassigned`. Целевая переменная — `Duration_Days`.

## API

Запуск сервера:

```powershell
uv run uvicorn api.main:app --reload
```

Swagger доступен по адресу `http://127.0.0.1:8000/docs`.

Пример запроса:

```text
GET /predict?description_issue_length=500&description_project_length=146&initial_type=Bug&initial_priority=P3
```

API передаёт модели те же четыре признака, что используются в текущем
ноутбуке. По умолчанию сервис ищет совместимый joblib-артефакт по пути
`artifacts/duration_model.joblib`; путь можно переопределить переменной окружения
`DURATION_MODEL_PATH`.

Автоматическое сохранение четырёх моделей и выбор нужного временного бакета для
новой задачи пока не реализованы. Поэтому API остаётся экспериментальным и без
совместимого артефакта отвечает статусом `503`.

## Тесты

```powershell
uv run pytest
```

## Источники

- [TAWOS dataset, UCL Figshare](https://doi.org/10.5522/04/21308124)
- [Описание и схема TAWOS](https://github.com/SOLAR-group/TAWOS)
- V. Tawosi et al., *A Versatile Dataset of Agile Open Source Software
  Projects*, MSR 2022, DOI: 10.1145/3524842.3528029.
