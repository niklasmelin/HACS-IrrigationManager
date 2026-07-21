"""Tests for Solar Irrigation progress reporting."""

import pytest
from custom_components.solar_irrigation.progress import progress_tracker

def test_progress_tracker_initialization():
    """Test that progress tracker initializes correctly."""
    assert progress_tracker is not None
    assert hasattr(progress_tracker, 'add_progress')
    assert hasattr(progress_tracker, 'update_status')

def test_progress_reporting():
    """Test progress reporting functionality."""
    # Clear any existing progress
    progress_tracker.clear_progress()
    
    # Add a progress message
    progress_tracker.add_progress("Test message", "info")
    
    # Check that progress was recorded
    report = progress_tracker.get_progress_report()
    assert len(report["messages"]) == 1
    assert report["messages"][0]["message"] == "Test message"
    assert report["messages"][0]["level"] == "info"

def test_status_update():
    """Test status update functionality."""
    progress_tracker.update_status("test_status")
    assert progress_tracker.get_current_status() == "test_status"
    
    # Test getting last message
    progress_tracker.add_progress("Another test")
    assert "Another test" in progress_tracker.get_last_message()