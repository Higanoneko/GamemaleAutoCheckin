# -*- coding: utf-8 -*-
"""Logging helpers shared by all GameMale modules."""

import logging

logger = logging.getLogger("gamemale")


def _format(msg: str, account_name: str = "") -> str:
    return f"[{account_name}] {msg}" if account_name else msg


def log_info(msg: str, account_name: str = ""):
    logger.info(_format(msg, account_name))


def log_success(msg: str, account_name: str = ""):
    logger.info(_format(f"✅ {msg}", account_name))


def log_error(msg: str, account_name: str = ""):
    logger.error(_format(f"❌ {msg}", account_name))


def log_warning(msg: str, account_name: str = ""):
    logger.warning(_format(f"⚠️ {msg}", account_name))


def log_section(title: str, account_name: str = ""):
    logger.info(_format(f"\n{'='*20} {title} {'='*20}", account_name))
