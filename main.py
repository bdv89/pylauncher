#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lanceur avec fonction d'indexation - Point d'entrée principal
Optimisé pour une faible empreinte mémoire et CPU
"""

import sys
import os
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

# Imports PyQt
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings, QThreadPool, QTimer

# Import des modules internes
from core.config import Config
from core.indexer import Indexer
from core.watcher import FileWatcher
from ui.launcher import LauncherWindow, HotkeyManager
from storage.db import Database

# Configuration du logging minimaliste
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("launcher.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def main():
    """Point d'entrée principal de l'application"""
    # Paramètres pour limiter l'utilisation des ressources
    os.environ["PYTHONFAULTHANDLER"] = "0"  # Désactive le gestionnaire d'erreurs par défaut (économie de mémoire)
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"  # Désactive le scaling automatique
    
    # Initialisation de QApplication avec des options minimalistes
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # L'application reste en arrière-plan
    app.setApplicationName("QuickLaunch")
    
    # Limiter le ThreadPool pour contrôler l'utilisation CPU
    QThreadPool.globalInstance().setMaxThreadCount(2)
    
    # Chargement de la configuration
    config = Config()
    
    # Initialisation de la base de données
    db = Database(config.get("database_path", os.path.expanduser("~/.quicklaunch/index.db")))
    
    # Initialisation de l'indexeur dans un thread dédié
    executor = ThreadPoolExecutor(max_workers=1)
    indexer = Indexer(db, config)
    
    # Initialisation du surveillant de fichiers
    watcher = FileWatcher(indexer, config)
    
    # Lancement du processus d'indexation initial en arrière-plan si nécessaire
    if config.get("perform_initial_indexing", True):
        executor.submit(indexer.perform_initial_indexing)
    
    # Création et affichage de l'interface utilisateur
    launcher = LauncherWindow(db, indexer, config, watcher)
    
    # Configuration du raccourci global Ctrl+Space
    launcher.setup_global_hotkey()
    
    # Lancement de la boucle d'événements
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()