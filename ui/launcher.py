#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interface principale du lanceur
Optimisée pour une utilisation fluide et une faible consommation de ressources
"""

import os
import sys
import time
import logging
import threading
from typing import List, Dict, Any, Optional, Set, Tuple
from functools import lru_cache

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QLabel, QApplication, QFrame, QMenu, QAction, QToolButton, QMainWindow,
    QSizePolicy, QCompleter, QToolTip, QSystemTrayIcon, QStyle, QMessageBox
)
from PyQt5.QtCore import (
    Qt, QSize, QTimer, QEvent, QObject, pyqtSignal, pyqtSlot, QRect, QThread, 
    QPoint, QSettings, QModelIndex, QMetaObject
)
from PyQt5.QtGui import (
    QIcon, QKeyEvent, QFont, QColor, QPalette, QFontMetrics, QPixmap, 
    QMouseEvent, QCursor
)

# Import pour le raccourci global sous Windows
import win32con
import win32api
import win32gui
from ctypes import wintypes

logger = logging.getLogger(__name__)

# Identifiant unique pour le raccourci clavier global
WM_HOTKEY_MSG = win32con.WM_USER + 1
HOTKEY_ID = 1

class HotkeyManager:
    """Gestionnaire de raccourcis clavier globaux utilisant un thread unique"""
    
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        """Implémentation d'un singleton thread-safe pour gérer les raccourcis"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = HotkeyManager()
            return cls._instance
    
    def __init__(self):
        """Initialise le gestionnaire de raccourcis"""
        self._hwnd = None
        self._registered_hotkeys = {}  # {id: (callback, modifier, key)}
        self._next_id = 1
        self._thread = None
        self._stop_event = threading.Event()
        self._is_running = False
    
    def start(self):
        """Démarre le thread de gestion des raccourcis"""
        if self._is_running:
            return
            
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="HotkeyManagerThread")
        self._thread.start()
        self._is_running = True
        logger.info("Gestionnaire de raccourcis démarré")
    
    def stop(self):
        """Arrête le thread de gestion des raccourcis"""
        if not self._is_running:
            return
            
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        self._is_running = False
        self._unregister_all_hotkeys()
        logger.info("Gestionnaire de raccourcis arrêté")
    
    def _run(self):
        """Fonction principale du thread"""
        try:
            # Créer une classe de fenêtre pour capturer les messages
            wc = win32gui.WNDCLASS()
            wc.lpszClassName = "QuickLaunchHotkeyWindow"
            wc.lpfnWndProc = self._wnd_proc
            wc.hInstance = win32api.GetModuleHandle(None)
            
            # Enregistrer la classe de fenêtre
            win32gui.RegisterClass(wc)
            
            # Créer la fenêtre
            self._hwnd = win32gui.CreateWindowEx(
                0, wc.lpszClassName, "QuickLaunch Hotkey Window",
                0, 0, 0, 0, 0, 0, 0, wc.hInstance, None
            )
            
            # Enregistrer les raccourcis
            self._register_pending_hotkeys()
            
            # Boucle de messages simplifée
            while not self._stop_event.is_set():
                # Utiliser PumpWaitingMessages au lieu de GetMessage ou PeekMessage
                # C'est plus simple et plus fiable
                win32gui.PumpWaitingMessages()
                time.sleep(0.1)
                
        except Exception as e:
            logger.error(f"Erreur dans le gestionnaire de raccourcis: {e}")
        finally:
            # Nettoyer
            if self._hwnd:
                try:
                    self._unregister_all_hotkeys()
                    win32gui.DestroyWindow(self._hwnd)
                    self._hwnd = None
                except Exception:
                    pass
    
    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        """Gestionnaire de messages Windows"""
        if msg == win32con.WM_HOTKEY and wparam in self._registered_hotkeys:
            # Récupérer et appeler le callback
            callback, _, _ = self._registered_hotkeys[wparam]
            try:
                if callback:
                    # Appel via QTimer pour exécuter sur le thread principal
                    QTimer.singleShot(0, callback)
            except Exception as e:
                logger.error(f"Erreur lors de l'appel du callback de raccourci: {e}")
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)
    
    def register_hotkey(self, callback, modifier, vk_code):
        """
        Enregistre un raccourci global
        
        Args:
            callback: Fonction à appeler lorsque le raccourci est activé
            modifier: Modificateur (MOD_CONTROL, MOD_ALT, etc.)
            vk_code: Code de la touche virtuelle
            
        Returns:
            ID du raccourci ou None en cas d'erreur
        """
        hotkey_id = self._next_id
        self._next_id += 1
        
        # Stocker le callback et la configuration
        self._registered_hotkeys[hotkey_id] = (callback, modifier, vk_code)
        
        # Si le thread est en cours d'exécution, enregistrer immédiatement
        if self._hwnd:
            success = self._register_hotkey(hotkey_id, modifier, vk_code)
            if success:
                return hotkey_id
            else:
                del self._registered_hotkeys[hotkey_id]
                return None
        
        # Sinon, il sera enregistré au démarrage du thread
        return hotkey_id
    
    def register_hotkey_safe(self, callback, modifier, vk_code):
        """
        Enregistre un raccourci global de manière thread-safe
        
        Args:
            callback: Fonction à appeler lorsque le raccourci est activé
            modifier: Modificateur (MOD_CONTROL, MOD_ALT, etc.)
            vk_code: Code de la touche virtuelle
            
        Returns:
            Helper qui contiendra l'ID du raccourci
        """
        # Utiliser QTimer pour s'assurer que l'enregistrement se fait sur le thread principal
        from PyQt5.QtCore import QTimer, QObject
        
        class RegisterHelper(QObject):
            def __init__(self, manager, callback, modifier, vk_code):
                super().__init__()
                self.manager = manager
                self.callback = callback
                self.modifier = modifier
                self.vk_code = vk_code
                self.hotkey_id = None
                
            def do_register(self):
                self.hotkey_id = self.manager.register_hotkey(
                    self.callback, self.modifier, self.vk_code
                )
        
        helper = RegisterHelper(self, callback, modifier, vk_code)
        QTimer.singleShot(0, helper.do_register)
        return helper  # Retourner l'helper qui contiendra l'ID plus tard
    
    def _register_hotkey(self, hotkey_id, modifier, vk_code):
        """Enregistre un raccourci auprès de Windows"""
        if not self._hwnd:
            return False
            
        try:
            result = win32gui.RegisterHotKey(self._hwnd, hotkey_id, modifier, vk_code)
            return result
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement du raccourci {hotkey_id}: {e}")
            return False
    
    def _register_pending_hotkeys(self):
        """Enregistre tous les raccourcis en attente"""
        if not self._hwnd:
            return
            
        for hotkey_id, (_, modifier, vk_code) in list(self._registered_hotkeys.items()):
            if not self._register_hotkey(hotkey_id, modifier, vk_code):
                # Supprimer en cas d'échec
                self._registered_hotkeys.pop(hotkey_id, None)
    
    def unregister_hotkey(self, hotkey_id):
        """Supprime un raccourci global"""
        if hotkey_id in self._registered_hotkeys:
            # Supprimer auprès de Windows si le thread est en cours d'exécution
            if self._hwnd:
                try:
                    win32gui.UnregisterHotKey(self._hwnd, hotkey_id)
                except Exception:
                    pass
            
            # Supprimer du dictionnaire
            del self._registered_hotkeys[hotkey_id]
    
    def _unregister_all_hotkeys(self):
        """Supprime tous les raccourcis globaux"""
        if not self._hwnd:
            return
            
        for hotkey_id in list(self._registered_hotkeys.keys()):
            try:
                win32gui.UnregisterHotKey(self._hwnd, hotkey_id)
            except Exception:
                pass
        
        self._registered_hotkeys.clear()

