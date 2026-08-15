"""Configurable constants for Storyloom."""

# ── Save format ──────────────────────────────────────────────────
SAVE_VERSION = 3           # save file format version; mismatch → load error (user decides)

# ── Default directory names ──────────────────────────────────────
DEFAULT_SAVES_DIR = "saves"
DEFAULT_MEDIA_DIR = "media"
DEFAULT_SYSTEM_MEDIA_DIR = "system_media"
SYSTEM_MANIFEST_FILENAME = "_manifest.json"

# ── Sliding window ─────────────────────────────────────────────
WINDOW_SIZE = 3          # full rounds to keep in window
FIRST_COMPRESSION_AT = 5  # round number to trigger first compression

# ── Line count ranges ─────────────────────────────────────────
LINES_PER_ROUND_MIN = 150
LINES_PER_ROUND_MAX = 300

# ── Language-specific segment limits ───────────────────────────
LANGUAGE_SEG_LIMITS = {
    "zh-CN": {"narration": 40, "dialogue": 50},
    "zh-TW": {"narration": 40, "dialogue": 50},
    "en":    {"narration": 120, "dialogue": 160},
}
SUPPORTED_LANGUAGES = {"zh-CN", "zh-TW", "en"}
DEFAULT_LANGUAGE = "en"

# ── Bridge ─────────────────────────────────────────────────────
BRIDGE_POSITION_RATIO = 0.75  # target bridge position (fraction of total, pre-bridge)
MIN_TAIL_LINES = 25           # minimum lines per branch after bridge

# ── Context budget ────────────────────────────────────────────
MAX_CONTEXT_TOKENS = 50_000   # target ceiling

# ── Reserved variable names ──────────────────────────────────
# <set var="BRANCH" val="..."/> sets current_branch directly
# without going through GameState (no state variable registration needed).
BRANCH_VAR_NAME = "BRANCH"
SCENE_VAR_NAME = "SCENE"     # <set var="SCENE" val="..."> → SCENE event (Phase 2)

# ── Co-creation ──────────────────────────────────────────────────

# Scoped variable caps (per 2026-07-21 scoped-variables spec)
VARIABLE_CAP = 6            # max total variables across all scopes
GLOBAL_SCOPE = "GLOBAL"     # default scope identifier (omit = GLOBAL)

# Story config title constraints
STORY_TITLE_MIN_CHARS = 1
STORY_TITLE_MAX_CHARS = 30

# Outline node ranges by tier (prompt reference only — not engine-enforced)
OUTLINE_NODE_RANGES = {
    "short":  (5, 10),
    "medium": (10, 20),
    "long":   (20, 30),
}

# ── API defaults ──────────────────────────────────────────────
DEFAULT_MODEL = "deepseek-v4-pro"
STREAM_STALL_TIMEOUT_SEC = 180

# ── Image API defaults ───────────────────────────────────────
DEFAULT_IMG_MODEL = "flux-2-pro"
DEFAULT_IMG_BASE_URL = "https://api.apiyi.com/v1"
IMAGE_GEN_TIMEOUT_SEC = 300     # image generation can take minutes
IMAGE_DOWNLOAD_TIMEOUT_SEC = 60

# ── Background removal model ──────────────────────────────────
# u2netp.onnx (~4.4 MB) is bundled as package data.  At runtime
# img_utils._model_dir() finds it via the package path.
BG_REMOVAL_MODEL_FILENAME = "u2netp.onnx"
BG_REMOVAL_MODEL_SHA256 = (
    "309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8"
)

# ── Asset management ────────────────────────────────────────────
CLEANUP_KEEP_COUNT = 80      # per-type keep target for auto-clean (> TOP_N=60 margin)

# ── Task framework (Phase 2) ────────────────────────────────────
TASK_POOL_MAX_WORKERS = 6    # Thread pool for LLM match/select/generate tasks

# ── Asset generation (Phase 2 §7.8b) ────────────────────────────
PREBUILD_MAX_WORKERS = 6     # Prebuilder concurrent image generation
GENERATE_LIBRARY_TOP_N = 60      # library entries in LLM selection prompt (system ~25 + user ~35)
# Reference images cause 4.4x slowdown on FLUX.2 Pro (15s→64s, see
# scripts/bench_ref_images.py).  Set to 0 for speed; restore to 3 if
# future models handle references faster or strong style consistency is needed.
GENERATE_REF_IMAGE_COUNT = 0     # max reference images for style guidance

# ── Auto-update ────────────────────────────────────────────────────
# Update checks read a small per-layer manifest file via the GitHub release
# *download* CDN (``releases/download/…``), never the rate-limited REST API
# (``api.github.com``).  See docs/superpowers/specs/2026-08-10-auto-update-design.md §4.
GITHUB_REPO_OWNER = "SiriLee"
GITHUB_REPO_NAME = "Storyloom"
GITHUB_RELEASES_URL = (
    f"https://github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases"
)
GITHUB_DOWNLOAD_BASE = f"{GITHUB_RELEASES_URL}/download"
UPDATE_MANIFEST_FILENAME = "update.json"        # app layer manifest asset
SYSTEM_MEDIA_TAG = "system-media"               # fixed release tag for system_media
SYSTEM_MEDIA_MANIFEST_FILENAME = "_manifest.json"  # version + min_app_version
LAUNCHER_TAG = "launcher"                       # fixed release tag for the launcher
LAUNCHER_MANIFEST_FILENAME = "VERSION"          # plain-text launcher version
