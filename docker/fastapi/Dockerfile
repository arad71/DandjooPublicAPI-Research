FROM python:3.10-slim-bullseye


LABEL name="Dandjoo API Application"

RUN apt-get update && \
    apt-get install -y wkhtmltopdf curl git build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*



RUN apt-get install -y wkhtmltopdf

RUN apt-get install -y git

RUN apt-get install -y --reinstall build-essential

RUN pip install poetry
# RUN curl -sSL https://install.python-poetry.org | python3 -

ENV PATH="${PATH}:/root/.local/bin"

RUN mkdir dandjoo-public-api
WORKDIR /dandjoo-public-api

COPY ./poetry.lock pyproject.toml /dandjoo-public-api/
COPY ./app /dandjoo-public-api/app

RUN poetry config virtualenvs.create false && poetry install --only main --no-interaction --no-ansi

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--proxy-headers", "--forwarded-allow-ips", "*"]