class PinnedItemWidget(QWidget):
    """Widget pour afficher un élément épinglé"""
    clicked = pyqtSignal(str)  # Signal émis lors du clic (avec le chemin)
    remove_requested = pyqtSignal(str)  # Signal pour demander la suppression d'un élément
    
    def __init__(self, name: str, path: str, parent=None):
        """
        Initialise le widget
        
        Args:
            name: Nom à afficher
            path: Chemin complet de l'élément
            parent: Widget parent
        """
        super().__init__(parent)
        self.path = path
        self.name = name
        
        # Configuration du widget
        self.setMouseTracking(True)
        self.setFixedHeight(30)
        self.setMinimumWidth(100)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        
        # Mise en page
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(5)
        
        # Créer et configurer le label
        self.label = QLabel(name)
        self.label.setToolTip(path)
        self.label.setStyleSheet("color: #EEEEEE; font-size: 12px;")
        layout.addWidget(self.label)
        
        # Créer le bouton de fermeture
        self.close_btn = QToolButton()
        self.close_btn.setText("×")
        self.close_btn.setStyleSheet(
            "QToolButton { color: #BBBBBB; background: transparent; border: none; font-size: 14px; }"
            "QToolButton:hover { color: #FF5555; }"
        )
        self.close_btn.setFixedSize(16, 16)
        self.close_btn.clicked.connect(self._on_close_clicked)
        layout.addWidget(self.close_btn)
        
        # Appliquer le style
        self.setStyleSheet(
            "PinnedItemWidget { background-color: #444444; border-radius: 3px; }"
            "PinnedItemWidget:hover { background-color: #555555; }"
        )
    
    def mousePressEvent(self, event: QMouseEvent):
        """Gère les clics de souris"""
        if event.button() == Qt.LeftButton:
            # Émettre le signal avec le chemin
            self.clicked.emit(self.path)
    
    def _on_close_clicked(self):
        """Gère le clic sur le bouton de fermeture"""
        self.remove_requested.emit(self.path)

