FROM python:3.7-buster

WORKDIR /usr/src/app

RUN apt-get update && \
    apt-get install -y --no-install-recommends libsmbclient-dev && \
    rm -rf /var/lib/apt/lists/*

COPY Pipfile .
COPY Pipfile.lock .
RUN pip install --no-cache-dir pipenv
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy
ENV PATH="/usr/src/app/.venv/bin:$PATH"

COPY scansmb.py .

ENTRYPOINT [ "python", "./scansmb.py" ]
