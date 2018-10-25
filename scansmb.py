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


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("scansmb")

MailConfig = namedtuple('MailConfig', ['mail_from', 'mail_to', 'user', 'password', 'host', 'port'])

mime = magic.Magic(mime=True)

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
    return list(map(lambda x: prefix + x.name, filter(lambda x: x.smbc_type == ent_type and not re.match(r'^[\.]+$', x.name), entries)))


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


def sendMail(document, ext, mtime, mail_config):
    msg = MIMEMultipart()

    msg["Subject"] = "New Scan!"
    msg["From"] = mail_config.mail_from
    msg["To"] = mail_config.mail_to

    mime_type = mime.from_buffer(document).split("/", 1)

    attachment = MIMENonMultipart(mime_type[0], mime_type[1])
    attachment.add_header("Content-Disposition", "attachment",
                   filename="scan-{timestamp}.{ext}".format(timestamp=mtime.strftime("%Y_%m_%d-%H%M%S"), ext=ext))
    attachment.set_payload(document)
    encoders.encode_base64(attachment)
    msg.attach(attachment)
    msg.attach(MIMEText("""Hey!

I found a new scan on your printer. You can find it in the attachments :)

Regards
Scan-Bot
"""))

    s = smtplib.SMTP(mail_config.host, mail_config.port)
    s.starttls()
    s.login(mail_config.user, mail_config.password)
    s.send_message(msg)


def loop(ctx, printer_host, mail_config):
    logger.debug("starting loop")
    try:
        for file in ls(ctx, scan_path(printer_host), ent_type=smbc.FILE, recursive=True):
            logger.info("found file {}".format(file))
            mtime = datetime.fromtimestamp(ctx.stat(file)[8])
            ext = os.path.splitext(file)[1].lower().strip('.')
            dl = ctx.open(file).read()
            sendMail(dl, ext, mtime, mail_config)
            ctx.unlink(file)  # Remove the scan after sending the email
    except Exception as e:
        logger.error(e)


def main():
    parser = configargparse.ArgParser(default_config_files=['scansmb.conf'])
    parser.add("-c", "--config", is_config_file=True, help="config file path", env_var="CONFIG")
    parser.add("-p", "--printer-host", required=True,
               help="printer hostname", env_var="PRINTER_HOST")
    parser.add("--smtp-user", required=True,
               help="smtp server username", env_var="SMTP_USERNAME")
    parser.add("--smtp-password", required=True,
               help="smtp server password", env_var="SMTP_PASSWORD")
    parser.add("--smtp-port", required=True,
               help="smtp server port", env_var="SMTP_PORT")
    parser.add("--smtp-host", required=True,
               help="smtp host", env_var="SMTP_HOST")
    parser.add("-f", "--mail-from",
               help="email from address", env_var="MAIL_FROM")
    parser.add("-t", "--mail-to", required=True,
               help="email recipient", env_var="MAIL_TO")

    options = parser.parse_args()

    if options.mail_from is None:
        options.mail_from = options.smtp_user

    ctx = smbc.Context(auth_fn=get_auth_data, client_ntlmv2_auth="no", client_use_spnego="no")
    mail_config = MailConfig(mail_from=options.mail_from, mail_to=options.mail_to, user=options.smtp_user,
                             password=options.smtp_password, host=options.smtp_host, port=options.smtp_port)

    logger.info("Started! Looking for scans...")
    logger.info(parser.format_values())

    scheduler = BlockingScheduler() 
    scheduler.add_job(loop, 'interval', minutes=1, args=[ctx, options.printer_host, mail_config])
    scheduler.start()


if __name__ == "__main__":
    main()
