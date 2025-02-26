#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interface de configuration du lanceur
Permet de configurer les emplacements d'indexation et autres options
"""

import os
import logging
from typing import List, Dict, Any, Set
from functools import partial

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel,
    QPushButton, QLineEdit, QCheckBox, QListWidget, QListWidgetItem,
    QFileDialog, QSpinBox, QMessageBox, QGroupBox, QComboBox, QFormLayout,
    QDialogButtonBox, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt5.QtGui import QIcon, QFont

logger = logging.getLogger(__name__)

class SettingsDialog(QDialog):
    """Fenêtre de paramètres"""
    
    # Signal émis lorsque la configuration est mise à jour
    config_updated = pyqtSignal()
    
    def __init__(self, config, indexer, parent=None):
        """
        Initialise la fenêtre de paramètres
        
        Args:
            config: Instance de la configuration
            indexer: Instance de l'indexeur
            parent: Widget parent
        """
        super().__init__(parent)
        
        # Stocker les références
        self.config = config
        self.indexer = indexer
        
        # Configuration de la fenêtre
        self.setWindowTitle("Paramètres")
        self.setMinimumSize(600, 450)
        
        # Créer l'interface
        self._setup_ui()
        
        # Charger les valeurs initiales
        self._load_config_values()
        
        # Flag pour empêcher les sauvegardes multiples
        self._saving = False
    
    def _setup_ui(self):
        """Configure l'interface utilisateur"""
        # Layout principal
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Onglets
        tabs = QTabWidget()
        
        # Onglet "Emplacements"
        locations_tab = QWidget()
        tabs.addTab(locations_tab, "Emplacements")
        
        # Onglet "Options"
        options_tab = QWidget()
        tabs.addTab(options_tab, "Options")
        
        # Onglet "Avancé"
        advanced_tab = QWidget()
        tabs.addTab(advanced_tab, "Avancé")
        
        # Ajouter les onglets au layout
        main_layout.addWidget(tabs)
        
        # Boutons OK/Annuler
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self._save_config)
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)
        
        # Configurer l'onglet "Emplacements"
        self._setup_locations_tab(locations_tab)
        
        # Configurer l'onglet "Options"
        self._setup_options_tab(options_tab)
        
        # Configurer l'onglet "Avancé"
        self._setup_advanced_tab(advanced_tab)
    
    def _setup_locations_tab(self, tab):
        """
        Configure l'onglet "Emplacements"
        
        Args:
            tab: Widget de l'onglet
        """
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        
        # Liste des emplacements
        layout.addWidget(QLabel("Emplacements indexés :"))
        
        self.locations_list = QListWidget()
        self.locations_list.setMinimumHeight(200)
        layout.addWidget(self.locations_list)
        
        # Boutons d'action
        buttons_layout = QHBoxLayout()
        
        add_btn = QPushButton("Ajouter un dossier...")
        add_btn.clicked.connect(self._add_location)
        buttons_layout.addWidget(add_btn)
        
        add_network_btn = QPushButton("Ajouter un dossier réseau...")
        add_network_btn.clicked.connect(self._add_network_location)
        buttons_layout.addWidget(add_network_btn)
        
        remove_btn = QPushButton("Supprimer")
        remove_btn.clicked.connect(self._remove_location)
        buttons_layout.addWidget(remove_btn)
        
        layout.addLayout(buttons_layout)
        
        # Section d'exclusion
        exclusion_group = QGroupBox("Exclusions")
        exclusion_layout = QVBoxLayout(exclusion_group)
        
        # Chemins exclus
        exclusion_layout.addWidget(QLabel("Chemins exclus :"))
        
        self.excluded_paths_list = QListWidget()
        self.excluded_paths_list.setMaximumHeight(100)
        exclusion_layout.addWidget(self.excluded_paths_list)
        
        # Boutons d'action pour les exclusions
        exclusion_buttons = QHBoxLayout()
        
        add_exclusion_btn = QPushButton("Ajouter...")
        add_exclusion_btn.clicked.connect(self._add_exclusion)
        exclusion_buttons.addWidget(add_exclusion_btn)
        
        remove_exclusion_btn = QPushButton("Supprimer")
        remove_exclusion_btn.clicked.connect(self._remove_exclusion)
        exclusion_buttons.addWidget(remove_exclusion_btn)
        
        exclusion_layout.addLayout(exclusion_buttons)
        
        # Extensions exclues
        extensions_layout = QHBoxLayout()
        extensions_layout.addWidget(QLabel("Extensions exclues :"))
        
        self.excluded_extensions = QLineEdit()
        self.excluded_extensions.setPlaceholderText("Ex: .tmp, .bak, .log")
        extensions_layout.addWidget(self.excluded_extensions)
        
        exclusion_layout.addLayout(extensions_layout)
        
        layout.addWidget(exclusion_group)
    
    def _setup_options_tab(self, tab):
        """
        Configure l'onglet "Options"
        
        Args:
            tab: Widget de l'onglet
        """
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        
        # Emplacement de la base de données
        db_group = QGroupBox("Base de données")
        db_layout = QVBoxLayout(db_group)
        
        db_path_layout = QHBoxLayout()
        db_path_layout.addWidget(QLabel("Emplacement :"))
        
        self.db_path = QLineEdit()
        self.db_path.setReadOnly(True)
        db_path_layout.addWidget(self.db_path)
        
        browse_db_btn = QPushButton("Parcourir...")
        browse_db_btn.clicked.connect(self._browse_db_path)
        db_path_layout.addWidget(browse_db_btn)
        
        db_layout.addLayout(db_path_layout)
        layout.addWidget(db_group)
        
        # Options de recherche
        search_group = QGroupBox("Recherche")
        search_layout = QFormLayout(search_group)
        
        self.max_results = QSpinBox()
        self.max_results.setMinimum(10)
        self.max_results.setMaximum(1000)
        self.max_results.setSingleStep(10)
        search_layout.addRow("Nombre maximal de résultats :", self.max_results)
        
        layout.addWidget(search_group)
        
        # Raccourci clavier
        hotkey_group = QGroupBox("Raccourci clavier global")
        hotkey_layout = QHBoxLayout(hotkey_group)
        
        self.modifier_combo = QComboBox()
        self.modifier_combo.addItems(["Ctrl", "Alt", "Shift", "Win"])
        hotkey_layout.addWidget(self.modifier_combo)
        
        hotkey_layout.addWidget(QLabel("+"))
        
        self.key_combo = QComboBox()
        self.key_combo.addItems(["Space", "Tab", "Return", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z"])
        hotkey_layout.addWidget(self.key_combo)
        
        hotkey_layout.addStretch()
        
        layout.addWidget(hotkey_group)
        
        # Espace vertical
        layout.addStretch()
    
    def _setup_advanced_tab(self, tab):
        """
        Configure l'onglet "Avancé"
        
        Args:
            tab: Widget de l'onglet
        """
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        
        # Intervalles de mise à jour
        update_group = QGroupBox("Intervalles de mise à jour (minutes)")
        update_layout = QFormLayout(update_group)
        
        self.local_interval = QSpinBox()
        self.local_interval.setMinimum(5)
        self.local_interval.setMaximum(1440)  # 24 heures
        update_layout.addRow("Disques locaux :", self.local_interval)
        
        self.network_interval = QSpinBox()
        self.network_interval.setMinimum(15)
        self.network_interval.setMaximum(1440 * 7)  # 7 jours
        update_layout.addRow("Disques réseau :", self.network_interval)
        
        layout.addWidget(update_group)
        
        # Options d'indexation
        index_group = QGroupBox("Indexation")
        index_layout = QVBoxLayout(index_group)
        
        self.initial_indexing = QCheckBox("Effectuer une indexation initiale au démarrage")
        index_layout.addWidget(self.initial_indexing)
        
        # Bouton pour forcer une réindexation complète
        reindex_btn = QPushButton("Forcer une réindexation complète")
        reindex_btn.clicked.connect(self._force_reindex)
        index_layout.addWidget(reindex_btn)
        
        layout.addWidget(index_group)
        
        # Statistiques
        stats_group = QGroupBox("Statistiques")
        stats_layout = QFormLayout(stats_group)
        
        self.total_files_label = QLabel("0")
        stats_layout.addRow("Fichiers indexés :", self.total_files_label)
        
        self.total_dirs_label = QLabel("0")
        stats_layout.addRow("Dossiers indexés :", self.total_dirs_label)
        
        self.last_indexed_label = QLabel("-")
        stats_layout.addRow("Dernière indexation :", self.last_indexed_label)
        
        # Bouton pour rafraîchir les statistiques
        refresh_stats_btn = QPushButton("Rafraîchir")
        refresh_stats_btn.clicked.connect(self._refresh_stats)
        stats_layout.addRow("", refresh_stats_btn)
        
        layout.addWidget(stats_group)
        
        # Espace vertical
        layout.addStretch()
    
    def _load_config_values(self):
        """Charge les valeurs de configuration"""
        # Emplacements indexés
        self.locations_list.clear()
        for location in self.config.get_indexed_locations():
            item = QListWidgetItem(location["path"])
            item.setData(Qt.UserRole, location)
            self.locations_list.addItem(item)
        
        # Chemins exclus
        self.excluded_paths_list.clear()
        for path in self.config.get("excluded_paths", []):
            self.excluded_paths_list.addItem(path)
        
        # Extensions exclues
        extensions = self.config.get("excluded_extensions", [])
        self.excluded_extensions.setText(", ".join(extensions))
        
        # Emplacement de la base de données
        self.db_path.setText(self.config.get("database_path", ""))
        
        # Options de recherche
        self.max_results.setValue(self.config.get("max_results", 50))
        
        # Raccourci clavier
        hotkey = self.config.get("hotkey", {"modifier": "ctrl", "key": "space"})
        modifier_index = self.modifier_combo.findText(hotkey["modifier"].capitalize())
        self.modifier_combo.setCurrentIndex(max(0, modifier_index))
        
        key_index = self.key_combo.findText(hotkey["key"].capitalize())
        self.key_combo.setCurrentIndex(max(0, key_index))
        
        # Intervalles de mise à jour
        update_interval = self.config.get("update_interval", {"local": 60, "network": 180})
        self.local_interval.setValue(update_interval["local"])
        self.network_interval.setValue(update_interval["network"])
        
        # Options d'indexation
        self.initial_indexing.setChecked(self.config.get("perform_initial_indexing", True))
        
        # Statistiques
        self._refresh_stats()
    
    def _add_location(self):
        """Ajoute un emplacement à indexer"""
        folder = QFileDialog.getExistingDirectory(
            self, "Sélectionner un dossier à indexer",
            os.path.expanduser("~")
        )
        
        if folder:
            # Vérifier si l'emplacement est déjà dans la liste
            for i in range(self.locations_list.count()):
                item = self.locations_list.item(i)
                if item.text() == folder:
                    return
            
            # Ajouter à la liste
            new_item = QListWidgetItem(folder)
            new_item.setData(Qt.UserRole, {"path": folder, "include_subfolders": True})
            self.locations_list.addItem(new_item)
    
    def _add_network_location(self):
        """Ajoute un emplacement réseau à indexer"""
        # Demander le chemin réseau
        from PyQt5.QtWidgets import QInputDialog
        network_path, ok = QInputDialog.getText(
            self, "Ajouter un dossier réseau",
            "Entrez le chemin réseau (format UNC, ex: \\\\serveur\\partage):"
        )
        
        if ok and network_path:
            # Vérifier le format
            if not (network_path.startswith("\\\\") or network_path.startswith("//")):
                QMessageBox.warning(
                    self, "Format incorrect",
                    "Le chemin réseau doit être au format UNC (\\\\serveur\\partage)"
                )
                return
            
            # Vérifier si l'emplacement est déjà dans la liste
            for i in range(self.locations_list.count()):
                item = self.locations_list.item(i)
                if item.text() == network_path:
                    return
            
            # Ajouter à la liste
            new_item = QListWidgetItem(network_path)
            new_item.setData(Qt.UserRole, {"path": network_path, "include_subfolders": True})
            self.locations_list.addItem(new_item)
    
    def _remove_location(self):
        """Supprime un emplacement de la liste"""
        # Obtenir l'élément sélectionné
        selected_items = self.locations_list.selectedItems()
        if not selected_items:
            return
        
        # Confirmation
        if QMessageBox.question(
            self, "Confirmer la suppression",
            "Voulez-vous vraiment supprimer cet emplacement de l'indexation ?",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            # Supprimer de la liste
            for item in selected_items:
                self.locations_list.takeItem(self.locations_list.row(item))
    
    def _add_exclusion(self):
        """Ajoute un chemin d'exclusion"""
        folder = QFileDialog.getExistingDirectory(
            self, "Sélectionner un dossier à exclure",
            os.path.expanduser("~")
        )
        
        if folder:
            # Vérifier si le chemin est déjà dans la liste
            for i in range(self.excluded_paths_list.count()):
                if self.excluded_paths_list.item(i).text() == folder:
                    return
            
            # Ajouter à la liste
            self.excluded_paths_list.addItem(folder)
    
    def _remove_exclusion(self):
        """Supprime un chemin d'exclusion"""
        # Obtenir l'élément sélectionné
        selected_items = self.excluded_paths_list.selectedItems()
        if not selected_items:
            return
        
        # Supprimer de la liste
        for item in selected_items:
            self.excluded_paths_list.takeItem(self.excluded_paths_list.row(item))
    
    def _browse_db_path(self):
        """Permet de sélectionner l'emplacement de la base de données"""
        current_path = self.db_path.text()
        current_dir = os.path.dirname(current_path) if current_path else os.path.expanduser("~")
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Emplacement de la base de données",
            current_dir,
            "Fichiers SQLite (*.db)"
        )
        
        if file_path:
            # S'assurer que l'extension est .db
            if not file_path.endswith(".db"):
                file_path += ".db"
            
            self.db_path.setText(file_path)
    
    def _force_reindex(self):
        """Force une réindexation complète"""
        # Confirmation
        if QMessageBox.question(
            self, "Confirmer la réindexation",
            "Cette opération va supprimer et recréer l'index complet.\n"
            "Cela peut prendre du temps en fonction du nombre de fichiers.\n\n"
            "Voulez-vous continuer ?",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            # Sauvegarder la configuration actuelle
            self._save_config()
            
            # Réinitialiser la base de données
            import sqlite3
            try:
                # Supprimer et recréer les tables
                db_path = self.config.get("database_path", "")
                if os.path.exists(db_path):
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    
                    # Supprimer les tables existantes
                    cursor.execute("DROP TABLE IF EXISTS files")
                    cursor.execute("DROP TABLE IF EXISTS indexed_paths")
                    
                    conn.commit()
                    conn.close()
                
                # Lancer l'indexation initiale
                self.indexer.perform_initial_indexing()
                
                QMessageBox.information(
                    self, "Réindexation lancée",
                    "La réindexation a été lancée avec succès.\n"
                    "Ce processus s'exécute en arrière-plan et peut prendre du temps."
                )
            except Exception as e:
                logger.error(f"Erreur lors de la réinitialisation de la base de données: {e}")
                QMessageBox.critical(
                    self, "Erreur",
                    f"Une erreur est survenue lors de la réindexation:\n{str(e)}"
                )
    
    def _refresh_stats(self):
        """Rafraîchit les statistiques"""
        stats = self.indexer.db.get_stats()
        
        # Mettre à jour les labels
        self.total_files_label.setText(str(stats.get("total_real_files", 0)))
        self.total_dirs_label.setText(str(stats.get("total_dirs", 0)))
        
        # Formater la date
        last_indexed = stats.get("last_indexed", 0)
        if last_indexed > 0:
            import datetime
            date_str = datetime.datetime.fromtimestamp(last_indexed).strftime("%d/%m/%Y %H:%M")
            self.last_indexed_label.setText(date_str)
        else:
            self.last_indexed_label.setText("-")
    
    def _save_config(self):
        """Sauvegarde la configuration de manière non bloquante"""
        # Éviter les sauvegardes multiples
        if self._saving:
            return
            
        self._saving = True
        
        # Désactiver les boutons pendant la sauvegarde
        self.button_box.setEnabled(False)
        
        try:
            # Collecter toutes les données de l'interface
            # Emplacements indexés
            locations = []
            for i in range(self.locations_list.count()):
                item = self.locations_list.item(i)
                location = item.data(Qt.UserRole)
                locations.append(location)
            
            self.config.set("indexed_locations", locations)
            
            # Chemins exclus
            excluded_paths = []
            for i in range(self.excluded_paths_list.count()):
                excluded_paths.append(self.excluded_paths_list.item(i).text())
            
            self.config.set("excluded_paths", excluded_paths)
            
            # Extensions exclues
            extensions_text = self.excluded_extensions.text()
            extensions = [ext.strip() for ext in extensions_text.split(",") if ext.strip()]
            self.config.set("excluded_extensions", extensions)
            
            # Emplacement de la base de données
            self.config.set("database_path", self.db_path.text())
            
            # Options de recherche
            self.config.set("max_results", self.max_results.value())
            
            # Raccourci clavier
            hotkey = {
                "modifier": self.modifier_combo.currentText().lower(),
                "key": self.key_combo.currentText().lower()
            }
            self.config.set("hotkey", hotkey)
            
            # Intervalles de mise à jour
            update_interval = {
                "local": self.local_interval.value(),
                "network": self.network_interval.value()
            }
            self.config.set("update_interval", update_interval)
            
            # Options d'indexation
            self.config.set("perform_initial_indexing", self.initial_indexing.isChecked())
            
            # Sauvegarder la configuration de manière asynchrone avec un callback
            def on_save_complete(success):
                self._saving = False
                self.button_box.setEnabled(True)
                
                if success:
                    # Fermer d'abord la boîte de dialogue avant d'émettre le signal
                    # Cela évite que le signal ne soit traité pendant que la boîte de dialogue est encore active
                    self.done(QDialog.Accepted)
                    
                    # Émettre le signal APRÈS avoir fermé la boîte de dialogue, avec un léger délai
                    QTimer.singleShot(100, lambda: self.config_updated.emit())
                else:
                    QMessageBox.warning(
                        self, "Erreur",
                        "La sauvegarde de la configuration a échoué. Veuillez réessayer."
                    )
            
            # Utiliser la sauvegarde asynchrone
            self.config.save_async(on_save_complete)
            
        except Exception as e:
            self._saving = False
            self.button_box.setEnabled(True)
            logger.error(f"Erreur lors de la sauvegarde de la configuration: {e}")
            QMessageBox.critical(
                self, "Erreur",
                f"Une erreur est survenue lors de la sauvegarde de la configuration:\n{str(e)}"
            )