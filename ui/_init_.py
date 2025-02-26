#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Initialisation du package UI
"""

import os
import logging

logger = logging.getLogger(__name__)

# S'assurer que les modules sont chargés dans le bon ordre
from ui.launcher import LauncherWindow
from ui.settings import SettingsDialog