#!/usr/bin/env python3
"""
Script to automatically send e-mails if a new file was found on the scanner's sdcard
"""
import os

import magic
import re
from collections import namedtuple
from datetime import datetime
import logging
from apscheduler.schedulers.background import BlockingScheduler
import smtplib
from email.mime.nonmultipart import MIMENonMultipart
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email import encoders
import configargparse
import smbc
from abc import ABC, abstractmethod
from webdav3.client import Client

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("requests").setLevel(logging.INFO)
logger = logging.getLogger("scansmb")

MailConfig = namedtuple('MailConfig', ['mail_from', 'mail_to', 'user', 'password', 'host', 'port'])
WebDavConfig = namedtuple('WebDavConfig', ['host', 'user', 'password', 'path'])

mime = magic.Magic(mime=True)


class ArgumentRequiredMode(Exception):
    def __init__(self, argument, mode):
        self.argument = argument
        self.mode = mode

    def __str__(self):
        format = 'argument %(argument_name)s is required for mode %(mode)s'
        return format % dict(argument_name=self.argument, mode=self.mode)


class DocumentStore(ABC):

    @abstractmethod
    def submit_document(self, document, ext, mtime):
        pass


class SMTPDocumentStore(DocumentStore):
    def __init__(self, mail_config):
        self.mail_config = mail_config

    def submit_document(self, document, ext, mtime):
        msg = MIMEMultipart()

        msg["Subject"] = "New Scan!"
        msg["From"] = self.mail_config.mail_from
        msg["To"] = self.mail_config.mail_to

        mime_type = mime.from_buffer(document).split("/", 1)

        attachment = MIMENonMultipart(mime_type[0], mime_type[1])
        attachment.add_header("Content-Disposition", "attachment",
                              filename="scan-{timestamp}.{ext}".format(timestamp=mtime.strftime("%Y_%m_%d-%H%M%S"),
                                                                       ext=ext))
        attachment.set_payload(document)
        encoders.encode_base64(attachment)
        msg.attach(attachment)
        msg.attach(MIMEText("""Hey!
        
I found a new scan on your printer. You can find it in the attachments :)

Regards
Scan-Bot
"""))

        s = smtplib.SMTP(self.mail_config.host, self.mail_config.port)
        s.starttls()
        s.login(self.mail_config.user, self.mail_config.password)
        s.send_message(msg)


class WebDavDocumentStore(DocumentStore):
    def __init__(self, webdav_config):
        self.webdav_config = webdav_config

    def submit_document(self, document, ext, mtime):
        options = {
            'webdav_hostname': self.webdav_config.host,
            'webdav_login': self.webdav_config.user,
            'webdav_password': self.webdav_config.password,
        }
        client = Client(options)
        ul_path = "/"
        if self.webdav_config.path is not None:
            ul_path = self.webdav_config.path
        client.upload_to(buff=document, remote_path=os.path.join(ul_path, "scan-{timestamp}.{ext}".format(
            timestamp=mtime.strftime("%Y_%m_%d-%H%M%S"), ext=ext)))


def get_auth_data(server, share, workgroup, username, password):
    """
    auth callback method for smb context
    this method is called by libsmbclient whenever it needs auth information
    epson printers accept any user/pass combination
    """
    user = "default"
    password = "default"
    workspace = "WORKGROUP"

    return (workspace, user, password)


def scan_path(hostname, model="epson"):
    if "epson" in model:
        return "smb://{hostname}/MEMORYCARD/EPSCAN".format(hostname=hostname)
    else:
        return ""


def get_path(entries, ent_type, root=""):
    """
    Return every dirname in this dir that is not ./.. or not of the given type
    """
    prefix = root + "/" if len(root) > 0 else ""
    return list(map(lambda x: prefix + x.name,
                    filter(lambda x: x.smbc_type == ent_type and not re.match(r'^[\.]+$', x.name), entries)))


def ls(ctx, root, ent_type=smbc.DIR, recursive=False):
    entries = ctx.opendir(root).getdents()

    dir_names = get_path(entries, smbc.DIR, root)

    if ent_type == smbc.FILE:
        file_names = get_path(entries, smbc.FILE, root)

    if recursive and len(dir_names) > 0:
        recv_dirs = []
        recv_dirs.extend(file_names if ent_type == smbc.FILE else dir_names)
        for d in dir_names:
            recv_dirs.extend(ls(ctx, d, ent_type, recursive=True))
        return recv_dirs

    return dir_names if ent_type == smbc.DIR else file_names


