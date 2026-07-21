import pytest
from unittest.mock import MagicMock
from ui.gui_validation import ValidationController

def test_validate_thread_input():
    mock_gui = MagicMock()
    mock_gui.state.run_target.get.return_value = "Local"
    mock_gui.max_threads = 8
    
    ctrl = ValidationController(mock_gui)
    
    # Valid inputs
    assert ctrl._validate_thread_input("") is True
    assert ctrl._validate_thread_input("1") is True
    assert ctrl._validate_thread_input("4") is True
    assert ctrl._validate_thread_input("8") is True
    
    # Invalid inputs
    assert ctrl._validate_thread_input("9") is False # exceeds max
    assert ctrl._validate_thread_input("0") is False # less than 1
    assert ctrl._validate_thread_input("-1") is False
    assert ctrl._validate_thread_input("abc") is False

def test_validate_thread_input_remote_unknown():
    mock_gui = MagicMock()
    mock_gui.state.run_target.get.return_value = "Server"
    mock_gui.remote_ctrl._server_thread_max_known.return_value = False
    
    ctrl = ValidationController(mock_gui)
    
    # When server thread max is unknown, we should only allow empty (which might revert to default or just block until known)
    assert ctrl._validate_thread_input("") is True
    assert ctrl._validate_thread_input("4") is False

def test_clamp_threads():
    mock_gui = MagicMock()
    mock_gui.max_threads = 16
    mock_gui.state.threads.get.return_value = "20"
    
    ctrl = ValidationController(mock_gui)
    ctrl._clamp_threads()
    
    # Should clamp 20 down to 16
    mock_gui.state.threads.set.assert_called_with(16)
    
    mock_gui.state.threads.get.return_value = "0"
    ctrl._clamp_threads()
    
    # Should clamp 0 up to 1
    mock_gui.state.threads.set.assert_called_with(1)
