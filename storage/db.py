#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module de base de données optimisé pour l'indexation et la recherche rapide
Utilise SQLite avec des optimisations pour minimiser l'utilisation CPU/RAM
"""

import os
import sqlite3
import time
import logging
from typing import List, Dict, Any, Optional, Tuple, Generator
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class Database:
    """Gestion optimisée de la base de données SQLite pour l'indexation des fichiers"""
    
    def __init__(self, db_path: str):
        """
        Initialise la base de données
        
        Args:
            db_path: Chemin vers le fichier de base de données SQLite
        """
        self.db_path = db_path
        self._ensure_db_dir()
        self._init_db()
        
        # Statistiques d'utilisation pour optimisation
        self._stats = {
            "total_queries": 0,
            "cache_hits": 0,
            "slow_queries": 0
        }
        
        # Cache de recherche pour les requêtes fréquentes (LRU)
        self._search_cache = {}
        self._cache_max_size = 50  # Limiter la taille du cache pour économiser la RAM

    @contextmanager
    def _get_connection(self) -> Generator[Tuple[sqlite3.Connection, sqlite3.Cursor], None, None]:
        """
        Obtient une connexion à la base de données avec des optimisations
        
        Yields:
            Tuple de (connexion, curseur)
        """
        conn = sqlite3.connect(self.db_path)
        
        # Optimisations critiques pour SQLite
        conn.execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging pour meilleures performances
        conn.execute("PRAGMA synchronous = NORMAL")  # Balance entre sécurité et performances
        conn.execute("PRAGMA cache_size = 5000")  # Cache de 5000 pages (~20MB)
        conn.execute("PRAGMA temp_store = MEMORY")  # Stockage temporaire en mémoire
        conn.execute("PRAGMA mmap_size = 30000000")  # Utilisation de mmap pour les fichiers fréquemment accédés
        
        conn.row_factory = sqlite3.Row  # Pour accès par nom de colonne
        cursor = conn.cursor()
        
        try:
            yield conn, cursor
        finally:
            conn.commit()
            cursor.close()
            conn.close()

    def _ensure_db_dir(self) -> None:
        """Assure que le répertoire de la base de données existe"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)

    def _init_db(self) -> None:
        """Initialise le schéma de la base de données si nécessaire"""
        with self._get_connection() as (conn, cursor):
            # Table principale des fichiers indexés
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                extension TEXT,
                is_dir INTEGER NOT NULL,
                parent_path TEXT,
                date_indexed INTEGER NOT NULL,
                date_modified INTEGER,
                size INTEGER
            )
            """)
            
            # Index pour des recherches rapides
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_name ON files(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_path ON files(path)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_parent ON files(parent_path)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_extension ON files(extension)")
            
            # Table séparée pour les chemins indexés (pour suivi des mises à jour)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS indexed_paths (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL UNIQUE,
                last_indexed INTEGER NOT NULL,
                is_network INTEGER NOT NULL
            )
            """)

    def add_file(self, path: str, name: str, is_dir: bool, parent_path: str,
                extension: Optional[str] = None, date_modified: Optional[int] = None,
                size: Optional[int] = None) -> bool:
        """
        Ajoute ou met à jour un fichier dans l'index
        
        Args:
            path: Chemin complet du fichier
            name: Nom du fichier
            is_dir: True si c'est un dossier, False sinon
            parent_path: Chemin du dossier parent
            extension: Extension du fichier (sans le point)
            date_modified: Date de modification en timestamp Unix
            size: Taille du fichier en octets
            
        Returns:
            True si l'opération a réussi, False sinon
        """
        try:
            with self._get_connection() as (conn, cursor):
                now = int(time.time())
                
                # Vérifier si le fichier existe déjà et le mettre à jour si nécessaire
                cursor.execute(
                    "SELECT id FROM files WHERE path = ?", (path,)
                )
                existing = cursor.fetchone()
                
                if existing:
                    cursor.execute(
                        """
                        UPDATE files
                        SET name = ?, extension = ?, is_dir = ?, parent_path = ?,
                            date_indexed = ?, date_modified = ?, size = ?
                        WHERE id = ?
                        """,
                        (name, extension, 1 if is_dir else 0, parent_path, 
                         now, date_modified, size, existing['id'])
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO files
                        (path, name, extension, is_dir, parent_path, date_indexed, date_modified, size)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (path, name, extension, 1 if is_dir else 0, parent_path, 
                         now, date_modified, size)
                    )
                
                # Invalider le cache de recherche
                self._search_cache.clear()
                return True
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout du fichier {path}: {e}")
            return False

    def remove_file(self, path: str) -> bool:
        """
        Supprime un fichier de l'index
        
        Args:
            path: Chemin complet du fichier
            
        Returns:
            True si l'opération a réussi, False sinon
        """
        try:
            with self._get_connection() as (conn, cursor):
                cursor.execute("DELETE FROM files WHERE path = ?", (path,))
                # Invalider le cache de recherche
                self._search_cache.clear()
                return True
        except Exception as e:
            logger.error(f"Erreur lors de la suppression du fichier {path}: {e}")
            return False

    def remove_files_in_dir(self, dir_path: str) -> bool:
        """
        Supprime tous les fichiers dans un répertoire de l'index
        
        Args:
            dir_path: Chemin du répertoire
            
        Returns:
            True si l'opération a réussi, False sinon
        """
        try:
            with self._get_connection() as (conn, cursor):
                # Ajouter le caractère '%' pour la correspondance avec LIKE
                pattern = f"{dir_path}%"
                cursor.execute("DELETE FROM files WHERE path LIKE ?", (pattern,))
                # Invalider le cache de recherche
                self._search_cache.clear()
                return True
        except Exception as e:
            logger.error(f"Erreur lors de la suppression des fichiers dans {dir_path}: {e}")
            return False

    def search(self, query: str, max_results: int = 50, search_dirs: bool = True,
              search_files: bool = True, extensions: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Recherche dans l'index avec gestion de cache
        
        Args:
            query: Termes de recherche
            max_results: Nombre maximum de résultats
            search_dirs: Rechercher dans les dossiers
            search_files: Rechercher dans les fichiers
            extensions: Liste d'extensions à filtrer
            
        Returns:
            Liste de résultats correspondants
        """
        # Incrémenter les stats de requêtes
        self._stats["total_queries"] += 1
        
        # Clé de cache (tuple immuable)
        cache_key = (query, max_results, search_dirs, search_files, 
                     tuple(extensions) if extensions else None)
        
        # Vérifier si la requête est dans le cache
        if cache_key in self._search_cache:
            self._stats["cache_hits"] += 1
            return self._search_cache[cache_key]
        
        # Construire la requête SQL optimisée
        start_time = time.time()
        try:
            with self._get_connection() as (conn, cursor):
                # Conditions de base
                conditions = []
                params = []
                
                # Filtre sur le type (dossier/fichier)
                type_conditions = []
                if search_dirs:
                    type_conditions.append("is_dir = 1")
                if search_files:
                    type_conditions.append("is_dir = 0")
                
                if type_conditions:
                    conditions.append(f"({' OR '.join(type_conditions)})")
                
                # Recherche par nom avec LIKE optimisé
                if query:
                    # Diviser la requête en mots pour une recherche plus flexible
                    search_terms = query.strip().lower().split()
                    for term in search_terms:
                        term_pattern = f"%{term}%"
                        conditions.append("LOWER(name) LIKE ?")
                        params.append(term_pattern)
                
                # Filtre par extension
                if extensions:
                    ext_placeholders = ','.join(['?' for _ in extensions])
                    conditions.append(f"extension IN ({ext_placeholders})")
                    params.extend(extensions)
                
                # Construire la clause WHERE finale
                where_clause = " AND ".join(conditions) if conditions else "1=1"
                
                # Exécuter la requête avec LIMIT pour contrôler l'utilisation mémoire
                sql = f"""
                SELECT path, name, extension, is_dir, parent_path, date_modified, size
                FROM files
                WHERE {where_clause}
                ORDER BY 
                    CASE WHEN LOWER(name) LIKE ? THEN 0 ELSE 1 END,  -- Correspondance exacte en premier
                    is_dir DESC,                                     -- Dossiers avant fichiers
                    name COLLATE NOCASE                              -- Tri alphabétique insensible à la casse
                LIMIT ?
                """
                
                # Ajouter le paramètre pour la correspondance exacte en début de nom
                exact_pattern = f"{query.lower()}%"
                params.append(exact_pattern)
                params.append(max_results)
                
                cursor.execute(sql, params)
                
                # Convertir en dictionnaires pour le cache
                results = [dict(row) for row in cursor.fetchall()]
                
                # Stocker dans le cache LRU (supprimer l'élément le plus ancien si nécessaire)
                if len(self._search_cache) >= self._cache_max_size:
                    self._search_cache.pop(next(iter(self._search_cache)))
                self._search_cache[cache_key] = results
                
                # Analyser les performances
                query_time = time.time() - start_time
                if query_time > 0.1:  # Plus de 100ms est considéré comme lent
                    self._stats["slow_queries"] += 1
                    logger.debug(f"Requête lente ({query_time:.3f}s): {query}")
                
                return results
                
        except Exception as e:
            logger.error(f"Erreur lors de la recherche pour '{query}': {e}")
            return []

    def get_files_in_dir(self, dir_path: str, max_results: int = 200) -> List[Dict[str, Any]]:
        """
        Récupère tous les fichiers dans un répertoire
        
        Args:
            dir_path: Chemin du répertoire
            max_results: Nombre maximum de résultats
            
        Returns:
            Liste de fichiers dans le répertoire
        """
        try:
            with self._get_connection() as (conn, cursor):
                cursor.execute(
                    """
                    SELECT path, name, extension, is_dir, parent_path, date_modified, size
                    FROM files
                    WHERE parent_path = ?
                    ORDER BY is_dir DESC, name COLLATE NOCASE
                    LIMIT ?
                    """,
                    (dir_path, max_results)
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des fichiers dans {dir_path}: {e}")
            return []

    def update_indexed_path(self, path: str, is_network: bool) -> None:
        """
        Met à jour le timestamp d'indexation pour un chemin
        
        Args:
            path: Chemin indexé
            is_network: True si c'est un chemin réseau
        """
        try:
            with self._get_connection() as (conn, cursor):
                now = int(time.time())
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO indexed_paths (path, last_indexed, is_network)
                    VALUES (?, ?, ?)
                    """,
                    (path, now, 1 if is_network else 0)
                )
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du chemin indexé {path}: {e}")

    def get_outdated_paths(self, local_interval: int, network_interval: int) -> List[Dict[str, Any]]:
        """
        Récupère les chemins qui nécessitent une mise à jour de l'index
        
        Args:
            local_interval: Intervalle de mise à jour pour les chemins locaux (en minutes)
            network_interval: Intervalle de mise à jour pour les chemins réseau (en minutes)
            
        Returns:
            Liste des chemins à mettre à jour
        """
        try:
            with self._get_connection() as (conn, cursor):
                now = int(time.time())
                local_threshold = now - (local_interval * 60)
                network_threshold = now - (network_interval * 60)
                
                cursor.execute(
                    """
                    SELECT path, last_indexed, is_network
                    FROM indexed_paths
                    WHERE (is_network = 0 AND last_indexed < ?)
                       OR (is_network = 1 AND last_indexed < ?)
                    """,
                    (local_threshold, network_threshold)
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des chemins obsolètes: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """
        Récupère des statistiques de la base de données
        
        Returns:
            Dictionnaire de statistiques
        """
        stats = self._stats.copy()
        
        try:
            with self._get_connection() as (conn, cursor):
                # Nombre total de fichiers indexés
                cursor.execute("SELECT COUNT(*) FROM files")
                stats["total_files"] = cursor.fetchone()[0]
                
                # Nombre de dossiers
                cursor.execute("SELECT COUNT(*) FROM files WHERE is_dir = 1")
                stats["total_dirs"] = cursor.fetchone()[0]
                
                # Nombre de fichiers
                stats["total_real_files"] = stats["total_files"] - stats["total_dirs"]
                
                # Taille moyenne des fichiers
                cursor.execute("SELECT AVG(size) FROM files WHERE is_dir = 0 AND size IS NOT NULL")
                stats["avg_file_size"] = cursor.fetchone()[0] or 0
                
                # Date de dernière indexation
                cursor.execute("SELECT MAX(date_indexed) FROM files")
                stats["last_indexed"] = cursor.fetchone()[0] or 0
                
                # Taux de hit du cache
                if stats["total_queries"] > 0:
                    stats["cache_hit_rate"] = stats["cache_hits"] / stats["total_queries"]
                else:
                    stats["cache_hit_rate"] = 0
                
                return stats
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des statistiques: {e}")
            return stats