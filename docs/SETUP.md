# Подготовка данных и запуск проекта на другом компьютере

Памятка описывает полный запуск проекта на Windows: загрузку TAWOS 1.1,
импорт в MySQL, просмотр через CloudBeaver и работу с данными из Python и
JupyterLab.

## 1. Что потребуется

- Git;
- Docker Desktop с поддержкой `docker compose`;
- Python 3.12;
- Git Bash с командами `curl`, `unzip` и `md5sum`;
- не менее 17 ГБ свободного места.

Docker Desktop должен быть запущен перед выполнением Docker-команд.

## 2. Клонирование проекта

В PowerShell:

```powershell
git clone https://github.com/Fillin0is/average_task_performance.git
cd average_task_performance
```

Все последующие команды выполняются из корня проекта.

## 3. Настройка окружения Docker

Создайте локальный файл с настройками базы:

```powershell
Copy-Item docker\.env.example docker\.env
```

Значения по умолчанию:

| Параметр | Значение |
|---|---|
| Database | `tawos` |
| User | `tawos` |
| Password | `tawos_dev_password` |
| MySQL с компьютера | `127.0.0.1:3307` |
| CloudBeaver | `http://127.0.0.1:8978` |

Файл `docker/.env` не сохраняется в Git. При необходимости пароли и локальный
порт можно изменить до первого запуска MySQL.

## 4. Загрузка датасета

Откройте Git Bash в корне проекта и выполните:

```bash
./scripts/download_tawos.sh
```

Скрипт:

1. скачает официальный архив TAWOS размером около 608 МБ;
2. проверит MD5;
3. распакует SQL-дамп размером около 4,1 ГБ в
   `data/raw/tawos/TAWOS.sql`.

Прерванную загрузку можно продолжить повторным запуском той же команды.

Если готовый дамп переносится с другого компьютера, достаточно скопировать его
в `data/raw/tawos/TAWOS.sql` и пропустить загрузку.

## 5. Запуск MySQL и CloudBeaver

Вернитесь в PowerShell и выполните:

```powershell
docker compose `
  -f docker/docker-compose.tawos.yaml `
  up -d
```

Первый запуск импортирует SQL-дамп в именованный Docker volume. Импорт может
занять от нескольких минут до получаса. Смотреть журнал:

```powershell
docker compose `
  -f docker/docker-compose.tawos.yaml `
  logs -f mysql
```

Завершение импорта обозначается сообщением:

```text
MySQL init process done. Ready for start up.
```

Выйти из просмотра логов можно через `Ctrl+C`: контейнеры продолжат работать.

После завершения импорта его можно проверить из Git Bash:

```bash
./scripts/check_tawos.sh
```

Проверить контейнеры:

```powershell
docker compose `
  -f docker/docker-compose.tawos.yaml `
  ps
```

## 6. Просмотр данных в CloudBeaver

Откройте в браузере:

```text
http://127.0.0.1:8978
```

При первом запуске создайте локального администратора CloudBeaver. Затем
создайте подключение с драйвером **MariaDB**:

| Поле | Значение |
|---|---|
| Host | `mysql` |
| Port | `3306` |
| Database | `tawos` |
| User | `tawos` |
| Password | `tawos_dev_password` |

В `Driver properties` добавьте:

```text
allowPublicKeyRetrieval = true
sslMode = disable
```

CloudBeaver обращается к MySQL внутри Docker-сети, поэтому использует
`mysql:3306`, а не внешний адрес `127.0.0.1:3307`.

После подключения раскройте `tawos -> Tables`. Таблицу можно открыть через
контекстное меню `View Data`. SQL-запрос выполняется в `SQL Editor` через
`Ctrl+Enter`, например:

```sql
SELECT
    Issue_Key,
    Title,
    Type,
    Priority,
    Status
FROM Issue
LIMIT 100;
```

## 7. Python-окружение

Создайте виртуальное окружение в PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

Если PowerShell запрещает активацию:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Если установлен `uv`, вместо команд выше достаточно:

```powershell
uv sync
```

Проверка подключения Python к MySQL:

```powershell
python -m data_access.connection
```

Проверка загрузки DataFrame:

```powershell
python -m data_access.loaders
```

Python запускается на компьютере, поэтому в `data_access/connection.py`
используется внешний адрес MySQL `127.0.0.1:3307`.

## 8. Запуск JupyterLab

При активном `.venv`:

```powershell
python -m jupyter lab
```

Откройте существующий notebook `data_access/loaders.ipynb` или создайте новый.
Пример ячейки:

```python
from data_access.loaders import df

df.head(20)
```

Для интерактивного табличного просмотра можно установить пакет в текущее
ядро notebook:

```python
%pip install itables
```

```python
from itables import show

show(df)
```

Не загружайте целиком `Comment` и `Change_Log`: в них миллионы строк. Для
первичного исследования используйте выбранные столбцы, `WHERE` и `LIMIT`.

## 9. Остановка и повторный запуск

Остановить контейнеры с сохранением импортированной базы:

```powershell
docker compose `
  -f docker/docker-compose.tawos.yaml `
  down
```

Повторный запуск:

```powershell
docker compose `
  -f docker/docker-compose.tawos.yaml `
  up -d
```

Повторный импорт не выполняется, пока существует volume
`average-task-performance-tawos_tawos_mysql_data`.

Полностью удалить импортированную базу и настройки CloudBeaver:

```powershell
docker compose `
  -f docker/docker-compose.tawos.yaml `
  down --volumes
```

Эта команда удаляет Docker volumes. SQL-дамп в `data/raw/tawos/` остаётся и
будет импортирован снова при следующем запуске.

Деактивировать Python-окружение:

```powershell
deactivate
```

Само окружение `.venv` можно удалить и создать заново; исходный код, notebook
и данные MySQL от этого не удаляются.

## 10. Частые проблемы

### `TAWOS.sql` отсутствует

Повторно запустите в Git Bash:

```bash
./scripts/download_tawos.sh
```

### CloudBeaver не соединяется с MySQL

- проверьте, что оба контейнера имеют статус `Up`;
- внутри CloudBeaver используйте `mysql:3306`;
- установите `allowPublicKeyRetrieval=true`;
- дождитесь окончания первоначального импорта.

### Python не соединяется с MySQL

- убедитесь, что Docker Desktop и контейнер MySQL запущены;
- из Python на компьютере используйте `127.0.0.1:3307`;
- проверьте порт:

```powershell
Test-NetConnection 127.0.0.1 -Port 3307
```

### Jupyter не видит библиотеки проекта

Запускайте его после активации `.venv`:

```powershell
.\.venv\Scripts\Activate.ps1
python -m jupyter lab
```
