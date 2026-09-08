# CLAUDE.md

Этот файл содержит инструкции для Claude Code (claude.ai/code) при работе с кодом в этом репозитории.

## О проекте

Исследовательский проект по прогнозированию времени решения программных задач
на открытом датасете TAWOS 1.1 (39 open-source проектов, дамп MySQL, ~608 МБ
архив / ~4.1 ГБ распакованный). Сам датасет и данные MySQL не хранятся в Git.

- `docs/DATABASE_DICTIONARY_RU.md` — полное описание схемы БД и связей.
- `docs/SETUP.md` — пошаговая инструкция по развёртыванию (ориентирована на Windows).
- `docs/NOTE.md` — рабочие заметки/решения по выбору целевой метки, фильтрации и т.д.

## Команды

Менеджер пакетов — `uv` (альтернатива: `pip install -e .` + venv, см. `docs/SETUP.md`).

```powershell
# установка зависимостей
uv sync

# поднять MySQL с TAWOS + CloudBeaver (данные должны быть уже скачаны в data/raw/tawos/)
docker compose -f docker/docker-compose.tawos.yaml up -d
./scripts/check_tawos.sh

# скачать датасет (Git Bash)
./scripts/download_tawos.sh

# обучить baseline-модель -> artifacts/duration_model.joblib + reports/baseline_metrics.json
uv run python -m ml.train

# запустить API (Swagger на http://127.0.0.1:8000/docs)
uv run uvicorn api.main:app --reload

# тесты
uv run pytest
uv run pytest tests/test_api.py::test_predict_bug   # один тест

# проверка подключения к БД / примера загрузчика
python -m data_access.connection
python -m data_access.loaders
```

Важно: модуль `ml/` (тот самый `python -m ml.train`, на который ссылаются README,
сообщения об ошибках в `api/main.py` и список пакетов в `pyproject.toml`) в
репозитории пока физически отсутствует — обучение модели и получение
`artifacts/duration_model.joblib` сейчас нужно делать иначе (например, из
ноутбука), прежде чем `api/main.py` сможет отдавать предсказания.

## Архитектура

- **`data_access/connection.py`** — единственный SQLAlchemy `engine` для MySQL
  с TAWOS. Захардкожен на адрес со стороны хоста `127.0.0.1:3307` (порт, в который
  Docker пробрасывает контейнер), а не на внутрисетевой адрес `mysql:3306`,
  которым пользуется CloudBeaver.
- **`data_access/loaders.py`** — пример/референсный загрузчик через
  `pandas.read_sql_query` поверх `engine`. Таблицы `Comment` и `Change_Log`
  содержат миллионы строк — всегда фильтровать через `WHERE`/`LIMIT`, никогда не
  загружать их целиком.
- **`data_access/queries/training_dataset.sql`** — основной запрос, формирующий
  обучающий датасет из сырых таблиц `Issue`/`Change_Log`. В нём вычисляются:
  - `Duration_Days` (целевая переменная): `Resolution_Date - Creation_Date`, с
    ограничением на задачи, решённые в промежутке от 5 минут до 8 лет после
    создания (почему выбрано именно такое окно и что стоит за приоритетом/статусом
    — см. `docs/NOTE.md`).
  - `initial_priority` / `initial_type`: *первое* значение `Priority`/`Type` из
    `Change_Log`, а если поле никогда не менялось — текущее значение
    `Issue.Priority`/`Issue.Type`. Это сделано потому, что у задач в Jira
    приоритет/тип часто переназначают уже после создания, а модель должна
    обучаться на том, что было известно в момент создания задачи, а не на
    финальном значении.
  - `Description_Length`: `CHAR_LENGTH` от `Description_Text`.
- **`data_access/notebooks/`** — исследовательские ноутбуки (аудит данных,
  проверка датасета, baseline-моделирование); именно здесь прорабатываются
  решения по датасету/признакам, прежде чем они попадают в `data_access/queries/`
  или (в перспективе) в `ml/`.
- **`api/main.py`** — FastAPI-приложение с единственным эндпоинтом
  `GET /predict`. Загружает joblib-сериализованный бандл `{"model": ...}`
  (`load_model_bundle`, кешируется через `lru_cache`) из
  `artifacts/duration_model.joblib` (путь можно переопределить переменной
  окружения `DURATION_MODEL_PATH`). Словарь признаков, собираемый из query-
  параметров, должен точно совпадать с именами признаков при обучении:
  `Description_Length`, `initial_type`, `initial_priority`. Если файл модели
  отсутствует — возвращается HTTP 503.
- **`tests/test_api.py`** — подменяет `api_main.load_model_bundle` через
  monkeypatch на заглушку модели, поэтому тестам не нужен реально обученный
  артефакт.
- **`docker/docker-compose.tawos.yaml`** — MySQL 8.0.44 (при первом запуске
  импортирует `data/raw/tawos/TAWOS.sql` через `docker-entrypoint-initdb.d`) +
  CloudBeaver для просмотра данных. MySQL проброшен на хост как
  `127.0.0.1:3307`; CloudBeaver обращается к нему внутри сети как `mysql:3306`.
  Настройки берутся из `docker/.env` (копируется из `docker/.env.example`, сам
  не коммитится). Повторный `up -d` не переимпортирует данные, пока существует
  именованный volume; `down --volumes` удаляет импортированную БД (сам SQL-дамп
  на диске не затрагивается).

## Особенности данных/целевой метки, важные перед изменением логики обучения

Подробности — в `docs/NOTE.md`. Кратко:
- Не у всех задач есть `Resolution_Date`; такие задачи не имеют полезной целевой
  метки и являются кандидатами в тестовую/инференс-выборку, а не в обучающую.
- ~24% закрытых задач хотя бы раз меняли `Status`, но статус не влияет на
  целевую переменную — в отличие от приоритета.
- У многих задач изначально вообще не был проставлен приоритет — только у
  ~79 691 задачи приоритет реально был задан в момент создания, поэтому
  `initial_priority` и вычисляется с откатом через `Change_Log`, как описано
  выше.
