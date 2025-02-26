#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Structure de données Trie optimisée pour une recherche ultra-rapide
Permet de suggérer des résultats pendant la frappe avec un minimum de RAM
"""

import re
import gc
import time
import logging
from typing import Dict, List, Set, Optional, Any, Tuple
from collections import deque

logger = logging.getLogger(__name__)

class TrieNode:
    """Nœud d'un arbre Trie"""
    
    __slots__ = ('children', 'is_end', 'file_ids')
    
    def __init__(self):
        """Initialise un nœud vide"""
        self.children = {}  # Dictionnaire des enfants: {caractère: nœud}
        self.is_end = False  # Indique si le nœud termine un mot
        self.file_ids = set()  # Ensemble des IDs de fichiers associés à ce nœud

class Trie:
    """Structure de données Trie optimisée pour la recherche rapide"""
    
    def __init__(self, case_sensitive: bool = False):
        """
        Initialise un Trie vide
        
        Args:
            case_sensitive: Si True, les recherches sont sensibles à la casse
        """
        self.root = TrieNode()
        self.case_sensitive = case_sensitive
        self._size = 0  # Nombre de mots dans le Trie
        self._memory_optimized = False
        
        # Cache pour les n-grammes (pour la recherche floue)
        self._ngram_cache = {}
        
        # Statistiques
        self._stats = {
            "inserts": 0,
            "removes": 0,
            "searches": 0,
            "search_time": 0.0
        }
    
    def _process_word(self, word: str) -> str:
        """
        Prétraite un mot avant insertion ou recherche
        
        Args:
            word: Mot à prétraiter
            
        Returns:
            Mot prétraité
        """
        # Supprimer les caractères spéciaux et normaliser
        normalized = re.sub(r'[^\w\s]', '', word)
        
        # Appliquer la sensibilité à la casse
        if not self.case_sensitive:
            normalized = normalized.lower()
        
        return normalized
    
    def insert(self, word: str, file_id: int) -> None:
        """
        Insère un mot dans le Trie
        
        Args:
            word: Mot à insérer
            file_id: ID du fichier associé
        """
        processed = self._process_word(word)
        if not processed:
            return
        
        # Invalider le cache des n-grammes
        self._ngram_cache.clear()
        
        # Insérer le mot
        node = self.root
        for char in processed:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
            node.file_ids.add(file_id)
        
        # Marquer la fin du mot
        if not node.is_end:
            node.is_end = True
            self._size += 1
        
        self._stats["inserts"] += 1
    
    def remove(self, word: str, file_id: int) -> bool:
        """
        Supprime un mot du Trie pour un fichier donné
        
        Args:
            word: Mot à supprimer
            file_id: ID du fichier associé
            
        Returns:
            True si le mot a été supprimé, False sinon
        """
        processed = self._process_word(word)
        if not processed:
            return False
        
        # Invalider le cache des n-grammes
        self._ngram_cache.clear()
        
        # Trouver le nœud du mot
        node = self._find_node(processed)
        if not node or not node.is_end:
            return False
        
        # Supprimer l'ID du fichier
        if file_id in node.file_ids:
            node.file_ids.remove(file_id)
        
        # Si plus aucun fichier associé, supprimer le nœud
        if not node.file_ids:
            # Utiliser un algorithme de suppression efficace
            self._lazy_delete(processed)
            self._size -= 1
        
        self._stats["removes"] += 1
        return True
    
    def _lazy_delete(self, word: str) -> None:
        """
        Suppression paresseuse: marque juste le nœud comme non terminal
        
        Args:
            word: Mot à supprimer
        """
        node = self._find_node(word)
        if node:
            node.is_end = False
    
    def _find_node(self, word: str) -> Optional[TrieNode]:
        """
        Trouve le nœud correspondant à un mot
        
        Args:
            word: Mot à rechercher
            
        Returns:
            Nœud correspondant ou None
        """
        node = self.root
        for char in word:
            if char not in node.children:
                return None
            node = node.children[char]
        return node
    
    def search(self, prefix: str, max_results: int = 50, 
              fuzzy: bool = False, fuzzy_threshold: int = 1) -> List[Tuple[int, int]]:
        """
        Recherche les fichiers contenant un préfixe
        
        Args:
            prefix: Préfixe à rechercher
            max_results: Nombre maximum de résultats
            fuzzy: Utiliser une recherche approximative
            fuzzy_threshold: Seuil de distance maximale pour la recherche floue
            
        Returns:
            Liste de tuples (file_id, score) triés par score décroissant
        """
        start_time = time.time()
        self._stats["searches"] += 1
        
        processed = self._process_word(prefix)
        if not processed:
            return []
        
        # Dictionnaire des résultats {file_id: score}
        results = {}
        
        # Recherche exacte
        exact_node = self._find_node(processed)
        if exact_node:
            self._collect_files_from_node(exact_node, results, 1.0)
        
        # Recherche de préfixe (complétion)
        if exact_node and len(processed) >= 2:
            self._collect_prefix_matches(exact_node, results, 0.8)
        
        # Recherche approximative si activée et pas assez de résultats
        if fuzzy and len(results) < max_results:
            self._fuzzy_search(processed, results, fuzzy_threshold, 0.6)
        
        # Convertir en liste de tuples et trier par score
        result_tuples = [(file_id, score) for file_id, score in results.items()]
        result_tuples.sort(key=lambda x: x[1], reverse=True)
        
        # Limiter le nombre de résultats
        result_tuples = result_tuples[:max_results]
        
        # Mettre à jour les statistiques
        self._stats["search_time"] += time.time() - start_time
        
        return result_tuples
    
    def _collect_files_from_node(self, node: TrieNode, results: Dict[int, float], score: float) -> None:
        """
        Collecte les fichiers associés à un nœud et ses descendants
        
        Args:
            node: Nœud de départ
            results: Dictionnaire des résultats à mettre à jour
            score: Score de pertinence
        """
        # Ajouter les fichiers du nœud actuel
        for file_id in node.file_ids:
            results[file_id] = max(results.get(file_id, 0), score)
        
        # Si le nombre de résultats est déjà très grand, ne pas descendre plus loin
        if len(results) > 1000:
            return
        
        # Explorer les descendants (mais pas trop profondément pour économiser la mémoire)
        stack = [(child, 1) for child in node.children.values()]
        max_depth = 3  # Limite de profondeur
        
        while stack:
            current, depth = stack.pop()
            
            # Ajouter les fichiers du nœud actuel avec un score réduit
            discount = 1.0 - (depth * 0.1)  # Réduction du score avec la profondeur
            for file_id in current.file_ids:
                results[file_id] = max(results.get(file_id, 0), score * discount)
            
            # Explorer les enfants jusqu'à la profondeur maximale
            if depth < max_depth:
                for child in current.children.values():
                    stack.append((child, depth + 1))
    
    def _collect_prefix_matches(self, node: TrieNode, results: Dict[int, float], base_score: float) -> None:
        """
        Collecte les fichiers qui complètent le préfixe
        
        Args:
            node: Nœud de départ
            results: Dictionnaire des résultats à mettre à jour
            base_score: Score de base
        """
        # Utiliser une file pour un parcours en largeur (BFS)
        queue = deque([(node, 1)])
        max_depth = 5  # Limiter la profondeur
        
        while queue:
            current, depth = queue.popleft()
            
            # Si nœud terminal, ajouter les fichiers avec un score qui diminue avec la profondeur
            if current.is_end:
                score_factor = base_score * (1.0 - (depth * 0.1))
                for file_id in current.file_ids:
                    results[file_id] = max(results.get(file_id, 0), score_factor)
            
            # Arrêter si on a atteint la profondeur maximale
            if depth >= max_depth:
                continue
            
            # Explorer les enfants
            for child in current.children.values():
                queue.append((child, depth + 1))
    
    def _fuzzy_search(self, query: str, results: Dict[int, float], threshold: int, base_score: float) -> None:
        """
        Effectue une recherche approximative
        
        Args:
            query: Requête
            results: Dictionnaire des résultats à mettre à jour
            threshold: Seuil de distance maximale
            base_score: Score de base
        """
        # Si la requête est trop courte, ignorer la recherche floue
        if len(query) < 3:
            return
        
        # Générer les n-grammes de la requête
        query_ngrams = self._get_ngrams(query, 2)  # Bigrammes
        
        # Pour les requêtes courtes, explorer plus largement
        if len(query) <= 5:
            # Rechercher les mots commençant par les mêmes caractères
            first_char = query[0]
            node = self.root
            
            if first_char in node.children:
                # Explorer l'arbre à partir du premier caractère
                candidates = self._collect_candidates(node.children[first_char], query, threshold)
                
                # Évaluer chaque candidat
                for candidate, dist in candidates:
                    candidate_node = self._find_node(candidate)
                    if candidate_node:
                        # Score inversement proportionnel à la distance
                        score = base_score * (1.0 - (dist / (threshold + 1)))
                        self._collect_files_from_node(candidate_node, results, score)
        else:
            # Pour les requêtes plus longues, utiliser une approche par n-grammes
            # (Plus efficace pour réduire l'espace de recherche)
            candidates = self._find_ngram_candidates(query, query_ngrams, threshold)
            
            for candidate, dist in candidates:
                candidate_node = self._find_node(candidate)
                if candidate_node:
                    # Score inversement proportionnel à la distance
                    score = base_score * (1.0 - (dist / (threshold + 1)))
                    self._collect_files_from_node(candidate_node, results, score)
    
    def _get_ngrams(self, word: str, n: int) -> Set[str]:
        """
        Génère les n-grammes d'un mot
        
        Args:
            word: Mot
            n: Taille des n-grammes
            
        Returns:
            Ensemble des n-grammes
        """
        # Vérifier le cache
        cache_key = (word, n)
        if cache_key in self._ngram_cache:
            return self._ngram_cache[cache_key]
        
        # Générer les n-grammes
        padded = f"${word}$"  # Padding pour les bords
        ngrams = set()
        
        for i in range(len(padded) - n + 1):
            ngrams.add(padded[i:i+n])
        
        # Mettre en cache
        self._ngram_cache[cache_key] = ngrams
        return ngrams
    
    def _collect_candidates(self, start_node: TrieNode, query: str, threshold: int) -> List[Tuple[str, int]]:
        """
        Collecte les candidats pour une recherche approximative
        
        Args:
            start_node: Nœud de départ
            query: Requête
            threshold: Seuil de distance maximale
            
        Returns:
            Liste de tuples (candidat, distance)
        """
        candidates = []
        max_candidates = 100  # Limite pour économiser la mémoire
        
        # Exploration limitée en profondeur
        def dfs(node, prefix, depth):
            # Limiter la profondeur
            if depth > len(query) + threshold:
                return
            
            # Si nœud terminal, calculer la distance
            if node.is_end:
                dist = self._levenshtein_distance(query, prefix)
                if dist <= threshold:
                    candidates.append((prefix, dist))
            
            # Arrêter si on a assez de candidats
            if len(candidates) >= max_candidates:
                return
            
            # Explorer les enfants
            for char, child in node.children.items():
                dfs(child, prefix + char, depth + 1)
        
        # Démarrer l'exploration
        dfs(start_node, query[0], 1)
        
        # Trier par distance
        candidates.sort(key=lambda x: x[1])
        return candidates
    
    def _find_ngram_candidates(self, query: str, query_ngrams: Set[str], threshold: int) -> List[Tuple[str, int]]:
        """
        Trouve les candidats par similarité de n-grammes
        
        Args:
            query: Requête
            query_ngrams: Ensemble des n-grammes de la requête
            threshold: Seuil de distance maximale
            
        Returns:
            Liste de tuples (candidat, distance)
        """
        # Ici, une implémentation plus complexe nécessiterait un index inversé des n-grammes
        # Pour une implémentation simple, on utilise un échantillonnage
        candidates = []
        
        # Explorer les premiers niveaux de l'arbre pour trouver des candidats potentiels
        def collect_words(node, prefix, depth, max_depth=10):
            if depth > max_depth:
                return
            
            if node.is_end:
                candidates.append(prefix)
            
            for char, child in node.children.items():
                collect_words(child, prefix + char, depth + 1, max_depth)
        
        # Collecter un échantillon de mots
        collect_words(self.root, "", 0, max_depth=6)
        
        # Calculer la distance pour chaque candidat
        result = []
        for candidate in candidates:
            dist = self._levenshtein_distance(query, candidate)
            if dist <= threshold:
                result.append((candidate, dist))
        
        # Trier par distance
        result.sort(key=lambda x: x[1])
        return result[:50]  # Limiter le nombre de résultats
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """
        Calcule la distance de Levenshtein entre deux chaînes
        Optimisée pour utiliser le moins de mémoire possible
        
        Args:
            s1: Première chaîne
            s2: Deuxième chaîne
            
        Returns:
            Distance de Levenshtein
        """
        # Optimisation pour les chaînes identiques ou vides
        if s1 == s2:
            return 0
        if not s1:
            return len(s2)
        if not s2:
            return len(s1)
        
        # Optimisation: utiliser uniquement deux lignes de matrice
        prev = list(range(len(s2) + 1))
        current = [0] * (len(s2) + 1)
        
        for i in range(1, len(s1) + 1):
            current[0] = i
            for j in range(1, len(s2) + 1):
                if s1[i-1] == s2[j-1]:
                    current[j] = prev[j-1]
                else:
                    current[j] = 1 + min(prev[j], current[j-1], prev[j-1])
            
            # Échanger les lignes
            prev, current = current, prev
        
        return prev[len(s2)]
    
    def optimize_memory(self) -> None:
        """Optimise l'utilisation de la mémoire en réduisant l'arbre"""
        if self._memory_optimized:
            return
        
        # Compresser les branches uniques
        self._compress_branches(self.root)
        
        # Forcer la libération de la mémoire
        gc.collect()
        
        self._memory_optimized = True
    
    def _compress_branches(self, node: TrieNode) -> None:
        """
        Compresse les branches uniques pour économiser de la mémoire
        
        Args:
            node: Nœud à compresser
        """
        # Cette implémentation est simplifiée
        # Une compression réelle nécessiterait de modifier la structure du nœud
        
        # Réduire les ensembles de file_ids
        if len(node.file_ids) > 100:
            # Convertir en liste pour économiser de la mémoire
            node.file_ids = set(list(node.file_ids)[:100])
        
        # Appliquer récursivement aux enfants
        for child in list(node.children.values()):
            self._compress_branches(child)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Récupère les statistiques
        
        Returns:
            Dictionnaire des statistiques
        """
        stats = self._stats.copy()
        stats["size"] = self._size
        
        # Calculer les performances moyennes
        if stats["searches"] > 0:
            stats["avg_search_time"] = stats["search_time"] / stats["searches"]
        else:
            stats["avg_search_time"] = 0
        
        return stats