def loop(ctx, printer_host, store):
    logger.debug("starting loop")
    try:
        for file in ls(ctx, scan_path(printer_host), ent_type=smbc.FILE, recursive=True):
            logger.info("found file {}".format(file))
            mtime = datetime.fromtimestamp(ctx.stat(file)[8])
            ext = os.path.splitext(file)[1].lower().strip('.')
            dl = ctx.open(file).read()
            store.submit_document(dl, ext, mtime)
            ctx.unlink(file)  # Remove the scan after sending the email
    except Exception as e:
        logger.error(e)


def main():
    parser = configargparse.ArgParser(default_config_files=['scansmb.conf'])
    parser.add("-c", "--config", is_config_file=True, help="config file path", env_var="CONFIG")
    parser.add("-p", "--printer-host", required=True,
               help="printer hostname", env_var="PRINTER_HOST")
    parser.add("--once", help="run once", action='store_true')
    parser.add("--mode", required=True, choices=["mail", "webdav"], help="operation mode", env_var="MODE")
    parser.add("--smtp-user",
               help="smtp server username", env_var="SMTP_USERNAME")
    parser.add("--smtp-password",
               help="smtp server password", env_var="SMTP_PASSWORD")
    parser.add("--smtp-port",
               help="smtp server port", env_var="SMTP_PORT")
    parser.add("--smtp-host",
               help="smtp host", env_var="SMTP_HOST")
    parser.add("-f", "--mail-from",
               help="email from address", env_var="MAIL_FROM")
    parser.add("-t", "--mail-to",
               help="email recipient", env_var="MAIL_TO")
    parser.add("--webdav-host", help="webdav host", env_var="WEBDAV_HOST")
    parser.add("--webdav-username", help="webdav username", env_var="WEBDAV_USERNAME")
    parser.add("--webdav-password", help="webdav password", env_var="WEBDAV_PASSWORD")
    parser.add("--webdav-path", help="webdav path", env_var="WEBDAV_PATH")

    options = parser.parse_args()

    store = None
    if options.mode == "mail":
        if options.smtp_user is None:
            raise ArgumentRequiredMode("--smtp-user", options.mode)
        if options.smtp_password is None:
            raise ArgumentRequiredMode("--smtp-password", options.mode)
        if options.smtp_port is None:
            raise ArgumentRequiredMode("--smtp-port", options.mode)
        if options.smtp_host is None:
            raise ArgumentRequiredMode("--smtp-host", options.mode)
        if options.mail_to is None:
            raise ArgumentRequiredMode("--mail-to", options.mode)

        if options.mail_from is None:
            options.mail_from = options.smtp_user

        mail_config = MailConfig(mail_from=options.mail_from, mail_to=options.mail_to, user=options.smtp_user,
                                 password=options.smtp_password, host=options.smtp_host, port=options.smtp_port)
        store = SMTPDocumentStore(mail_config)
    elif options.mode == "webdav":
        if options.webdav_host is None:
            raise ArgumentRequiredMode("--webdav-host", options.mode)
        if options.webdav_username is None:
            raise ArgumentRequiredMode("--webdav-username", options.mode)
        if options.webdav_password is None:
            raise ArgumentRequiredMode("--webdav-password", options.mode)
        webdav_config = WebDavConfig(host=options.webdav_host, user=options.webdav_username,
                                     password=options.webdav_password, path=options.webdav_path)
        store = WebDavDocumentStore(webdav_config)

    ctx = smbc.Context(auth_fn=get_auth_data, client_ntlmv2_auth="no", client_use_spnego="no")

    logger.info("Started! Looking for scans...")
    logger.info(parser.format_values())

    loop(ctx, options.printer_host, store)
    if not options.once:
        scheduler = BlockingScheduler()
        scheduler.add_job(loop, 'interval', minutes=1, args=[ctx, options.printer_host, store])
        scheduler.start()


if __name__ == "__main__":
    main()
