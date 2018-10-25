# scansmb

Checks the smb share of a printer (currently optimized for epson printers) for new files and sends them to the configures recipients

## About

The script uses the pysmbc library to bind to libsmbclient.
It will check the printer's smb share every minute and pull new files to send them as an email.

The printer has to be equipped with a sd card and the smb fileshare has to be enabled.

## Installation

It depends on:

- [pysmbc](https://github.com/hensur/pysmbc)
- [configargparse](https://github.com/bw2/ConfigArgParse)
- [python-magic](https://github.com/ahupp/python-magic)
- [apscheduler](https://github.com/agronholm/apscheduler)

Install them with pip:
```
pip install -r requirements.txt
```

## Usage

It can be configured by commandline arguments, environment variables and config file thanks to the configargparse library.
A sample configration that configures the smtp server is provided in `scansmb.example.conf`

Start it on the command line like this (this example makes use of all means of configuration):
```
PRINTER_HOST=192.168.8.111 python3 scansmb.py -c scansmb.conf -f scan@example.com -t you@example.com
```

Multiple Recipients can be supplied as a comma separated list: `scan@example.com,scan2@example.com`

Or use the docker image at [dockerhub](https://hub.docker.com/r/hensur/scansmb):
```
docker run -v $(pwd)/scansmb.conf:/scansmb.conf -e PRINTER_HOST=192.168.8.111 -e MAIL_FROM=scan@example.com -e MAIL_TO=you@example.com -e CONFIG=/scansmb.conf hensur/scansmb
```