class SearchResultItem(QListWidgetItem):
    """Item personnalisé pour afficher un résultat de recherche"""
    
    def __init__(self, name: str, path: str, is_dir: bool, parent=None):
        """
        Initialise l'item
        
        Args:
            name: Nom du fichier/dossier
            path: Chemin complet
            is_dir: True si c'est un dossier, False sinon
            parent: Widget parent
        """
        super().__init__(parent)
        self.path = path
        self.name = name
        self.is_dir = is_dir
        
        # Définir le texte à afficher
        self.setText(name)
        
        # Définir l'icône en fonction du type
        icon = QApplication.style().standardIcon(
            QStyle.SP_DirIcon if is_dir else QStyle.SP_FileIcon
        )
        self.setIcon(icon)
        
        # Définir le tooltip avec le chemin complet
        self.setToolTip(path)
        
        # Stocker les données pour le tri et le filtrage
        self.setData(Qt.UserRole, {
            'path': path,
            'name': name,
            'is_dir': is_dir
        })

class LauncherWindow(QMainWindow):
    """Fenêtre principale du lanceur"""
    
    def __init__(self, db, indexer, config, watcher):
        """
        Initialise la fenêtre du lanceur
        
        Args:
            db: Instance de la base de données
            indexer: Instance de l'indexeur
            config: Instance de la configuration
            watcher: Instance du surveillant de fichiers
        """
        super().__init__()
        
        # Stocker les références
        self.db = db
        self.indexer = indexer
        self.config = config
        self.watcher = watcher
        
        # Variables d'état
        self.current_dir = ""
        self.history = []
        self.history_index = -1
        self.last_query = ""
        self.visible = False
        self._hotkey_id = None
        self._hotkey_helper = None
        
        # Configurer la fenêtre
        self._setup_ui()
        
        # Charger les éléments épinglés
        self._load_pinned_items()
        
        # Surveillance du réseau et mise à jour périodique
        self._setup_background_timers()
    
    def _setup_ui(self):
        """Configure l'interface utilisateur"""
        # Configurer la fenêtre principale
        self.setWindowTitle("QuickLaunch")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Créer le widget central
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        central_widget.setStyleSheet(
            "#centralWidget { background-color: #333333; border-radius: 8px; border: 1px solid #444444; }"
        )
        self.setCentralWidget(central_widget)
        
        # Créer le layout principal
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(5)
        
        # Créer la zone des éléments épinglés
        self.pinned_container = QWidget()
        self.pinned_layout = QHBoxLayout(self.pinned_container)
        self.pinned_layout.setContentsMargins(0, 0, 0, 5)
        self.pinned_layout.setSpacing(5)
        main_layout.addWidget(self.pinned_container)
        
        # Créer le conteneur de recherche
        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(5)
        
        # Créer la barre de recherche
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Rechercher...")
        self.search_bar.setStyleSheet(
            "QLineEdit { "
            "background-color: #444444; "
            "color: #EEEEEE; "
            "border: none; "
            "border-radius: 4px; "
            "padding: 6px; "
            "selection-background-color: #666666; "
            "font-size: 14px; "
            "}"
        )
        search_layout.addWidget(self.search_bar)
        
        # Bouton de configuration
        settings_btn = QToolButton()
        settings_btn.setIcon(QApplication.style().standardIcon(QStyle.SP_FileDialogDetailedView))
        settings_btn.setStyleSheet(
            "QToolButton { background-color: #555555; border: none; border-radius: 4px; padding: 3px; }"
            "QToolButton:hover { background-color: #666666; }"
        )
        settings_btn.clicked.connect(self._show_settings)
        search_layout.addWidget(settings_btn)
        
        main_layout.addWidget(search_container)
        
        # Créer la liste des résultats
        self.results_list = QListWidget()
        self.results_list.setStyleSheet(
            "QListWidget { "
            "background-color: #3A3A3A; "
            "color: #EEEEEE; "
            "border: none; "
            "border-radius: 4px; "
            "outline: none; "
            "font-size: 13px; "
            "}"
            "QListWidget::item { "
            "padding: 6px; "
            "border-radius: 4px; "
            "}"
            "QListWidget::item:selected { "
            "background-color: #555555; "
            "}"
            "QListWidget::item:hover:!selected { "
            "background-color: #444444; "
            "}"
        )
        self.results_list.setUniformItemSizes(True)
        self.results_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.results_list.itemActivated.connect(self._on_item_activated)
        main_layout.addWidget(self.results_list)
        
        # Barre de chemin pour la navigation
        self.path_bar = QLabel()
        self.path_bar.setStyleSheet(
            "QLabel { "
            "color: #AAAAAA; "
            "background-color: transparent; "
            "font-size: 12px; "
            "padding: 3px; "
            "}"
        )
        self.path_bar.setVisible(False)
        main_layout.addWidget(self.path_bar)
        
        # Définir la taille initiale
        self.resize(500, 400)
        
        # Centrer la fenêtre sur l'écran
        self._center_on_screen()
        
        # Connecter les signaux
        self.search_bar.textChanged.connect(self._on_search_text_changed)
        self.search_bar.returnPressed.connect(self._on_search_return_pressed)
        
        # Installer le gestionnaire d'événements pour les touches fléchées
        self.search_bar.installEventFilter(self)
        self.results_list.installEventFilter(self)
        
        # Créer l'icône de la barre d'état système
        self._setup_tray_icon()
    
    def _center_on_screen(self):
        """Centre la fenêtre sur l'écran"""
        screen_geometry = QApplication.desktop().availableGeometry()
        window_geometry = self.frameGeometry()
        
        # Centrer horizontalement, mais un peu plus haut que le centre vertical
        center_point = screen_geometry.center()
        center_point.setY(center_point.y() - int(screen_geometry.height() * 0.1))
        
        window_geometry.moveCenter(center_point)
        self.move(window_geometry.topLeft())
    
    def _setup_background_timers(self):
        """Configure les timers pour les tâches d'arrière-plan"""
        # Timer pour les mises à jour incrémentielles
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(15 * 60 * 1000)  # 15 minutes
        self.update_timer.timeout.connect(self._on_scheduled_update)
        self.update_timer.start()
        
        # Timer pour les mises à jour d'interface
        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(250)  # 250ms
        self.ui_timer.timeout.connect(self._update_ui_state)
        self.ui_timer.start()
    
    def _setup_tray_icon(self):
        """Configure l'icône de la barre d'état système"""
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QApplication.style().standardIcon(QStyle.SP_FileDialogStart))
        
        # Créer le menu contextuel
        tray_menu = QMenu()
        
        # Action pour afficher/masquer
        show_action = QAction("Afficher", self)
        show_action.triggered.connect(self.show_launcher)
        tray_menu.addAction(show_action)
        
        # Action pour les paramètres
        settings_action = QAction("Paramètres", self)
        settings_action.triggered.connect(self._show_settings)
        tray_menu.addAction(settings_action)
        
        # Séparateur
        tray_menu.addSeparator()
        
        # Action pour quitter
        quit_action = QAction("Quitter", self)
        quit_action.triggered.connect(self._quit_application)
        tray_menu.addAction(quit_action)
        
        # Assigner le menu à l'icône
        self.tray_icon.setContextMenu(tray_menu)
        
        # Afficher l'icône
        self.tray_icon.show()
        
        # Connecter le signal d'activation
        self.tray_icon.activated.connect(self._on_tray_icon_activated)
    
    def _on_tray_icon_activated(self, reason):
        """Gère l'activation de l'icône de la barre d'état système"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_launcher()
    
    def _quit_application(self):
        """Quitte proprement l'application"""
        # Arrêter la surveillance
        self.watcher.stop()
        
        # Arrêter l'indexeur
        self.indexer.stop()
        
        # Arrêter le gestionnaire de raccourcis
        if self._hotkey_id is not None:
            try:
                hotkey_manager = HotkeyManager.get_instance()
                hotkey_manager.unregister_hotkey(self._hotkey_id)
                hotkey_manager.stop()
            except Exception as e:
                logger.error(f"Erreur lors de la libération du raccourci: {e}")
        
        # Quitter l'application
        QApplication.quit()
    
    def _load_pinned_items(self):
        """Charge les éléments épinglés depuis la configuration"""
        # Supprimer les widgets existants
        for i in reversed(range(self.pinned_layout.count())):
            widget = self.pinned_layout.itemAt(i).widget()
            if widget:
                self.pinned_layout.removeWidget(widget)
                widget.deleteLater()
        
        # Charger les éléments épinglés
        pinned_items = self.config.get("pinned_items", [])
        
        for item in pinned_items:
            self._add_pinned_widget(item["name"], item["path"])
        
        # Masquer le conteneur s'il n'y a pas d'éléments
        self.pinned_container.setVisible(len(pinned_items) > 0)
    
    def _add_pinned_widget(self, name: str, path: str):
        """
        Ajoute un widget d'élément épinglé
        
        Args:
            name: Nom à afficher
            path: Chemin complet
        """
        widget = PinnedItemWidget(name, path)
        widget.clicked.connect(self._on_pinned_item_clicked)
        widget.remove_requested.connect(self._on_pinned_item_removed)
        self.pinned_layout.addWidget(widget)
    
    def _on_pinned_item_clicked(self, path: str):
        """
        Gère le clic sur un élément épinglé
        
        Args:
            path: Chemin de l'élément
        """
        if os.path.isdir(path):
            # Si c'est un dossier, naviguer vers celui-ci
            self._navigate_to_directory(path)
        else:
            # Si c'est un fichier, l'ouvrir
            self._open_file(path)
    
    def _on_pinned_item_removed(self, path: str):
        """
        Gère la demande de suppression d'un élément épinglé
        
        Args:
            path: Chemin de l'élément à supprimer
        """
        # Supprimer de la configuration
        self.config.remove_pinned_item(path)
        
        # Recharger les éléments
        self._load_pinned_items()
    
    def _on_search_text_changed(self, text: str):
        """
        Gère les modifications du texte de recherche
        
        Args:
            text: Nouveau texte de recherche
        """
        # Si nous sommes en mode navigation (dans un dossier)
        if self.current_dir:
            if text:
                # Filtrer les résultats localement
                self._filter_directory_results(text)
            else:
                # Réafficher tous les fichiers du dossier
                self._load_directory_contents(self.current_dir)
        else:
            # Mode recherche global
            if text and len(text) >= 1:  # Commencer à chercher dès le premier caractère
                self._perform_search(text)
                self.last_query = text
            else:
                # Effacer les résultats
                self.results_list.clear()
    
    def _on_search_return_pressed(self):
        """Gère l'appui sur Entrée dans la barre de recherche"""
        # S'il y a des résultats, activer le premier
        if self.results_list.count() > 0:
            self.results_list.setCurrentRow(0)
            self._on_item_activated(self.results_list.currentItem())
    
    def _on_item_activated(self, item):
        """
        Gère l'activation d'un élément de la liste
        
        Args:
            item: Élément activé
        """
        if not item:
            return
        
        # Récupérer les données
        path = item.path
        is_dir = item.is_dir
        
        if is_dir:
            # Naviguer vers le dossier
            self._navigate_to_directory(path)
        else:
            # Ouvrir le fichier
            self._open_file(path)
    
    def _navigate_to_directory(self, path: str):
        """
        Navigue vers un dossier
        
        Args:
            path: Chemin du dossier
        """
        if os.path.isdir(path):
            # Ajouter à l'historique
            if self.current_dir:
                self.history.append(self.current_dir)
                self.history_index = len(self.history) - 1
            
            # Définir le dossier courant
            self.current_dir = path
            
            # Effacer la recherche
            self.search_bar.clear()
            
            # Afficher le chemin
            self.path_bar.setText(path)
            self.path_bar.setVisible(True)
            
            # Charger le contenu
            self._load_directory_contents(path)
    
    def _load_directory_contents(self, path: str):
        """
        Charge le contenu d'un dossier
        
        Args:
            path: Chemin du dossier
        """
        self.results_list.clear()
        
        # Option pour remonter d'un niveau
        parent_dir = os.path.dirname(path)
        if parent_dir and parent_dir != path:
            parent_item = SearchResultItem("..", parent_dir, True)
            parent_item.setIcon(QApplication.style().standardIcon(QStyle.SP_FileDialogToParent))
            self.results_list.addItem(parent_item)
        
        # Charger les fichiers depuis la base de données
        files = self.db.get_files_in_dir(path)
        
        # Créer les éléments de la liste
        for file in files:
            item = SearchResultItem(
                file["name"],
                file["path"],
                file["is_dir"] == 1
            )
            self.results_list.addItem(item)
    
    def _filter_directory_results(self, query: str):
        """
        Filtre les résultats de répertoire
        
        Args:
            query: Terme de recherche
        """
        # Obtenir tous les éléments du répertoire
        files = self.db.get_files_in_dir(self.current_dir)
        
        # Filtrer les résultats
        filtered = [f for f in files if query.lower() in f["name"].lower()]
        
        # Effacer la liste
        self.results_list.clear()
        
        # Option pour remonter d'un niveau
