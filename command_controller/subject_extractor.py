"""Extract distinct subjects and group associated steps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from command_controller.llm import LocalLLMInterpreter

from utils.log_utils import tprint
from utils.settings_store import is_deep_logging, deep_log


@dataclass
class SubjectGroup:
    """A group of steps associated with a single subject."""

    subject_name: str  # "YouTube", "Gmail", "Spotify"
    subject_type: str  # "url" | "app" | "file" | "unknown"
    steps: list[dict]  # Steps associated with this subject
    start_index: int  # Original step index (preserves execution order)


class SubjectExtractor:
    """Extract distinct subjects and group associated steps."""

    def __init__(self, llm_interpreter: LocalLLMInterpreter | None = None) -> None:
        """Initialize subject extractor.

        Args:
            llm_interpreter: Optional LLM for semantic subject identification.
                           If None, uses keyword-based heuristics.
        """
        self._llm = llm_interpreter

    def extract(self, text: str, steps: list[dict]) -> list[SubjectGroup]:
        """Group steps by subject.

        Args:
            text: Original command text (e.g., "open Gmail and Spotify")
            steps: Validated step list from engine

        Returns:
            List of SubjectGroup objects, preserving execution order
        """
        if not steps:
            return []

        # Identify distinct subjects
        subjects = self._identify_subjects(text, steps)

        if is_deep_logging():
            deep_log(f"[DEEP][SUBJECT_EXTRACTOR] Identified subjects: {subjects}")

        # If no clear subjects or single subject, return all steps in one group
        if not subjects or len(subjects) == 1:
            # Infer subject from first step
            first_step = steps[0]
            subject_name = self._get_subject_from_step(first_step)
            subject_type = self._infer_subject_type(subject_name, first_step)

            return [
                SubjectGroup(
                    subject_name=subject_name,
                    subject_type=subject_type,
                    steps=steps,
                    start_index=0,
                )
            ]

        # Assign steps to subjects
        return self._assign_steps_to_subjects(subjects, steps)

    def _identify_subjects(self, text: str, steps: list[dict]) -> list[str]:
        """Identify distinct entities in command text.

        Args:
            text: Command text
            steps: Step list

        Returns:
            List of subject names (e.g., ["Gmail", "Spotify"])
        """
        subjects: list[str] = []

        # Extract subjects from steps
        for step in steps:
            subject = self._get_subject_from_step(step)
            if subject and subject not in subjects:
                subjects.append(subject)

        # Check for conjunctions in text indicating multiple subjects
        text_lower = text.lower()
        has_conjunction = " and " in text_lower or " then " in text_lower

        # If multiple subjects detected or conjunction present, return subjects
        if len(subjects) > 1 or (has_conjunction and len(subjects) > 0):
            return subjects

        # Single subject or unclear - return as-is
        return subjects

    def _get_subject_from_step(self, step: dict) -> str:
        """Extract subject name from a step.

        Args:
            step: Intent step

        Returns:
            Subject name (e.g., "Gmail", "YouTube", "myfile.txt")
        """
        intent = step.get("intent", "")

        if intent == "open_app":
            return step.get("app", "Unknown App")
        elif intent == "open_url":
            url = step.get("url", "")
            # Extract domain or use full URL
            if "youtube" in url.lower():
                return "YouTube"
            elif "gmail" in url.lower() or "mail.google" in url.lower():
                return "Gmail"
            elif "google" in url.lower():
                return "Google"
            elif "github" in url.lower():
                return "GitHub"
            else:
                return url.split("/")[0] if "/" in url else url
        elif intent == "open_file":
            path = step.get("path", "")
            # Extract filename
            return path.split("/")[-1] if "/" in path else path
        elif intent == "web_send_message":
            return step.get("contact", "Contact")
        else:
            return "Unknown"

    def _assign_steps_to_subjects(
        self, subjects: list[str], steps: list[dict]
    ) -> list[SubjectGroup]:
        """Associate steps with their target subjects.

        Args:
            subjects: List of identified subjects
            steps: Step list

        Returns:
            List of SubjectGroup objects
        """
        groups: list[SubjectGroup] = []
        current_subject_idx = 0

        for i, step in enumerate(steps):
            step_subject = self._get_subject_from_step(step)

            # Find matching subject
            matched_idx = None
            for idx, subject in enumerate(subjects):
                if subject.lower() in step_subject.lower() or step_subject.lower() in subject.lower():
                    matched_idx = idx
                    break

            # If no match, add to current subject group
            if matched_idx is None:
                matched_idx = current_subject_idx

            # Update current subject
            current_subject_idx = matched_idx

            # Find or create group for this subject
            existing_group = None
            for group in groups:
                if group.subject_name == subjects[matched_idx]:
                    existing_group = group
                    break

            if existing_group:
                existing_group.steps.append(step)
            else:
                subject_type = self._infer_subject_type(subjects[matched_idx], step)
                groups.append(
                    SubjectGroup(
                        subject_name=subjects[matched_idx],
                        subject_type=subject_type,
                        steps=[step],
                        start_index=i,
                    )
                )

        return groups

    def _infer_subject_type(self, subject: str, step: dict) -> str:
        """Infer subject type from step intent.

        Args:
            subject: Subject name
            step: First step associated with subject

        Returns:
            "url" | "app" | "file" | "unknown"
        """
        intent = step.get("intent", "")

        if intent == "open_url" or intent.startswith("web_"):
            return "url"
        elif intent == "open_app":
            return "app"
        elif intent == "open_file":
            return "file"
        else:
            return "unknown"
