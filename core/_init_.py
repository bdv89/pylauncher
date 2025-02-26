#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Initialisation du package Core
"""

import logging

logger = logging.getLogger(__name__)

# S'assurer que les modules sont chargés dans le bon ordre
from core.config import Config
from core.indexer import Indexer
from core.watcher import FileWatcher, FileSystemChangeHandler