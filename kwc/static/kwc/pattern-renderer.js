/**
 * Client-side Django template pattern renderer.
 * Provides a minimal implementation to preview naming patterns in the browser.
 */

/**
 * Render a Django-like template pattern with the given values.
 * Supports:
 * - Simple conditionals: {% if X %}...{% endif %}
 * - Variables: {{ variable }}
 * - Pad filter: {{ variable|pad:N }}
 *
 * @param {Object} values - Object with template variables (title, year, season, episode, counter, etc.)
 * @param {string} pattern - Django template pattern string
 * @returns {string} Rendered pattern
 */
function renderPattern(values, pattern) {
  // Replace simple conditionals {% if X %}...{% endif %}
  pattern = pattern.replace(/\{\%\s*if\s+season\s*\%\}([\s\S]*?)\{\%\s*endif\s*\%\}/g, (_m, inner) => 
    (values.season ? inner : '')
  );
  pattern = pattern.replace(/\{\%\s*if\s+episode\s*\%\}([\s\S]*?)\{\%\s*endif\s*\%\}/g, (_m, inner) => 
    (values.episode ? inner : '')
  );
  pattern = pattern.replace(/\{\%\s*if\s+year\s*\%\}([\s\S]*?)\{\%\s*endif\s*\%\}/g, (_m, inner) => 
    (values.year ? inner : '')
  );

  // Replace variables with pad filter first (more specific)
  pattern = pattern.replace(/\{\{\s*counter\s*\|\s*pad:(\d+)\s*\}\}/g, (_m, w) => 
    String(values.counter || 1).padStart(parseInt(w, 10) || 0, '0')
  );
  pattern = pattern.replace(/\{\{\s*season\s*\|\s*pad:(\d+)\s*\}\}/g, (_m, w) => {
    const num = parseInt(values.season, 10);
    return Number.isNaN(num) ? (values.season || '') : String(num).padStart(parseInt(w, 10) || 0, '0');
  });
  pattern = pattern.replace(/\{\{\s*episode\s*\|\s*pad:(\d+)\s*\}\}/g, (_m, w) => {
    const num = parseInt(values.episode, 10);
    return Number.isNaN(num) ? (values.episode || '') : String(num).padStart(parseInt(w, 10) || 0, '0');
  });

  // Replace simple variables (after pad filter to avoid conflicts)
  pattern = pattern.replace(/\{\{\s*title\s*\}\}/g, values.title || '');
  pattern = pattern.replace(/\{\{\s*year\s*\}\}/g, values.year || '');
  pattern = pattern.replace(/\{\{\s*season\s*\}\}/g, values.season || '');
  pattern = pattern.replace(/\{\{\s*episode\s*\}\}/g, values.episode || '');
  pattern = pattern.replace(/\{\{\s*counter\s*\}\}/g, values.counter || '1');

  return pattern;
}

// Export for module usage (if needed)
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { renderPattern };
}
