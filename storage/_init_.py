#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Initialisation du package Storage
"""

import logging

logger = logging.getLogger(__name__)

# S'assurer que les modules sont chargés dans le bon ordre
from storage.db import Database
from storage.trie import Trie, TrieNode