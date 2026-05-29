from settings.settings import (
    SAVE_DIR, SETTINGS_FILE, CUSTOM_CIDRS_FILE,
    DEFAULT_SETTINGS, load_settings, save_settings,
    load_custom_cidrs, save_custom_cidrs,
)
from settings.history import (
    ensure_save_dir, save_results_to_file, load_results_from_file,
    get_history_list,
)
