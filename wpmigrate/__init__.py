"""wp-migrator: scrape arbitrary web pages into WordPress Gutenberg WXR imports.

Pipeline (see pipeline.py): fetch -> extract main content -> tokenize images ->
download+upload images to the WP media library -> LLM cleanup into a constrained
HTML whitelist -> deterministic conversion to Gutenberg block markup -> WXR.
"""

__version__ = "0.1.0"
