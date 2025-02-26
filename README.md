# QuickLaunch

A lightweight, resource-efficient application launcher and file indexer for Windows.

## Overview

QuickLaunch is a minimalist file indexing and launching application designed with performance optimization as its core principle. It provides a quick way to find and launch files and applications by indexing your file system and offering a fast search interface accessible via a global hotkey (default: Ctrl+Space).

## Key Features

- **Efficient Resource Usage**: Optimized for minimal CPU and RAM consumption
- **Fast File Indexing**: Intelligent file system indexing with change detection
- **Real-time File System Monitoring**: Detects and indexes new, modified, and deleted files
- **Smart Search**: Finds files quickly with prefix matching and fuzzy search capabilities
- **Customizable**: Configurable indexing locations, update intervals, and search options
- **Global Hotkey**: Quick access from anywhere with a customizable keyboard shortcut
- **Navigation**: Browse through folders directly in the interface
- **Pinned Items**: Save frequently used files or folders for quick access

## Architecture

The application follows a modular architecture organized into several core components:

### Core Components

- **Config**: Configuration management with caching for performance optimization
- **Indexer**: Resource-efficient file system indexer with throttling mechanisms
- **Watcher**: File system change monitoring using watchdog for local drives, custom polling for network shares
- **Database**: SQLite-based storage with query optimization and caching
- **Trie**: Custom trie data structure for ultra-fast search suggestions with minimal memory usage
- **UI**: Minimalist PyQt5-based interface with responsive design

### Directory Structure

```
├── core/
│   ├── __init__.py        # Core package initialization
│   ├── config.py          # Configuration management
│   ├── indexer.py         # File indexing engine
│   ├── watcher.py         # File system monitoring
│   └── searcher.py        # Search functionality
├── storage/
│   ├── __init__.py        # Storage package initialization
│   ├── db.py              # Database operations and caching
│   └── trie.py            # Optimized trie for fast search
├── ui/
│   ├── __init__.py        # UI package initialization
│   ├── launcher.py        # Main application window
│   ├── hotkeys.py         # Global hotkey handling
│   └── settings.py        # Configuration interface
└── main.py                # Application entry point
```

## Technical Details

### Performance Optimizations

- **Memory Management**:
  - Throttled indexing to limit memory spikes
  - Queue-based background processing
  - Selective depth indexing for network locations
  - Lazy loading and processing of file data

- **CPU Efficiency**:
  - Batch processing to control CPU utilization
  - Optimized SQLite configuration (WAL mode, cache settings)
  - Thread pooling and worker limits
  - Throttled event handling to reduce processing overhead

- **Disk I/O Optimization**:
  - Caching of frequently accessed data
  - Asynchronous configuration saving
  - Optimized database schema with appropriate indices
  - Transactional operations to reduce disk writes

### Concurrency Model

- **Threading Strategy**:
  - Main UI thread for responsiveness
  - Dedicated indexing thread for background processing
  - Dedicated file system watching thread
  - Thread-safe data access via locks

### Search Algorithm

The search functionality employs multiple strategies for optimal results:

1. **Exact Matching**: Prioritizes exact matches for immediate results
2. **Prefix Completion**: Suggests completions for partial inputs
3. **Fuzzy Matching**: Handles typographical errors and alternative spellings
4. **Trie-based Optimization**: Custom trie data structure with memory optimizations for efficient prefix lookups
5. **Levenshtein Distance**: Calculates edit distance for fuzzy matching with minimal memory usage

## Implementation Notes

### File System Interaction

- **Local Drives**: Uses watchdog for real-time file system event monitoring
- **Network Drives**: Employs a lightweight polling approach to conserve resources
- **Change Detection**: Throttles rapid changes to avoid overloading the system

### Global Hotkey Implementation

Uses a dedicated thread and Windows API (win32gui, win32api) to register and handle global hotkeys without blocking the main application.

### UI Design Philosophy

- **Minimalist Interface**: Clean, focused UI with no unnecessary elements
- **Keyboard-first Navigation**: Optimized for keyboard shortcuts and quick access
- **Non-intrusive**: Stays out of the way when not needed (system tray integration)

## Configuration Options

QuickLaunch offers numerous configuration options, accessible via the settings dialog:

### Indexing Locations

- Add/remove local folders to index
- Add/remove network shares to index
- Exclude specific paths from indexing
- Exclude file extensions from indexing

### Update Intervals

- Configure local drive update frequency (minutes)
- Configure network drive update frequency (minutes)
- Option to perform initial indexing at startup

### Search Options

- Maximum number of search results
- Database location customization
- Global hotkey configuration

## Development Guidelines

### Adding New Features

1. **Resource Efficiency First**: Always consider CPU, RAM, and disk impact
2. **Thread Safety**: Use appropriate locking mechanisms for shared data
3. **Error Handling**: Implement robust error recovery with appropriate logging
4. **UI Responsiveness**: Avoid blocking the main thread
5. **Backward Compatibility**: Maintain configuration compatibility

### Code Style

- **Docstrings**: Comprehensive documentation with parameter descriptions
- **Type Hints**: Use Python type annotations for better code clarity
- **Logging**: Appropriate logging levels for debugging and monitoring
- **Error Handling**: Specific exception handling with informative messages

## Future Improvements

Potential areas for enhancement:

1. **Search Enhancements**:
   - Content-based search for text files
   - Metadata extraction and indexing
   - Natural language query processing

2. **Performance Optimizations**:
   - Incremental trie updates to reduce memory pressure
   - More selective file monitoring based on usage patterns
   - Additional caching strategies for frequent searches

3. **UI Improvements**:
   - Customizable themes and appearance
   - Quick preview of files
   - Enhanced navigation options

4. **Additional Features**:
   - Plugin system for extensibility
   - Cloud storage integration
   - Search history and analytics

## Troubleshooting

### Common Issues

- **High CPU Usage**: May occur during initial indexing; will normalize after completion
- **Missing Files**: Check excluded paths and extensions in settings
- **Hotkey Not Working**: Possible conflict with other applications; try changing the hotkey

### Logging

QuickLaunch logs information to `launcher.log` in the application directory. This file is invaluable for diagnosing issues.

## Dependencies

- **Python 3.6+**: Base runtime environment
- **PyQt5**: UI framework
- **SQLite3**: Database backend
- **win32api/win32gui/win32con**: Windows API interaction
- **watchdog** (optional): Enhanced file system monitoring

## License

This project is proprietary software. All rights reserved.
