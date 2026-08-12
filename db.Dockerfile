# Образ PostgreSQL: параметры БД (POSTGRES_USER/PASSWORD/DB) берутся
# ИСКЛЮЧИТЕЛЬНО из конфиг-сервиса — их получает db-entrypoint.sh (curl),
# который затем вызывает штатный docker-entrypoint.sh образа postgres.
FROM postgres:16-alpine

# curl нужен entrypoint-скрипту для запроса к конфиг-сервису;
# dos2unix нормализует CRLF в скрипте (иначе ломается shebang).
RUN apk add --no-cache curl dos2unix

COPY scripts/db-entrypoint.sh /usr/local/bin/db-entrypoint.sh
RUN dos2unix /usr/local/bin/db-entrypoint.sh \
    && chmod +x /usr/local/bin/db-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/db-entrypoint.sh"]
CMD ["postgres"]
