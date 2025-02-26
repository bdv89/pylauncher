#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module de configuration optimisé pour le lanceur
Utilise un fichier JSON simple pour la configuration
"""

import os
import json
import logging
import threading
from typing import Any, Dict, List, Optional, Union, Callable

logger = logging.getLogger(__name__)

class Config:
    """Gestion de la configuration avec mise en cache pour optimiser les performances"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialise la configuration
        
        Args:
            config_path: Chemin vers le fichier de configuration
        """
        # Chemin par défaut dans le répertoire utilisateur
        self.config_path = config_path or os.path.expanduser("~/.quicklaunch/config.json")
        self._config_cache = {}  # Cache pour éviter les accès disque répétés
        self._lock = threading.RLock()  # Verrou récursif pour thread-safety
        self._load_config()
    
    def _load_config(self) -> None:
        """Charge la configuration depuis le fichier, crée le fichier par défaut si nécessaire"""
        with self._lock:
            try:
                # Vérifier si le répertoire existe
                config_dir = os.path.dirname(self.config_path)
                if not os.path.exists(config_dir):
                    os.makedirs(config_dir)
                
                # Charger la configuration si le fichier existe
                if os.path.exists(self.config_path):
                    with open(self.config_path, 'r', encoding='utf-8') as f:
                        self._config_cache = json.load(f)
                else:
                    # Configuration par défaut
                    self._config_cache = {
                        "database_path": os.path.join(config_dir, "index.db"),
                        "indexed_locations": [
                            {"path": os.path.expanduser("~/Documents"), "include_subfolders": True},
                            {"path": os.path.expanduser("~/Desktop"), "include_subfolders": True},
                            {"path": "C:/Program Files", "include_subfolders": True}
                        ],
                        "excluded_paths": [
                            os.path.expanduser("~/Documents/temp"),
                            "C:/Windows/Temp"
                        ],
                        "excluded_extensions": [".tmp", ".bak", ".log"],
                        "update_interval": {
                            "local": 60,     # en minutes pour disques locaux
                            "network": 180   # en minutes pour disques réseau
                        },
                        "max_results": 50,
                        "perform_initial_indexing": True,
                        "hotkey": {
                            "modifier": "ctrl",
                            "key": "space"
                        },
                        "pinned_items": []
                    }
                    self.save()
            except Exception as e:
                logger.error(f"Erreur lors du chargement de la configuration: {e}")
                # En cas d'erreur, utiliser une configuration minimale par défaut
                self._config_cache = {"database_path": os.path.expanduser("~/.quicklaunch/index.db")}
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Récupère une valeur de configuration
        
        Args:
            key: Clé de configuration
            default: Valeur par défaut si la clé n'existe pas
            
        Returns:
            Valeur de configuration
        """
        with self._lock:
            return self._config_cache.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """
        Définit une valeur de configuration
        
        Args:
            key: Clé de configuration
            value: Valeur à définir
        """
        with self._lock:
            self._config_cache[key] = value
    
    def save(self) -> bool:
        """
        Sauvegarde la configuration dans le fichier de manière synchrone
        
        Returns:
            True si la sauvegarde a réussi, False sinon
        """
        with self._lock:
            try:
                config_dir = os.path.dirname(self.config_path)
                if not os.path.exists(config_dir):
                    os.makedirs(config_dir)
                
                # Sauvegarder d'abord dans un fichier temporaire
                temp_path = self.config_path + ".temp"
                
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(self._config_cache, f, indent=2)
                
                # Remplacer le fichier existant par le nouveau
                if os.path.exists(self.config_path):
                    os.replace(temp_path, self.config_path)
                else:
                    os.rename(temp_path, self.config_path)
                
                logger.info(f"Configuration sauvegardée avec succès dans: {self.config_path}")
                return True
            except Exception as e:
                logger.error(f"Erreur lors de la sauvegarde de la configuration: {e}")
                return False
    
    def save_async(self, callback: Optional[Callable[[bool], None]] = None) -> bool:
        """
        Sauvegarde la configuration de manière non bloquante
        
        Args:
            callback: Fonction à appeler une fois la sauvegarde terminée, prend un booléen success en argument
            
        Returns:
            True si la sauvegarde a été lancée, False sinon
        """
        # Créer une copie des données pour éviter les problèmes de concurrence
        with self._lock:
            config_copy = self._config_cache.copy()
        
        def _do_save():
            success = False
            try:
                config_dir = os.path.dirname(self.config_path)
                if not os.path.exists(config_dir):
                    os.makedirs(config_dir)
                    
                # Utiliser un fichier temporaire pour éviter la corruption
                temp_path = self.config_path + ".temp"
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(config_copy, f, indent=2)
                
                # Remplacer le fichier existant par le nouveau
                if os.path.exists(self.config_path):
                    os.replace(temp_path, self.config_path)
                else:
                    os.rename(temp_path, self.config_path)
                
                logger.info(f"Configuration sauvegardée avec succès dans: {self.config_path}")
                success = True
            except Exception as e:
                logger.error(f"Erreur lors de la sauvegarde asynchrone de la configuration: {e}")
                success = False
            
            # Appeler le callback si fourni
            if callback:
                # Utiliser QTimer pour s'assurer que le callback est exécuté dans le thread UI
                try:
                    from PyQt5.QtCore import QTimer
                    QTimer.singleShot(0, lambda: callback(success))
                except ImportError:
                    # Fallback si PyQt n'est pas importable dans ce contexte
                    if callback:
                        callback(success)
        
        # Exécuter dans un thread séparé
        t = threading.Thread(target=_do_save, daemon=True)
        t.start()
        return True
    
    def get_indexed_locations(self) -> List[Dict[str, Union[str, bool]]]:
        """
        Récupère la liste des emplacements à indexer
        
        Returns:
            Liste des emplacements
        """
        with self._lock:
            # Retourner une copie pour éviter les modifications externes
            return self.get("indexed_locations", []).copy()
    
    def add_indexed_location(self, path: str, include_subfolders: bool = True) -> None:
        """
        Ajoute un emplacement à indexer
        
        Args:
            path: Chemin à indexer
            include_subfolders: Inclure les sous-dossiers
        """
        with self._lock:
            locations = self.get_indexed_locations()
            if path not in [loc["path"] for loc in locations]:
                locations.append({"path": path, "include_subfolders": include_subfolders})
                self.set("indexed_locations", locations)
    
    def remove_indexed_location(self, path: str) -> None:
        """
        Supprime un emplacement à indexer
        
        Args:
            path: Chemin à supprimer
        """
        with self._lock:
            locations = self.get_indexed_locations()
            self.set("indexed_locations", [loc for loc in locations if loc["path"] != path])
    
    def add_pinned_item(self, path: str, name: str) -> None:
        """
        Ajoute un élément épinglé
        
        Args:
            path: Chemin complet de l'élément
            name: Nom à afficher
        """
        with self._lock:
            pinned_items = self.get("pinned_items", [])
            # Vérifier si l'élément est déjà épinglé
            if path not in [item["path"] for item in pinned_items]:
                pinned_items.append({"path": path, "name": name})
                self.set("pinned_items", pinned_items)
                self.save()
    
    def remove_pinned_item(self, path: str) -> None:
        """
        Supprime un élément épinglé
        
        Args:
            path: Chemin de l'élément à supprimer
        """
        with self._lock:
            pinned_items = self.get("pinned_items", [])
            self.set("pinned_items", [item for item in pinned_items if item["path"] != path])
            self.save()