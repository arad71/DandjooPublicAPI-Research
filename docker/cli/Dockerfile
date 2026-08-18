FROM python:3.8-slim-bullseye

LABEL name="Dandjoo CLI"

RUN apt-get update && apt-get install -y curl

RUN apt-get install -y wkhtmltopdf

RUN apt-get install -y git

RUN apt-get install -y build-essential

RUN curl -sSL https://install.python-poetry.org | python3 -

ENV PATH="${PATH}:/root/.local/bin"

RUN mkdir dandjoo-public-api
WORKDIR /dandjoo-public-api

COPY ./poetry.lock pyproject.toml /dandjoo-public-api/

RUN poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi

COPY ./scripts /dandjoo-public-api/scripts

CMD ["/bin/bash"]
