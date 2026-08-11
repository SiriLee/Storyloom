"""Manages conversation messages array with sliding window + compression."""

from storyloom.config import WINDOW_SIZE, FIRST_COMPRESSION_AT
import re


class ContextManager:
    """Manages the messages array for conversation-based LLM interaction.

    Architecture:
      [0] System prompt (permanent — role, format, rules, story setting)
      [... compressed rounds as user/assistant pair ...]
      [... last WINDOW_SIZE full rounds (user + assistant each) ...]
      [last] Current round user message

    The system prompt is set once and NEVER removed or compressed.
    All rounds (including Round 1) go through the same window/compression
    cycle — the system prompt replaces the old Round 1 permanent anchor.
    """

    def __init__(self):
        self._system_prompt: str | None = None
        self._rounds: list[dict] = []
        self._compressed_summaries: list[str] = []
        self._round_count: int = 0
        self._last_bridge_text: str = ""

    @property
    def round_count(self) -> int:
        return self._round_count

    def set_system_prompt(self, content: str) -> None:
        """Set the system prompt (permanent anchor).  Call once before
        the first ``add_round``.  The system prompt is always the first
        message in the array and is never compressed."""
        if self._system_prompt is not None:
            raise RuntimeError("System prompt already set")
        self._system_prompt = content

    def add_round(
        self,
        user_content: str,
        assistant_content: str,
        bridge_text: str = "",
        selected_branch: str | None = None,
    ) -> None:
        """Add a new round's messages and trigger compression if needed.

        Args:
            user_content: The Round N context message sent to the LLM.
            assistant_content: The LLM's XML response.
            bridge_text: Post-bridge text filtered by ``current_branch``
                         at parse time (provided by GameLoop).
            selected_branch: The branch name the player chose (None if no
                            choice was presented).
        """
        if self._system_prompt is None:
            raise RuntimeError(
                "System prompt not set — call set_system_prompt first"
            )

        checkpoint_text = self._extract_checkpoint_summaries(assistant_content)

        self._rounds.append({
            "round_num": self._round_count + 1,
            "user_content": user_content,
            "assistant_content": assistant_content,
            "checkpoint": checkpoint_text,
            "selected_branch": selected_branch,
        })
        self._round_count += 1

        self._last_bridge_text = bridge_text

        self._maybe_compress()

    def get_messages(self) -> list[dict]:
        """Build the full messages array for the next API call."""
        messages = []

        # System prompt is always first and never compressed
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})

        # Insert compressed summaries as a user/assistant pair
        if self._compressed_summaries:
            user_msg, asst_msg = self._build_compression_messages(
                self._compressed_summaries
            )
            messages.append({"role": "user", "content": user_msg})
            messages.append({"role": "assistant", "content": asst_msg})

        # Append the sliding window rounds in full
        window_rounds = self._get_window_rounds()
        for r in window_rounds:
            messages.append({"role": "user", "content": r["user_content"]})
            messages.append({"role": "assistant", "content": r["assistant_content"]})

        return messages

    def get_compressed_rounds(self) -> list[int]:
        """Return list of round numbers that have been compressed."""
        num_rounds = len(self._rounds)
        if num_rounds < FIRST_COMPRESSION_AT:
            return []
        window_count = min(WINDOW_SIZE, num_rounds)
        compressed_count = num_rounds - window_count
        if compressed_count > 0:
            return list(range(1, 1 + compressed_count))
        return []

    def get_window_rounds(self) -> list[int]:
        """Return list of round numbers currently in the window."""
        num_rounds = len(self._rounds)
        if num_rounds == 0:
            return []
        window_count = min(WINDOW_SIZE, num_rounds)
        start = num_rounds - window_count
        return list(range(start + 1, num_rounds + 1))

    def get_last_bridge_text(self) -> str:
        """Return bridge_text from the most recent round."""
        return self._last_bridge_text

    def get_compressed_summaries(self) -> list[str]:
        """Return compressed checkpoint summary strings."""
        return list(self._compressed_summaries)

    def _maybe_compress(self) -> None:
        """Compress rounds that have fallen out of the window."""
        total_rounds = len(self._rounds)
        if total_rounds < FIRST_COMPRESSION_AT:
            return

        window_count = min(WINDOW_SIZE, len(self._rounds))
        keep_start = len(self._rounds) - window_count
        if keep_start < 0:
            keep_start = 0

        for i in range(keep_start):
            cp = self._rounds[i].get("checkpoint", "")
            if cp and cp not in self._compressed_summaries:
                self._compressed_summaries.append(cp)

    def _get_window_rounds(self) -> list[dict]:
        """Get the round dicts currently in the sliding window."""
        window_count = min(WINDOW_SIZE, len(self._rounds))
        return self._rounds[-window_count:] if window_count > 0 else []

    @staticmethod
    def _extract_checkpoint_summaries(xml: str) -> str:
        """Extract checkpoint summary from XML output."""
        match = re.search(r'<checkpoint[^>]*summary="([^"]*)"', xml)
        return match.group(1) if match else ""

    @staticmethod
    def _build_compression_messages(summaries: list[str]) -> tuple[str, str]:
        """Build user/assistant message pair for compressed rounds."""
        items = "\n".join(f"- {s}" for s in summaries)
        user_msg = f"Key events so far:\n\n{items}"
        asst_msg = "(Summary of previous events. The story continues.)"
        return user_msg, asst_msg
