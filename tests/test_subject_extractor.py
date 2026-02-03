"""Tests for SubjectExtractor (subject grouping and type inference)."""

import pytest

from command_controller.subject_extractor import SubjectExtractor, SubjectGroup


class TestSubjectExtractor:
    """Test suite for SubjectExtractor."""

    def test_empty_steps_returns_empty_list(self):
        """Test that empty step list returns empty subject groups."""
        extractor = SubjectExtractor()
        groups = extractor.extract("open something", [])
        assert groups == []

    def test_single_subject_single_step(self):
        """Test single step creates single subject group."""
        extractor = SubjectExtractor()
        steps = [{"intent": "open_url", "url": "https://youtube.com"}]

        groups = extractor.extract("open youtube", steps)

        assert len(groups) == 1
        assert groups[0].subject_name == "YouTube"
        assert groups[0].subject_type == "url"
        assert len(groups[0].steps) == 1
        assert groups[0].start_index == 0

    def test_single_subject_multiple_steps(self):
        """Test multiple steps with same subject are grouped."""
        extractor = SubjectExtractor()
        steps = [
            {"intent": "open_url", "url": "https://youtube.com"},
            {"intent": "type_text", "text": "cats"},
            {"intent": "key_combo", "keys": ["enter"]},
        ]

        groups = extractor.extract("open youtube and search cats", steps)

        assert len(groups) == 1
        assert groups[0].subject_name == "YouTube"
        assert groups[0].subject_type == "url"
        assert len(groups[0].steps) == 3

    def test_multi_subject_with_conjunction(self):
        """Test multiple subjects separated by 'and' conjunction."""
        extractor = SubjectExtractor()
        steps = [
            {"intent": "open_url", "url": "https://gmail.com"},
            {"intent": "open_url", "url": "https://youtube.com"},
        ]

        groups = extractor.extract("open Gmail and YouTube", steps)

        assert len(groups) == 2
        assert groups[0].subject_name == "Gmail"
        assert groups[0].subject_type == "url"
        assert groups[1].subject_name == "YouTube"
        assert groups[1].subject_type == "url"

    def test_multi_subject_with_then_conjunction(self):
        """Test multiple subjects separated by 'then' conjunction."""
        extractor = SubjectExtractor()
        steps = [
            {"intent": "open_app", "app": "Spotify"},
            {"intent": "open_app", "app": "Slack"},
        ]

        groups = extractor.extract("open Spotify then Slack", steps)

        assert len(groups) == 2
        assert groups[0].subject_name == "Spotify"
        assert groups[0].subject_type == "app"
        assert groups[1].subject_name == "Slack"
        assert groups[1].subject_type == "app"

    def test_subject_type_inference_url(self):
        """Test that URL intents are correctly typed as 'url'."""
        extractor = SubjectExtractor()
        steps = [{"intent": "open_url", "url": "https://github.com"}]

        groups = extractor.extract("open github", steps)

        assert groups[0].subject_type == "url"

    def test_subject_type_inference_app(self):
        """Test that app intents are correctly typed as 'app'."""
        extractor = SubjectExtractor()
        steps = [{"intent": "open_app", "app": "Terminal"}]

        groups = extractor.extract("open terminal", steps)

        assert groups[0].subject_type == "app"

    def test_subject_type_inference_file(self):
        """Test that file intents are correctly typed as 'file'."""
        extractor = SubjectExtractor()
        steps = [{"intent": "open_file", "path": "/Users/test/document.pdf"}]

        groups = extractor.extract("open document", steps)

        assert groups[0].subject_type == "file"
        assert groups[0].subject_name == "document.pdf"

    def test_subject_type_inference_unknown(self):
        """Test that unknown intents are typed as 'unknown'."""
        extractor = SubjectExtractor()
        steps = [{"intent": "scroll", "direction": "down"}]

        groups = extractor.extract("scroll down", steps)

        assert groups[0].subject_type == "unknown"
        assert groups[0].subject_name == "Unknown"

    def test_domain_extraction_youtube(self):
        """Test YouTube URL extraction."""
        extractor = SubjectExtractor()
        steps = [{"intent": "open_url", "url": "https://www.youtube.com/watch?v=123"}]

        groups = extractor.extract("open youtube", steps)

        assert groups[0].subject_name == "YouTube"

    def test_domain_extraction_gmail(self):
        """Test Gmail URL extraction."""
        extractor = SubjectExtractor()
        steps = [{"intent": "open_url", "url": "https://mail.google.com/mail"}]

        groups = extractor.extract("open gmail", steps)

        assert groups[0].subject_name == "Gmail"

    def test_domain_extraction_google(self):
        """Test Google URL extraction."""
        extractor = SubjectExtractor()
        steps = [{"intent": "open_url", "url": "https://www.google.com"}]

        groups = extractor.extract("open google", steps)

        assert groups[0].subject_name == "Google"

    def test_domain_extraction_github(self):
        """Test GitHub URL extraction."""
        extractor = SubjectExtractor()
        steps = [{"intent": "open_url", "url": "https://github.com/user/repo"}]

        groups = extractor.extract("open github", steps)

        assert groups[0].subject_name == "GitHub"

    def test_domain_extraction_generic_url(self):
        """Test generic URL extraction falls back to domain."""
        extractor = SubjectExtractor()
        steps = [{"intent": "open_url", "url": "https://example.com/path"}]

        groups = extractor.extract("open example", steps)

        # Should extract "https:" as first part before "/"
        assert "https:" in groups[0].subject_name or "example.com" in groups[0].subject_name

    def test_file_path_extraction(self):
        """Test file path extraction."""
        extractor = SubjectExtractor()
        steps = [{"intent": "open_file", "path": "/Users/test/Documents/report.pdf"}]

        groups = extractor.extract("open report", steps)

        assert groups[0].subject_name == "report.pdf"

    def test_web_send_message_subject(self):
        """Test web_send_message intent subject extraction."""
        extractor = SubjectExtractor()
        steps = [{"intent": "web_send_message", "contact": "Alice", "message": "Hello"}]

        groups = extractor.extract("send message to Alice", steps)

        assert groups[0].subject_name == "Alice"
        assert groups[0].subject_type == "url"  # web_ prefix

    def test_start_index_preservation(self):
        """Test that start_index preserves execution order."""
        extractor = SubjectExtractor()
        steps = [
            {"intent": "open_app", "app": "Spotify"},  # 0
            {"intent": "type_text", "text": "rock"},  # 1
            {"intent": "open_app", "app": "Slack"},  # 2
        ]

        groups = extractor.extract("open Spotify then Slack", steps)

        assert len(groups) == 2
        assert groups[0].start_index == 0
        assert groups[1].start_index == 2

    def test_step_assignment_to_correct_subject(self):
        """Test that steps are assigned to correct subject groups."""
        extractor = SubjectExtractor()
        steps = [
            {"intent": "open_url", "url": "https://youtube.com"},  # YouTube
            {"intent": "type_text", "text": "cats"},  # YouTube
            {"intent": "open_url", "url": "https://gmail.com"},  # Gmail
            {"intent": "type_text", "text": "search query"},  # Gmail
        ]

        groups = extractor.extract("open YouTube and Gmail", steps)

        assert len(groups) == 2
        assert groups[0].subject_name == "YouTube"
        assert len(groups[0].steps) == 2
        assert groups[1].subject_name == "Gmail"
        assert len(groups[1].steps) == 2

    def test_no_conjunction_but_multiple_subjects(self):
        """Test multiple subjects without explicit conjunction."""
        extractor = SubjectExtractor()
        steps = [
            {"intent": "open_app", "app": "Finder"},
            {"intent": "open_app", "app": "Terminal"},
        ]

        groups = extractor.extract("open Finder Terminal", steps)

        # Should detect multiple subjects even without conjunction
        assert len(groups) == 2

    def test_ambiguous_steps_assigned_to_current_subject(self):
        """Test that ambiguous steps stay with current subject."""
        extractor = SubjectExtractor()
        steps = [
            {"intent": "open_url", "url": "https://youtube.com"},
            {"intent": "scroll", "direction": "down"},  # Ambiguous
            {"intent": "type_text", "text": "cats"},  # Ambiguous
        ]

        groups = extractor.extract("open youtube", steps)

        # All steps should be grouped with YouTube
        assert len(groups) == 1
        assert groups[0].subject_name == "YouTube"
        assert len(groups[0].steps) == 3

    def test_llm_interpreter_none_uses_heuristics(self):
        """Test that None LLM interpreter uses keyword heuristics."""
        extractor = SubjectExtractor(llm_interpreter=None)
        steps = [{"intent": "open_url", "url": "https://youtube.com"}]

        groups = extractor.extract("open youtube", steps)

        assert len(groups) == 1
        assert groups[0].subject_name == "YouTube"

    def test_case_insensitive_matching(self):
        """Test that subject matching is case-insensitive."""
        extractor = SubjectExtractor()
        steps = [
            {"intent": "open_url", "url": "https://YOUTUBE.com"},
            {"intent": "type_text", "text": "test"},
        ]

        groups = extractor.extract("open youtube", steps)

        assert len(groups) == 1
        assert groups[0].subject_name == "YouTube"

    def test_partial_match_assigns_to_subject(self):
        """Test that partial matches assign steps to correct subject."""
        extractor = SubjectExtractor()
        steps = [
            {"intent": "open_url", "url": "https://github.com"},
            {"intent": "open_url", "url": "https://github.com/repo"},  # Partial match
        ]

        groups = extractor.extract("open github", steps)

        # Both should be in same group (partial matching)
        assert len(groups) == 1
        assert len(groups[0].steps) == 2

    def test_complex_multi_subject_command(self):
        """Test complex command with multiple subjects and conjunctions."""
        extractor = SubjectExtractor()
        steps = [
            {"intent": "open_url", "url": "https://gmail.com"},
            {"intent": "type_text", "text": "work"},
            {"intent": "open_url", "url": "https://youtube.com"},
            {"intent": "type_text", "text": "music"},
            {"intent": "open_app", "app": "Spotify"},
        ]

        groups = extractor.extract("open Gmail and YouTube and Spotify", steps)

        assert len(groups) == 3
        assert groups[0].subject_name == "Gmail"
        assert groups[1].subject_name == "YouTube"
        assert groups[2].subject_name == "Spotify"
