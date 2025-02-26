#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Moteur d'indexation optimisé pour une consommation minimale de ressources
"""

import os
import time
import logging
import threading
import queue
from typing import List, Dict, Any, Set, Optional, Tuple
from datetime import datetime

# Imports pour la gestion du réseau sous Windows
import win32wnet
import win32netcon
import win32api

logger = logging.getLogger(__name__)

class Indexer:
    """Moteur d'indexation de fichiers optimisé pour une faible empreinte mémoire"""
    
    def __init__(self, db, config):
        """
        Initialise l'indexeur
        
        Args:
            db: Instance de la base de données
            config: Instance de la configuration
        """
        self.db = db
        self.config = config
        
        # Files d'attente pour limiter l'utilisation de la mémoire
        self._indexing_queue = queue.Queue()
        self._update_queue = queue.Queue()
        
        # Contrôle des threads
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
        # Cache des chemins exclus pour optimiser les vérifications
        self._excluded_paths_cache = set(self.config.get("excluded_paths", []))
        self._excluded_extensions_cache = set(self.config.get("excluded_extensions", []))
        
        # Variables pour les stats et le contrôle de performance
        self._files_indexed = 0
        self._last_update_time = time.time()
        self._indexing_in_progress = False
        
        # Démarrer le thread d'indexation en arrière-plan
        self._start_background_workers()
    
    def _start_background_workers(self) -> None:
        """Démarre les threads d'indexation en arrière-plan"""
        # Thread de traitement de la file d'indexation
        self._indexing_thread = threading.Thread(
            target=self._process_indexing_queue,
            daemon=True,
            name="IndexingThread"
        )
        self._indexing_thread.start()
        
        # Thread de traitement des mises à jour
        self._update_thread = threading.Thread(
            target=self._process_update_queue,
            daemon=True,
            name="UpdateThread"
        )
        self._update_thread.start()
    
    def _process_indexing_queue(self) -> None:
        """Traite la file d'indexation en arrière-plan"""
        while not self._stop_event.is_set():
            try:
                # Récupération avec timeout pour permettre d'arrêter proprement le thread
                path_info = self._indexing_queue.get(timeout=1.0)
                if path_info:
                    path, include_subfolders = path_info
                    self._index_location(path, include_subfolders)
                self._indexing_queue.task_done()
            except queue.Empty:
                # File vide, on continue la boucle
                continue
            except Exception as e:
                logger.error(f"Erreur dans le thread d'indexation: {e}")
                time.sleep(0.5)  # Pause brève pour éviter de surcharger en cas d'erreur
    
    def _process_update_queue(self) -> None:
        """Traite la file des mises à jour en arrière-plan"""
        while not self._stop_event.is_set():
            try:
                # Prioriser les petites mises à jour rapides
                op, path = self._update_queue.get(timeout=1.0)
                
                if op == 'add':
                    self._add_single_file(path)
                elif op == 'remove':
                    self.db.remove_file(path)
                elif op == 'remove_dir':
                    self.db.remove_files_in_dir(path)
                
                self._update_queue.task_done()
            except queue.Empty:
                # File vide, on continue la boucle
                continue
            except Exception as e:
                logger.error(f"Erreur dans le thread de mise à jour: {e}")
                time.sleep(0.5)
    
    def perform_initial_indexing(self) -> None:
        """Effectue l'indexation initiale de tous les emplacements configurés"""
        with self._lock:
            self._indexing_in_progress = True
            self._files_indexed = 0
            
            try:
                locations = self.config.get_indexed_locations()
                logger.info(f"Démarrage de l'indexation initiale: {len(locations)} emplacements")
                
                # Mettre à jour les caches des exclusions
                self._excluded_paths_cache = set(self.config.get("excluded_paths", []))
                self._excluded_extensions_cache = set(self.config.get("excluded_extensions", []))
                
                # Soumettre les emplacements à la file d'indexation
                for location in locations:
                    path = location["path"]
                    include_subfolders = location.get("include_subfolders", True)
                    
                    # Vérifier si le chemin est accessible
                    if self._is_path_accessible(path):
                        self._indexing_queue.put((path, include_subfolders))
                        logger.info(f"Ajout de {path} à la file d'indexation")
                    else:
                        logger.warning(f"Chemin inaccessible: {path}")
                
                # Attendre que l'indexation soit terminée
                self._indexing_queue.join()
                logger.info(f"Indexation initiale terminée. {self._files_indexed} fichiers indexés.")
            
            except Exception as e:
                logger.error(f"Erreur lors de l'indexation initiale: {e}")
            
            finally:
                self._indexing_in_progress = False
    
    def schedule_incremental_update(self) -> None:
        """Planifie une mise à jour incrémentielle des emplacements indexés"""
        if self._indexing_in_progress:
            return  # Ne pas démarrer de mise à jour si une indexation est en cours
        
        # Obtenir les intervalles de mise à jour
        update_intervals = self.config.get("update_interval", {"local": 60, "network": 180})
        local_interval = update_intervals["local"]
        network_interval = update_intervals["network"]
        
        # Récupérer les chemins qui nécessitent une mise à jour
        outdated_paths = self.db.get_outdated_paths(local_interval, network_interval)
        
        # Planifier les mises à jour
        for path_info in outdated_paths:
            path = path_info["path"]
            if self._is_path_accessible(path):
                self._indexing_queue.put((path, True))  # True pour inclure les sous-dossiers
                logger.debug(f"Planification de mise à jour: {path}")
    
    def _index_location(self, root_path: str, include_subfolders: bool) -> None:
        """
        Indexe un emplacement en minimisant l'utilisation des ressources
        
        Args:
            root_path: Chemin racine à indexer
            include_subfolders: Inclure les sous-dossiers
        """
        # Vérifier si le chemin est un partage réseau
        is_network = self._is_network_path(root_path)
        
        try:
            # Traiter le dossier racine
            if os.path.isdir(root_path):
                # Indexer le dossier lui-même
                self._add_directory(root_path, os.path.dirname(root_path))
                
                # Obtenir la liste des fichiers et dossiers
                items = []
                try:
                    # Limiter le nombre d'éléments traités à la fois pour économiser la mémoire
                    items = os.listdir(root_path)
                except PermissionError:
                    # Log plus discret pour les dossiers systèmes courants auxquels l'accès est souvent refusé
                    if any(folder in root_path.lower() for folder in [
                        "ma musique", "mes images", "mes vidéos", "appdata", 
                        "programdata", "windows", "system32"
                    ]):
                        logger.debug(f"Accès refusé (dossier système): {root_path}")
                    else:
                        logger.warning(f"Accès refusé: {root_path}")
                    return
                except Exception as e:
                    logger.warning(f"Erreur lors de l'accès à {root_path}: {e}")
                    return
                
                # Traiter par lots pour un meilleur contrôle des ressources
                batch_size = 100  # Ajuster selon les besoins
                for i in range(0, len(items), batch_size):
                    if self._stop_event.is_set():
                        return
                    
                    batch = items[i:i+batch_size]
                    self._process_directory_batch(root_path, batch, include_subfolders)
                    
                    # Petite pause pour libérer le CPU
                    time.sleep(0.01)
                
                # Mettre à jour le statut d'indexation
                self.db.update_indexed_path(root_path, is_network)
                
            elif os.path.isfile(root_path):
                # Si c'est un fichier unique, l'ajouter directement
                self._add_single_file(root_path)
        
        except Exception as e:
            logger.error(f"Erreur lors de l'indexation de {root_path}: {e}")
    
    def _process_directory_batch(self, parent_path: str, items: List[str], 
                               include_subfolders: bool) -> None:
        """
        Traite un lot d'éléments dans un répertoire
        
        Args:
            parent_path: Chemin du répertoire parent
            items: Liste des noms d'éléments
            include_subfolders: Inclure les sous-dossiers
        """
        # Préparer les chemins complets
        full_paths = [os.path.join(parent_path, item) for item in items]
        
        # Traiter les dossiers d'abord si on inclut les sous-dossiers
        if include_subfolders:
            for i, path in enumerate(full_paths):
                if self._stop_event.is_set():
                    return
                
                try:
                    if os.path.isdir(path) and not self._is_excluded_path(path):
                        # Ajouter le dossier à l'index
                        self._add_directory(path, parent_path)
                        
                        # Récursivement indexer le sous-dossier (via la file d'attente)
                        self._indexing_queue.put((path, include_subfolders))
                except (PermissionError, FileNotFoundError):
                    # Ignorer les dossiers inaccessibles
                    continue
        
        # Traiter les fichiers
        for i, path in enumerate(full_paths):
            if self._stop_event.is_set():
                return
            
            try:
                if os.path.isfile(path) and not self._is_excluded_path(path):
                    self._add_file(path, parent_path)
            except (PermissionError, FileNotFoundError):
                # Ignorer les fichiers inaccessibles
                continue
            
            # Mettre à jour les stats périodiquement
            if self._files_indexed % 1000 == 0:
                current_time = time.time()
                elapsed = current_time - self._last_update_time
                logger.info(f"Indexation en cours: {self._files_indexed} fichiers "
                           f"({self._files_indexed / max(1, elapsed):.1f} fichiers/s)")
                self._last_update_time = current_time
    
    def _add_directory(self, path: str, parent_path: str) -> None:
        """
        Ajoute un dossier à l'index
        
        Args:
            path: Chemin complet du dossier
            parent_path: Chemin du dossier parent
        """
        try:
            name = os.path.basename(path)
            self.db.add_file(
                path=path,
                name=name,
                is_dir=True,
                parent_path=parent_path,
                extension=None,
                date_modified=int(os.path.getmtime(path)),
                size=None  # Les dossiers n'ont pas de taille
            )
            self._files_indexed += 1
        except (PermissionError, FileNotFoundError):
            # Ignorer les dossiers inaccessibles
            pass
    
    def _add_file(self, path: str, parent_path: str) -> None:
        """
        Ajoute un fichier à l'index
        
        Args:
            path: Chemin complet du fichier
            parent_path: Chemin du dossier parent
        """
        try:
            name = os.path.basename(path)
            _, extension = os.path.splitext(name)
            
            # Ignorer si l'extension est exclue
            if extension and extension.lower() in self._excluded_extensions_cache:
                return
            
            # Éliminer le point de l'extension
            extension = extension[1:] if extension else ""
            
            self.db.add_file(
                path=path,
                name=name,
                is_dir=False,
                parent_path=parent_path,
                extension=extension.lower(),
                date_modified=int(os.path.getmtime(path)),
                size=os.path.getsize(path)
            )
            self._files_indexed += 1
        except (PermissionError, FileNotFoundError):
            # Ignorer les fichiers inaccessibles
            pass
    
    def _add_single_file(self, path: str) -> None:
        """
        Ajoute un seul fichier à l'index (utilisé pour les mises à jour)
        
        Args:
            path: Chemin complet du fichier
        """
        if not os.path.exists(path) or self._is_excluded_path(path):
            return
        
        parent_path = os.path.dirname(path)
        
        if os.path.isdir(path):
            self._add_directory(path, parent_path)
        else:
            self._add_file(path, parent_path)
    
    def _is_excluded_path(self, path: str) -> bool:
        """
        Vérifie si un chemin est exclu de l'indexation
        
        Args:
            path: Chemin à vérifier
            
        Returns:
            True si le chemin est exclu, False sinon
        """
        # Vérifier les chemins exclus
        for excluded in self._excluded_paths_cache:
            if path.startswith(excluded):
                return True
        
        # Vérifier les fichiers cachés (commençant par un point)
        name = os.path.basename(path)
        if name.startswith("."):
            return True
        
        return False
    
    def _is_network_path(self, path: str) -> bool:
        """
        Vérifie si un chemin est un partage réseau
        
        Args:
            path: Chemin à vérifier
            
        Returns:
            True si c'est un chemin réseau, False sinon
        """
        return path.startswith("\\\\") or path.startswith("//")
    
    def _is_path_accessible(self, path: str) -> bool:
        """
        Vérifie si un chemin est accessible
        
        Args:
            path: Chemin à vérifier
            
        Returns:
            True si le chemin est accessible, False sinon
        """
        try:
            # Pour les chemins réseau, essayer de les connecter d'abord
            if self._is_network_path(path):
                # Essayer de lister les fichiers pour vérifier l'accès
                os.listdir(path)
            else:
                # Pour les chemins locaux, vérifier simplement l'existence
                return os.path.exists(path)
            return True
        except Exception:
            return False
    
    def add_file_to_index(self, path: str) -> None:
        """
        Ajoute un fichier à l'index (API publique)
        
        Args:
            path: Chemin du fichier à ajouter
        """
        if not self._is_excluded_path(path):
            self._update_queue.put(('add', path))
    
    def remove_file_from_index(self, path: str) -> None:
        """
        Supprime un fichier de l'index (API publique)
        
        Args:
            path: Chemin du fichier à supprimer
        """
        self._update_queue.put(('remove', path))
    
    def remove_dir_from_index(self, path: str) -> None:
        """
        Supprime un répertoire et son contenu de l'index (API publique)
        
        Args:
            path: Chemin du répertoire à supprimer
        """
        self._update_queue.put(('remove_dir', path))
    
    def stop(self) -> None:
        """Arrête les threads d'indexation"""
        self._stop_event.set()
        
        # Vider les files pour permettre aux threads de se terminer
        while not self._indexing_queue.empty():
            try:
                self._indexing_queue.get_nowait()
                self._indexing_queue.task_done()
            except queue.Empty:
                break
        
        while not self._update_queue.empty():
            try:
                self._update_queue.get_nowait()
                self._update_queue.task_done()
            except queue.Empty:
                break