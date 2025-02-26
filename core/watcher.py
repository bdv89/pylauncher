#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module optimisé pour surveiller les modifications de fichiers
Utilise watchdog pour les disques locaux et une approche légère pour les disques réseau
"""

import os
import time
import logging
import threading
from typing import Dict, List, Set, Optional, Any
from pathlib import Path

# Import conditionnel de watchdog pour réduire l'empreinte mémoire si non utilisé
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileSystemEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = object  # Type factice pour éviter les erreurs
    FileSystemEventHandler = object

logger = logging.getLogger(__name__)

class FileSystemChangeHandler(FileSystemEventHandler if WATCHDOG_AVAILABLE else object):
    """Gestionnaire d'événements pour les modifications du système de fichiers"""
    
    def __init__(self, indexer, excluded_paths: Set[str]):
        """
        Initialise le gestionnaire d'événements
        
        Args:
            indexer: Instance de l'indexeur
            excluded_paths: Ensemble des chemins exclus
        """
        super().__init__()
        self.indexer = indexer
        self.excluded_paths = excluded_paths
        self._throttle_map = {}  # Pour limiter les événements répétés
    
    def on_created(self, event: Any) -> None:
        """
        Gère les événements de création de fichier
        
        Args:
            event: Événement de création
        """
        if not self._should_process(event):
            return
        
        path = event.src_path
        if not self._is_throttled(path, 'created', 2.0):
            logger.debug(f"Fichier créé: {path}")
            self.indexer.add_file_to_index(path)
    
    def on_deleted(self, event: Any) -> None:
        """
        Gère les événements de suppression de fichier
        
        Args:
            event: Événement de suppression
        """
        if not self._should_process(event):
            return
        
        path = event.src_path
        if not self._is_throttled(path, 'deleted', 2.0):
            logger.debug(f"Fichier supprimé: {path}")
            if event.is_directory:
                self.indexer.remove_dir_from_index(path)
            else:
                self.indexer.remove_file_from_index(path)
    
    def on_modified(self, event: Any) -> None:
        """
        Gère les événements de modification de fichier
        
        Args:
            event: Événement de modification
        """
        # Ignorer les modifications de répertoire qui sont fréquentes mais peu intéressantes
        if event.is_directory:
            return
            
        if not self._should_process(event):
            return
        
        path = event.src_path
        # Les modifications sont très fréquentes, throttle plus agressif
        if not self._is_throttled(path, 'modified', 5.0):
            logger.debug(f"Fichier modifié: {path}")
            self.indexer.add_file_to_index(path)
    
    def on_moved(self, event: Any) -> None:
        """
        Gère les événements de déplacement de fichier
        
        Args:
            event: Événement de déplacement
        """
        if not self._should_process(event):
            return
        
        src_path = event.src_path
        dest_path = event.dest_path
        
        if not self._is_throttled(src_path, 'moved', 2.0):
            logger.debug(f"Fichier déplacé: {src_path} -> {dest_path}")
            # Supprimer l'ancien chemin et ajouter le nouveau
            if event.is_directory:
                self.indexer.remove_dir_from_index(src_path)
            else:
                self.indexer.remove_file_from_index(src_path)
            
            self.indexer.add_file_to_index(dest_path)
    
    def _should_process(self, event: Any) -> bool:
        """
        Vérifie si un événement doit être traité
        
        Args:
            event: Événement à vérifier
            
        Returns:
            True si l'événement doit être traité, False sinon
        """
        # Vérifier si le chemin est exclu
        path = event.src_path
        for excluded in self.excluded_paths:
            if path.startswith(excluded):
                return False
        
        # Ignorer les fichiers temporaires et cachés
        filename = os.path.basename(path)
        if filename.startswith('.') or filename.startswith('~$') or filename.endswith('.tmp'):
            return False
        
        return True
    
    def _is_throttled(self, path: str, event_type: str, timeout: float) -> bool:
        """
        Vérifie si un événement doit être limité pour éviter les rafales
        
        Args:
            path: Chemin du fichier
            event_type: Type d'événement
            timeout: Délai en secondes
            
        Returns:
            True si l'événement doit être ignoré (limité), False sinon
        """
        key = f"{path}:{event_type}"
        current_time = time.time()
        
        # Supprimer les entrées expirées pour éviter les fuites mémoire
        keys_to_remove = []
        for k, t in self._throttle_map.items():
            if current_time - t > timeout * 2:
                keys_to_remove.append(k)
        
        for k in keys_to_remove:
            del self._throttle_map[k]
        
        # Vérifier si l'événement est déjà traité
        if key in self._throttle_map:
            last_time = self._throttle_map[key]
            if current_time - last_time < timeout:
                return True
        
        # Mettre à jour le timestamp
        self._throttle_map[key] = current_time
        return False