# Option pour remonter d'un niveau
        parent_dir = os.path.dirname(self.current_dir)
        if parent_dir and parent_dir != self.current_dir:
            parent_item = SearchResultItem("..", parent_dir, True)
            parent_item.setIcon(QApplication.style().standardIcon(QStyle.SP_FileDialogToParent))
            self.results_list.addItem(parent_item)
        
        # Ajouter les résultats filtrés
        for file in filtered:
            item = SearchResultItem(
                file["name"],
                file["path"],
                file["is_dir"] == 1
            )
            self.results_list.addItem(item)
    
    @pyqtSlot()
    def _perform_search(self, query: str):
        """
        Effectue une recherche
        
        Args:
            query: Terme de recherche
        """
        # Limiter le nombre maximum de résultats
        max_results = self.config.get("max_results", 50)
        
        # Effectuer la recherche
        results = self.db.search(query, max_results=max_results)
        
        # Effacer les résultats précédents
        self.results_list.clear()
        
        # Trier les résultats (dossiers d'abord)
        results.sort(key=lambda x: (0 if x["is_dir"] == 1 else 1, x["name"].lower()))
        
        # Ajouter les résultats à la liste
        for result in results:
            item = SearchResultItem(
                result["name"],
                result["path"],
                result["is_dir"] == 1
            )
            self.results_list.addItem(item)
    
    def _open_file(self, path: str):
        """
        Ouvre un fichier avec l'application par défaut
        
        Args:
            path: Chemin du fichier
        """
        try:
            # Utiliser startfile qui ouvre avec l'application par défaut
            os.startfile(path)
            
            # Masquer le lanceur après ouverture
            self.hide_launcher()
        except Exception as e:
            logger.error(f"Erreur lors de l'ouverture du fichier {path}: {e}")
            # Afficher un message d'erreur?
    
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """
        Filtre personnalisé pour les événements
        
        Args:
            obj: Objet qui a généré l'événement
            event: Événement à filtrer
            
        Returns:
            True si l'événement a été traité, False sinon
        """
        # Gérer les touches spéciales dans la barre de recherche
        if obj == self.search_bar and event.type() == QEvent.KeyPress:
            key_event = event
            
            # Navigation avec les flèches
            if key_event.key() == Qt.Key_Down:
                # Si la liste a des éléments, la sélectionner
                if self.results_list.count() > 0:
                    self.results_list.setCurrentRow(0)
                    self.results_list.setFocus()
                return True
            
            # Navigation en arrière/avant avec Alt+Flèches
            elif key_event.key() == Qt.Key_Left and key_event.modifiers() & Qt.AltModifier:
                self._navigate_back()
                return True
            
            elif key_event.key() == Qt.Key_Right and key_event.modifiers() & Qt.AltModifier:
                self._navigate_forward()
                return True
            
            # Épingler avec Ctrl+P
            elif key_event.key() == Qt.Key_P and key_event.modifiers() & Qt.ControlModifier:
                self._pin_current_selection()
                return True
            
            # Échap pour cacher
            elif key_event.key() == Qt.Key_Escape:
                self.hide_launcher()
                return True
        
        # Gérer les touches spéciales dans la liste des résultats
        elif obj == self.results_list and event.type() == QEvent.KeyPress:
            key_event = event
            
            # Flèche gauche dans un dossier
            if key_event.key() == Qt.Key_Left and self.current_dir:
                self._navigate_back()
                return True
            
            # Flèche droite sur un dossier
            elif key_event.key() == Qt.Key_Right:
                current_item = self.results_list.currentItem()
                if current_item and current_item.is_dir:
                    self._navigate_to_directory(current_item.path)
                    return True
            
            # Enter = ouvrir
            elif key_event.key() == Qt.Key_Return or key_event.key() == Qt.Key_Enter:
                current_item = self.results_list.currentItem()
                if current_item:
                    self._on_item_activated(current_item)
                return True
            
            # Alt+Enter = ouvrir l'emplacement
            elif (key_event.key() == Qt.Key_Return or key_event.key() == Qt.Key_Enter) and key_event.modifiers() & Qt.AltModifier:
                current_item = self.results_list.currentItem()
                if current_item:
                    parent_dir = os.path.dirname(current_item.path)
                    self._open_file(parent_dir)
                return True
            
            # Ctrl+P = épingler
            elif key_event.key() == Qt.Key_P and key_event.modifiers() & Qt.ControlModifier:
                self._pin_current_selection()
                return True
            
            # Échap pour retourner à la barre de recherche
            elif key_event.key() == Qt.Key_Escape:
                self.search_bar.setFocus()
                self.search_bar.selectAll()
                return True
        
        # Propager l'événement
        return super().eventFilter(obj, event)
    
    def _navigate_back(self):
        """Navigue en arrière dans l'historique"""
        if self.history and self.history_index >= 0:
            # Obtenir le dossier précédent
            prev_dir = self.history[self.history_index]
            self.history_index -= 1
            
            # Naviguer sans ajouter à l'historique
            self.current_dir = prev_dir
            self.path_bar.setText(prev_dir)
            self.path_bar.setVisible(True)
            self._load_directory_contents(prev_dir)
    
    def _navigate_forward(self):
        """Navigue en avant dans l'historique"""
        if self.history and self.history_index < len(self.history) - 1:
            # Obtenir le dossier suivant
            self.history_index += 1
            next_dir = self.history[self.history_index]
            
            # Naviguer sans ajouter à l'historique
            self.current_dir = next_dir
            self.path_bar.setText(next_dir)
            self.path_bar.setVisible(True)
            self._load_directory_contents(next_dir)
    
    def _pin_current_selection(self):
        """Épingle l'élément actuellement sélectionné"""
        # Vérifier s'il y a une sélection dans la liste
        current_item = self.results_list.currentItem()
        if current_item:
            # Ajouter aux épinglés
            self.config.add_pinned_item(current_item.path, current_item.name)
            
            # Recharger les éléments épinglés
            self._load_pinned_items()
            
            # Afficher le conteneur des épinglés
            self.pinned_container.setVisible(True)
    
    def _on_scheduled_update(self):
        """Effectue une mise à jour planifiée"""
        # Planifier une mise à jour incrémentielle
        self.indexer.schedule_incremental_update()
    
    def _update_ui_state(self):
        """Met à jour l'état de l'interface utilisateur"""
        # Mettre à jour le focus si nécessaire
        if self.visible and not self.search_bar.hasFocus() and not self.results_list.hasFocus():
            self.search_bar.setFocus()
    
    def _show_settings(self):
        """Affiche la fenêtre de configuration"""
        # Importer localement pour éviter les dépendances circulaires
        from ui.settings import SettingsDialog
        
        # Créer et afficher la fenêtre
        settings_dialog = SettingsDialog(self.config, self.indexer, self)
        settings_dialog.setWindowModality(Qt.ApplicationModal)
        
        # Se connecter au signal de fermeture
        settings_dialog.config_updated.connect(self._on_config_updated)
        
        # Afficher la fenêtre
        settings_dialog.exec_()
    
    def _on_config_updated(self):
        """Gère la mise à jour de la configuration"""
        try:
            # Recharger les éléments épinglés
            self._load_pinned_items()
            
            # Configurer le nouveau raccourci avec un délai
            # pour s'assurer que tout est bien initialisé
            QTimer.singleShot(200, self.setup_global_hotkey)
            
            # Redémarrer la surveillance avec un délai plus long
            QTimer.singleShot(500, self.watcher.start)
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de la configuration: {e}")
    
    def show_launcher(self):
        """Affiche le lanceur"""
        # Réinitialiser l'état
        self.current_dir = ""
        self.path_bar.setVisible(False)
        self.results_list.clear()
        
        # Effacer la barre de recherche
        self.search_bar.clear()
        
        # Positionner la fenêtre
        self._center_on_screen()
        
        # Afficher la fenêtre
        self.show()
        self.raise_()
        self.activateWindow()
        
        # Donner le focus à la barre de recherche
        self.search_bar.setFocus()
        
        # Mettre à jour l'état
        self.visible = True
    
    def hide_launcher(self):
        """Masque le lanceur"""
        self.hide()
        self.visible = False
    
    def setup_global_hotkey(self):
        """Configure le raccourci clavier global"""
        # Récupérer la configuration du raccourci
        hotkey_config = self.config.get("hotkey", {"modifier": "ctrl", "key": "space"})
        modifier_str = hotkey_config["modifier"]
        key_str = hotkey_config["key"]
        
        # Convertir en codes Windows
        modifier_map = {
            "ctrl": win32con.MOD_CONTROL,
            "alt": win32con.MOD_ALT,
            "shift": win32con.MOD_SHIFT,
            "win": win32con.MOD_WIN
        }
        
        key_map = {
            "space": win32con.VK_SPACE,
            "tab": win32con.VK_TAB,
            "return": win32con.VK_RETURN,
            "escape": win32con.VK_ESCAPE
        }
        
        # Convertir les valeurs
        modifier = modifier_map.get(modifier_str.lower(), win32con.MOD_CONTROL)
        
        # Vérifier si key_str est une chaîne d'un seul caractère ou un mot clé spécial
        if key_str.lower() in key_map:
            vk_code = key_map.get(key_str.lower())
        elif len(key_str) == 1:
            vk_code = ord(key_str.upper())
        else:
            vk_code = win32con.VK_SPACE
        
        try:
            # Libérer l'ancien raccourci s'il existe
            hotkey_manager = HotkeyManager.get_instance()
            if self._hotkey_id is not None:
                hotkey_manager.unregister_hotkey(self._hotkey_id)
                self._hotkey_id = None
            
            # Enregistrer le nouveau raccourci
            self._hotkey_id = hotkey_manager.register_hotkey(
                self.show_launcher,  # Callback
                modifier,            # Modificateur
                vk_code              # Code de touche
            )
            
            if self._hotkey_id is not None:
                logger.info(f"Raccourci global enregistré: {modifier_str}+{key_str}")
            else:
                logger.error(f"Impossible d'enregistrer le raccourci global: {modifier_str}+{key_str}")
                
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation du raccourci global: {e}")


    def closeEvent(self, event):
        """Gère l'événement de fermeture de la fenêtre"""
        # Masquer au lieu de fermer
        self.hide_launcher()
        event.ignore()
