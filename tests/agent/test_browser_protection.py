"""
Unit and Integration Tests for FaceSentry Browser Protection Manager
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from apps.agent.facesentry_agent.browser_protection import BrowserProtectionManager
from packages.shared.schemas import BrowserProtectionConfigSchema
from packages.shared.enums import BrowserProtectionMode

class MockProcess:
    def __init__(self, name: str, is_alive: bool = True):
        self.name_val = name
        self.is_alive = is_alive
        self.terminated = False
        self.info = {'name': self.name_val}

    def is_running(self):
        return self.is_alive

    def terminate(self):
        self.terminated = True
        self.is_alive = False

@pytest.fixture
def mock_psutil():
    with patch('apps.agent.facesentry_agent.browser_protection.psutil') as mock_ps:
        yield mock_ps

@pytest.fixture
def mock_sqlite():
    with patch('apps.agent.facesentry_agent.browser_protection.sqlite3') as mock_sql:
        yield mock_sql


def test_browser_protection_disabled_by_default(mock_psutil):
    config = BrowserProtectionConfigSchema()
    assert config.enabled is False
    assert config.mode == BrowserProtectionMode.DISABLED

    manager = BrowserProtectionManager(config=config, is_windows=True)
    manager.protect()
    
    # Process iteration should not be called
    mock_psutil.process_iter.assert_not_called()


def test_browser_protection_requires_windows(mock_psutil):
    config = BrowserProtectionConfigSchema(enabled=True, mode=BrowserProtectionMode.CLOSE_BROWSER)
    manager = BrowserProtectionManager(config=config, is_windows=False)
    manager.protect()
    
    # Process iteration should not be called on non-Windows
    mock_psutil.process_iter.assert_not_called()


def test_browser_detection_and_close_success(mock_psutil):
    # Setup mock processes
    p_chrome = MockProcess("chrome.exe")
    p_edge = MockProcess("msedge.exe")
    p_other = MockProcess("notepad.exe")
    
    # Mock psutil behavior
    mock_psutil.process_iter.return_value = [p_chrome, p_edge, p_other]
    mock_psutil.wait_procs.return_value = ([p_chrome, p_edge], [])  # gone, alive
    
    # Configure manager
    config = BrowserProtectionConfigSchema(enabled=True, mode=BrowserProtectionMode.CLOSE_BROWSER)
    events = []
    manager = BrowserProtectionManager(
        config=config,
        is_windows=True,
        on_event=lambda e: events.append(e)
    )
    
    # Execute protect
    manager.protect()
    
    # Verify behavior
    assert p_chrome.terminated is True
    assert p_edge.terminated is True
    assert p_other.terminated is False
    
    # Verify events
    event_types = [e.event_type for e in events]
    assert "BROWSER_PROTECTION_TRIGGERED" in event_types
    assert "BROWSER_DETECTED" in event_types
    assert "BROWSER_CLOSE_REQUESTED" in event_types
    assert "BROWSER_CLOSE_SUCCEEDED" in event_types
    assert "SESSION_CLEANUP_STARTED" not in event_types  # Mode was CLOSE_BROWSER only


def test_session_cleanup_unsupported_for_firefox(mock_psutil, mock_sqlite):
    p_firefox = MockProcess("firefox.exe")
    mock_psutil.process_iter.return_value = [p_firefox]
    mock_psutil.wait_procs.return_value = ([p_firefox], [])
    
    config = BrowserProtectionConfigSchema(
        enabled=True, 
        mode=BrowserProtectionMode.CLOSE_BROWSER_AND_CLEAR_SESSION_COOKIES
    )
    
    events = []
    manager = BrowserProtectionManager(
        config=config,
        is_windows=True,
        on_event=lambda e: events.append(e)
    )
    
    manager.protect()
    
    # Verify Firefox was closed
    assert p_firefox.terminated is True
    
    # Verify SQLite was NEVER called (since firefox doesn't support safe cookie cleanup here)
    mock_sqlite.connect.assert_not_called()
    
    # Verify unsupported event was emitted
    cleanup_events = [e for e in events if "SESSION_CLEANUP" in e.event_type]
    assert len(cleanup_events) == 2
    assert cleanup_events[0].event_type == "SESSION_CLEANUP_STARTED"
    assert cleanup_events[1].event_type == "SESSION_CLEANUP_UNSUPPORTED"


@patch('os.path.exists', return_value=True)
def test_session_cleanup_success_for_chrome(mock_exists, mock_psutil, mock_sqlite):
    p_chrome = MockProcess("chrome.exe")
    mock_psutil.process_iter.return_value = [p_chrome]
    mock_psutil.wait_procs.return_value = ([p_chrome], [])
    
    # Mock SQLite DB
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_sqlite.connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    
    # Mock table check (returns one row indicating 'cookies' table exists)
    mock_cursor.fetchone.return_value = ('cookies',)
    mock_cursor.rowcount = 42
    
    config = BrowserProtectionConfigSchema(
        enabled=True, 
        mode=BrowserProtectionMode.CLOSE_BROWSER_AND_CLEAR_SESSION_COOKIES
    )
    events = []
    manager = BrowserProtectionManager(
        config=config,
        is_windows=True,
        on_event=lambda e: events.append(e)
    )
    
    manager.protect()
    
    # Verify Chrome was closed
    assert p_chrome.terminated is True
    
    # Verify SQLite was called correctly
    mock_sqlite.connect.assert_called_once()
    assert "DELETE FROM cookies WHERE is_persistent = 0 OR is_persistent = '0'" in mock_cursor.execute.call_args_list[-1][0][0]
    mock_conn.commit.assert_called_once()
    
    # Verify success event
    cleanup_events = [e for e in events if "SESSION_CLEANUP" in e.event_type]
    assert cleanup_events[-1].event_type == "SESSION_CLEANUP_SUCCEEDED"
