#!/usr/bin/env python3
"""
Script to automatically send e-mails if a new file was found on the scanner's sdcard
"""

import re
from datetime import datetime
import logging
from apscheduler.schedulers.background import BlockingScheduler
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import configargparse
import smbc


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("scansmb")


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


def sendMail(document, mtime, mail_from, mail_to, smtp_user, smtp_password, smtp_host, smtp_port):
    msg = MIMEMultipart()

    msg["Subject"] = "New Scan!"
    msg["From"] = mail_from
    msg["To"] = ", ".join(mail_to)

    pdf = MIMEApplication(document, "pdf")
    pdf.add_header("Content-Disposition", "attachment",
                   filename="scan-{timestamp}.pdf".format(timestamp=mtime.strftime("%Y_%m_%d-%H%M%S")))
    msg.attach(pdf)
    msg.attach(MIMEText("""Hey!

I found a new scan on your printer. You can find it in the attachments :)

Regards
Scan-Bot
"""))

    s = smtplib.SMTP(smtp_host, smtp_port)
    s.starttls()
    s.login(smtp_user, smtp_password)
    s.send_message(msg)


def loop(ctx, options):
    logger.debug("starting loop")
    try:
        for file in ls(ctx, scan_path(options.printer_host), ent_type=smbc.FILE, recursive=True):
            logger.info("found file {}".format(file))
            mtime = datetime.fromtimestamp(ctx.stat(file)[8])
            dl = ctx.open(file).read()
            to = options.mail_to.split(",")
            sendMail(dl, mtime, options.mail_from, to, options.smtp_user,
                     options.smtp_password, options.smtp_host, options.smtp_port)
            ctx.unlink(file)  # Remove the scan after sending the email
    except Exception as e:
        logger.debug("poll failed")


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

    logger.info("Started! Looking for scans...")
    logger.info(parser.format_values())

    scheduler = BlockingScheduler() 
    scheduler.add_job(loop, 'interval', minutes=1, args=[ctx, options])
    scheduler.start()


if __name__ == "__main__":
    main()
