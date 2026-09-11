import os

# AKTIF SEBELUM backend.config di-import test mana pun:
# suite hermetik — selalu default, .env lokal tidak boleh bikin merah palsu.
os.environ.setdefault("SNOOPY_TEST_DEFAULTS", "1")
