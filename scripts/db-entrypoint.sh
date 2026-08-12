#!/bin/sh
# Получает параметры PostgreSQL ИСКЛЮЧИТЕЛЬНО из конфиг-сервиса
# (GET {URL}/config/{CONFIG_PROJECT_DB_NAME}?format=env) и запускает
# штатный entrypoint образа postgres. В .env только ссылки.
set -eu

CONFIG_SERVICE_URL="${CONFIG_SERVICE_URL:-http://host.docker.internal:8420}"
CONFIG_PROJECT_DB_NAME="${CONFIG_PROJECT_DB_NAME:-postgress}"

# localhost внутри контейнера — сам контейнер; переписываем на хост.
CONFIG_SERVICE_URL="$(printf '%s' "$CONFIG_SERVICE_URL" | sed -E \
  -e 's#http://localhost:#http://host.docker.internal:#' \
  -e 's#http://127\.0\.0\.1:#http://host.docker.internal:#')"
CONFIG_SERVICE_URL="${CONFIG_SERVICE_URL%/}"

# Токен: из окружения или из общего volume resources/config_token.txt
# (его пишет сайт, когда админ вводит токен в блокирующем окне).
CONFIG_TOKEN="${CONFIG_TOKEN:-}"
if [ -z "$CONFIG_TOKEN" ] && [ -f /resources/config_token.txt ]; then
    CONFIG_TOKEN="$(tr -d '\r\n' < /resources/config_token.txt || true)"
fi

# Скачивает конфиг проекта в временный файл; печатает путь к нему.
# При неудаче печатает понятную диагностику (в т.ч. различает 401 от
# отсутствия сети) и возвращает 1.
fetch_config() {
    url="${CONFIG_SERVICE_URL}/config/${CONFIG_PROJECT_DB_NAME}?format=env"
    tmp="$(mktemp)"
    errlog="${tmp}.err"
    if [ -n "$CONFIG_TOKEN" ]; then
        http_code="$(curl -fsSL --max-time 10 -H "Authorization: Bearer ${CONFIG_TOKEN}" \
            -w '%{http_code}' -o "$tmp" "$url" 2>"$errlog" || true)"
    else
        http_code="$(curl -fsSL --max-time 10 -w '%{http_code}' -o "$tmp" "$url" 2>"$errlog" || true)"
    fi
    if [ -s "$tmp" ]; then
        rm -f "$errlog"
        printf '%s' "$tmp"
        return 0
    fi
    case "$http_code" in
        [0-9][0-9][0-9]) status="HTTP $http_code" ;;
        *) status="сетевая ошибка (curl: $http_code)" ;;
    esac
    echo "db-entrypoint: конфиг-сервис $CONFIG_SERVICE_URL не отдал конфиг проекта '$CONFIG_PROJECT_DB_NAME': $status." >&2
    if [ "$http_code" = "401" ]; then
        echo "db-entrypoint: 401 Unauthorized — нужен валидный CONFIG_TOKEN или resources/config_token.txt." >&2
    fi
    if [ -s "$errlog" ]; then
        sed 's/^/db-entrypoint: /' "$errlog" >&2 || true
    fi
    rm -f "$errlog" "$tmp"
    return 1
}

# Ждём до 60 попыток по 5 секунд, пока сервис не отдаст конфиг.
config_file=""
attempt=0
while :; do
    attempt=$((attempt + 1))
    config_file="$(fetch_config || true)"
    if [ -n "$config_file" ] && [ -s "$config_file" ]; then
        break
    fi
    if [ -n "$config_file" ]; then
        rm -f "$config_file"
        config_file=""
    fi
    if [ "$attempt" -ge 60 ]; then
        echo "db-entrypoint: не удалось получить конфиг проекта '$CONFIG_PROJECT_DB_NAME' из $CONFIG_SERVICE_URL (60 попыток)." >&2
        exit 1
    fi
    echo "db-entrypoint: конфиг-сервис недоступен, повтор через 5 с (попытка $attempt/60)."
    sleep 5
done

# Извлекает значение KEY из env-файла (без кавычек и переноса строк).
fetch_value() {
    key="$1"
    file="$2"
    value="$(grep "^${key}=" "$file" | head -n1 | cut -d= -f2- | tr -d '\r')"
    case "$value" in
        \"*\" | \'*\') value="${value#?}"; value="${value%?}" ;;
    esac
    printf '%s' "$value"
}

PGUSER="$(fetch_value PGUSER "$config_file")"
PGDATABASE="$(fetch_value PGDATABASE "$config_file")"
PGPASSWORD="$(fetch_value PGPASSWORD "$config_file")"
PGPORT="$(fetch_value PGPORT "$config_file")"

# Порт передаётся healthcheck'у docker-compose (может быть нестандартным).
printf '%s' "${PGPORT:-5432}" > /tmp/pgport

if [ -z "$PGUSER" ] || [ -z "$PGDATABASE" ]; then
    echo "db-entrypoint: конфиг проекта '$CONFIG_PROJECT_DB_NAME' не содержит PGUSER/PGDATABASE." >&2
    exit 1
fi

# Передаём параметры штатному docker-entrypoint.sh образа postgres.
export POSTGRES_USER="$PGUSER"
export POSTGRES_DB="$PGDATABASE"
export POSTGRES_PASSWORD="$PGPASSWORD"

# Порт по умолчанию (если в конфиг-сервисе не указан).
PGPORT="${PGPORT:-5432}"

# Если БД уже инициализирована, штатный entrypoint не обновит пароль
# (он задаётся только при initdb) — синхронизируем его принудительно:
# pg_hba.conf настроен на trust, поэтому временный socket-only сервер
# выполнит ALTER USER без пароля.
if [ -s "$PGDATA/PG_VERSION" ]; then
    echo "db-entrypoint: БД уже существует — обновляем пароль пользователя '$PGUSER'"
    # pg_ctl отказывается работать от root — временный сервер запускаем
    # от postgres; слушает только unix-сокет, порт как у основного.
    if su-exec postgres pg_ctl -D "$PGDATA" -w start \
        -o "-c listen_addresses='' -p '$PGPORT'"; then
        ALTER_SQL="ALTER USER \"$PGUSER\" WITH PASSWORD '$PGPASSWORD';"
        su-exec postgres psql -v ON_ERROR_STOP=1 -U "$PGUSER" \
             -h /var/run/postgresql -p "$PGPORT" -d postgres -c "$ALTER_SQL"
        su-exec postgres pg_ctl -D "$PGDATA" -m fast -w stop
    else
        echo "db-entrypoint: не удалось запустить временный PostgreSQL для обновления пароля." >&2
        exit 1
    fi
fi

# Нестандартный порт из конфиг-сервиса передаём postgres как опцию.
if [ -n "$PGPORT" ] && [ "$PGPORT" != "5432" ]; then
    set -- postgres -p "$PGPORT"
fi

rm -f "$config_file"
echo "db-entrypoint: параметры PostgreSQL получены из конфиг-сервиса: user=$PGUSER db=$PGDATABASE port=${PGPORT:-5432}"
exec /usr/local/bin/docker-entrypoint.sh "$@"