class FileWatcher:
    """Gestionnaire de surveillance de fichiers optimisé"""
    
    def __init__(self, indexer, config):
        """
        Initialise le surveillant de fichiers
        
        Args:
            indexer: Instance de l'indexeur
            config: Instance de la configuration
        """
        self.indexer = indexer
        self.config = config
        
        # Initialiser les attributs
        self._observers = {}  # Dictionnaire des observateurs par chemin
        self._network_paths = set()  # Ensemble des chemins réseau
        self._excluded_paths = set(config.get("excluded_paths", []))
        
        # Verrou pour les opérations thread-safe
        self._lock = threading.Lock()
        
        # Pour le suivi des chemins réseau
        self._network_check_thread = None
        self._stop_event = threading.Event()
        
        # Vérifier si watchdog est disponible
        if not WATCHDOG_AVAILABLE:
            logger.warning("Le module watchdog n'est pas disponible, la surveillance en temps réel est limitée")
    
    def start(self) -> None:
        """Démarre la surveillance des emplacements indexés"""
        with self._lock:
            # Arrêter les observateurs existants
            self.stop()
            
            # Récupérer les emplacements indexés
            locations = self.config.get_indexed_locations()
            
            # Trier les emplacements entre locaux et réseau
            local_paths = []
            network_paths = set()
            
            for location in locations:
                path = location["path"]
                
                # Vérifier si c'est un chemin réseau
                if path.startswith("\\\\") or path.startswith("//"):
                    network_paths.add(path)
                else:
                    local_paths.append(path)
            
            # Démarrer la surveillance des chemins locaux avec watchdog
            if WATCHDOG_AVAILABLE:
                for path in local_paths:
                    self._start_observer(path)
            
            # Stocker les chemins réseau pour la surveillance périodique
            self._network_paths = network_paths
            
            # Démarrer le thread de surveillance réseau si nécessaire
            if network_paths and not self._network_check_thread:
                self._stop_event.clear()
                self._network_check_thread = threading.Thread(
                    target=self._check_network_paths_periodically,
                    daemon=True,
                    name="NetworkWatcherThread"
                )
                self._network_check_thread.start()
    
    def stop(self) -> None:
        """Arrête tous les observateurs"""
        with self._lock:
            # Arrêter les observateurs locaux
            for path, observer in self._observers.items():
                logger.info(f"Arrêt de la surveillance pour: {path}")
                observer.stop()
            
            # Attendre l'arrêt complet des observateurs
            for observer in self._observers.values():
                observer.join(timeout=1.0)
            
            # Vider le dictionnaire
            self._observers.clear()
            
            # Arrêter le thread de surveillance réseau
            if self._network_check_thread:
                self._stop_event.set()
                self._network_check_thread.join(timeout=2.0)
                self._network_check_thread = None
    
    def _start_observer(self, path: str) -> bool:
        """
        Démarre un observateur pour un chemin donné
        
        Args:
            path: Chemin à surveiller
            
        Returns:
            True si l'observateur a démarré avec succès, False sinon
        """
        if not os.path.isdir(path):
            logger.warning(f"Impossible de surveiller {path}: ce n'est pas un répertoire")
            return False
        
        try:
            # Créer l'gestionnaire d'événements
            event_handler = FileSystemChangeHandler(self.indexer, self._excluded_paths)
            
            # Créer et démarrer l'observateur
            observer = Observer()
            observer.schedule(event_handler, path, recursive=True)
            observer.start()
            
            # Stocker l'observateur
            self._observers[path] = observer
            logger.info(f"Surveillance démarrée pour: {path}")
            return True
        except Exception as e:
            logger.error(f"Erreur lors du démarrage de la surveillance pour {path}: {e}")
            return False
    
    def _check_network_paths_periodically(self) -> None:
        """Vérifie périodiquement les chemins réseau pour les modifications"""
        # Pour éviter une surconsommation de ressources, cette fonction
        # vérifie les chemins réseau à intervalle régulier plutôt qu'en temps réel
        
        # État précédemment connu des fichiers par chemin
        path_states = {}
        
        while not self._stop_event.is_set():
            for path in self._network_paths:
                try:
                    # Vérifier si le chemin est accessible
                    if not os.path.exists(path):
                        continue
                    
                    # Obtenir l'état actuel du répertoire (en limitant la profondeur)
                    current_state = self._get_shallow_dir_state(path)
                    
                    # Comparer avec l'état précédent
                    if path in path_states:
                        previous_state = path_states[path]
                        # Détecter les changements
                        self._detect_changes(path, previous_state, current_state)
                    
                    # Mettre à jour l'état
                    path_states[path] = current_state
                
                except Exception as e:
                    logger.warning(f"Erreur lors de la vérification du chemin réseau {path}: {e}")
            
            # Attendre avant la prochaine vérification
            # Utiliser wait avec timeout plutôt que sleep pour permettre un arrêt propre
            self._stop_event.wait(timeout=60.0)  # Vérifier toutes les minutes
    
    def _get_shallow_dir_state(self, path: str, max_depth: int = 2) -> Dict[str, float]:
        """
        Obtient l'état d'un répertoire de manière peu profonde (pour économiser les ressources)
        
        Args:
            path: Chemin du répertoire
            max_depth: Profondeur maximale de récursion
            
        Returns:
            Dictionnaire avec les chemins et les timestamps de modification
        """
        result = {}
        
        def scan_dir(current_path: str, depth: int = 0):
            if depth > max_depth:
                return
            
            try:
                with os.scandir(current_path) as entries:
                    for entry in entries:
                        # Ignorer les fichiers/dossiers cachés
                        if entry.name.startswith('.'):
                            continue
                        
                        try:
                            # Obtenir le temps de modification
                            mtime = entry.stat().st_mtime
                            result[entry.path] = mtime
                            
                            # Récursivement scanner les sous-dossiers
                            if entry.is_dir() and depth < max_depth:
                                scan_dir(entry.path, depth + 1)
                        except (PermissionError, FileNotFoundError):
                            # Ignorer les entrées inaccessibles
                            continue
            except (PermissionError, FileNotFoundError):
                # Ignorer les répertoires inaccessibles
                pass
        
        # Démarrer le scan
        scan_dir(path)
        return result
    
    def _detect_changes(self, root_path: str, prev_state: Dict[str, float], 
                       curr_state: Dict[str, float]) -> None:
        """
        Détecte les changements entre deux états du système de fichiers
        
        Args:
            root_path: Chemin racine
            prev_state: État précédent
            curr_state: État actuel
        """
        # Détecter les fichiers ajoutés ou modifiés
        for path, mtime in curr_state.items():
            if path not in prev_state:
                # Nouveau fichier
                self.indexer.add_file_to_index(path)
            elif abs(mtime - prev_state[path]) > 0.1:  # Seuil pour minimiser les faux positifs
                # Fichier modifié
                self.indexer.add_file_to_index(path)
        
        # Détecter les fichiers supprimés
        for path in prev_state:
            if path not in curr_state:
                # Fichier supprimé
                if os.path.isdir(path):
                    self.indexer.remove_dir_from_index(path)
                else:
                    self.indexer.remove_file_from_index(path)