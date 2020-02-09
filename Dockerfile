FROM python:3.7

WORKDIR /usr/src/app

RUN apt-get update && \
    apt-get install -y --no-install-recommends libsmbclient-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY scansmb.py .

ENTRYPOINT [ "python", "./scansmb.py" ]
